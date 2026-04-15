from __future__ import annotations

import logging
from datetime import date, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from common.ip import hash_ip
from common.qr import build_qr_svg

from .entitlements import is_reviews_pro, reviews_allowed, smart_filter_allowed, trial_available
from .models import Review, ReviewConfig, ReviewMode, ReviewVisit
from .serializers import (
    PublicReviewConfigSerializer,
    ReviewConfigSerializer,
    ReviewSerializer,
    ReviewStatusUpdateSerializer,
    ReviewSubmitSerializer,
)

logger = logging.getLogger(__name__)

# Re-use canonical set of statuses that keep public pages visible.
PUBLISHABLE_STATUSES = frozenset({'active', 'trialing', 'past_due'})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_review_config(business) -> ReviewConfig:
    config, _ = ReviewConfig.objects.get_or_create(business=business)
    return config


def _build_review_landing_url(slug: str) -> str:
    base_url = (
        getattr(settings, 'PUBLIC_MENU_BASE_URL', None)
        or getattr(settings, 'FRONTEND_URL', None)
        or 'http://localhost:3000'
    )
    return f"{base_url.rstrip('/')}/r/{slug}/"


# ---------------------------------------------------------------------------
# Throttle for public submit endpoint
# ---------------------------------------------------------------------------

class ReviewSubmitThrottle(AnonRateThrottle):
    rate = '30/hour'


# ---------------------------------------------------------------------------
# Private views (authenticated dashboard)
# ---------------------------------------------------------------------------

class ReviewConfigView(APIView):
    """
    GET  /api/v1/reviews/config/  — retrieve config
    PATCH /api/v1/reviews/config/ — update config
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'manage_reviews',
        'PATCH': 'manage_reviews',
    }

    def get(self, request):
        business = getattr(request, 'business')
        config = _ensure_review_config(business)
        serializer = ReviewConfigSerializer(config)
        return Response(serializer.data)

    def patch(self, request):
        business = getattr(request, 'business')
        config = _ensure_review_config(business)
        serializer = ReviewConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        changed = list(request.data.keys())
        logger.info(
            "[Reviews] Config updated business=%s fields=%s",
            business.id, changed,
        )
        return Response(serializer.data)


class ReviewQRCodeView(APIView):
    """
    GET /api/v1/reviews/qr/  — generate QR code.

    In ``direct`` mode the QR encodes the Google review URL directly so the
    end-user never touches Mi Rubro infrastructure.
    In ``smart_filter`` mode the QR points to the Mi Rubro landing page.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'manage_reviews',
    }

    def get(self, request):
        business = getattr(request, 'business')

        if not reviews_allowed(business):
            logger.warning("[Reviews] QR denied business=%s reason=plan_not_allowed", business.id)
            return Response(
                {'detail': 'Reseñas no disponibles en tu plan actual.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not business.slug:
            logger.warning("[Reviews] QR denied business=%s reason=no_slug", business.id)
            return Response(
                {'detail': 'El negocio no tiene un slug configurado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config = _ensure_review_config(business)

        # Direct mode → QR points straight to Google, zero Mi Rubro in the path
        if config.effective_mode == ReviewMode.DIRECT and config.redirect_url:
            target_url = config.redirect_url
        else:
            target_url = _build_review_landing_url(business.slug)

        qr_svg = build_qr_svg(target_url)

        return Response({
            'slug': business.slug,
            'public_url': target_url,
            'qr_svg': qr_svg,
            'effective_mode': config.effective_mode,
            'generated_at': timezone.now(),
        })


class ReviewListView(APIView):
    """
    GET /api/v1/reviews/  — list internal reviews for the business
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'manage_reviews',
    }

    def get(self, request):
        business = getattr(request, 'business')
        qs = Review.objects.filter(business=business)

        # Optional filters
        rating = request.query_params.get('rating')
        if rating is not None:
            try:
                qs = qs.filter(rating=int(rating))
            except (ValueError, TypeError):
                pass

        rating_min = request.query_params.get('rating_min')
        if rating_min is not None:
            try:
                qs = qs.filter(rating__gte=int(rating_min))
            except (ValueError, TypeError):
                pass

        rating_max = request.query_params.get('rating_max')
        if rating_max is not None:
            try:
                qs = qs.filter(rating__lte=int(rating_max))
            except (ValueError, TypeError):
                pass

        review_status = request.query_params.get('status')
        if review_status:
            qs = qs.filter(status=review_status)

        serializer = ReviewSerializer(qs[:100], many=True)
        return Response(serializer.data)


class ReviewDetailView(APIView):
    """
    PATCH /api/v1/reviews/<uuid:id>/  — update review status
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'PATCH': 'manage_reviews',
    }

    def patch(self, request, id):
        business = getattr(request, 'business')
        review = get_object_or_404(Review, id=id, business=business)
        old_status = review.status
        serializer = ReviewStatusUpdateSerializer(
            data=request.data,
            context={'current_status': review.status},
        )
        serializer.is_valid(raise_exception=True)
        review.status = serializer.validated_data['status']
        review.save(update_fields=['status'])
        invalidate_review_stats_cache(business.id)
        logger.info(
            "[Reviews] Status changed business=%s review=%s %s→%s",
            business.id, review.id, old_status, review.status,
        )
        return Response(ReviewSerializer(review).data)


# ── Stats cache ────────────────────────────────────────────────────────────
_STATS_CACHE_PREFIX = 'review_stats:'
_STATS_CACHE_TTL = 300  # 5 minutes


def _stats_cache_key(business_id: int) -> str:
    return f"{_STATS_CACHE_PREFIX}{business_id}"


def invalidate_review_stats_cache(business_id: int) -> None:
    """Delete cached stats for a business so the next GET recomputes."""
    cache.delete(_stats_cache_key(business_id))


class ReviewStatsView(APIView):
    """
    GET /api/v1/reviews/stats/  — analytics overview for the business.

    Metrics:
      - total_reviews, average_rating, total_visits, conversion_rate
      - positive/negative counts and rates (uses config.redirect_threshold)
      - status breakdown and resolution_rate (resolved / total_reviews)
      - rating_distribution, status_distribution
      - daily_trend (30 days), reviews_last_7_days, reviews_last_30_days
      - visits_last_7_days, visits_last_30_days
      - recent_reviews (latest 5)
      - redirect_threshold, effective_mode (config context)

    Cached per business for 5 minutes; invalidated on review create / status update.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'manage_reviews',
    }

    def get(self, request):
        business = getattr(request, 'business')
        ck = _stats_cache_key(business.id)
        cached = cache.get(ck)
        if cached is not None:
            logger.debug("[Reviews] Stats cache hit business=%s", business.id)
            return Response(cached)

        logger.debug("[Reviews] Stats cache miss business=%s — recomputing", business.id)
        payload = self._compute_stats(business)
        cache.set(ck, payload, _STATS_CACHE_TTL)
        return Response(payload)

    @staticmethod
    def _compute_stats(business) -> dict:
        now = timezone.now()
        config = _ensure_review_config(business)
        threshold = config.redirect_threshold

        reviews = Review.objects.filter(business=business)
        total_reviews = reviews.count()

        # Aggregates --------------------------------------------------------
        avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0

        positive_reviews = reviews.filter(rating__gte=threshold).count()
        negative_reviews = reviews.filter(rating__lt=threshold).count()

        # Status counts (single query) -------------------------------------
        status_qs = (
            reviews.values_list('status')
            .annotate(cnt=Count('id'))
        )
        status_counts: dict[str, int] = {row[0]: row[1] for row in status_qs}

        new_reviews = status_counts.get('new', 0)
        contacted_reviews = status_counts.get('contacted', 0)
        resolved_reviews = status_counts.get('resolved', 0)

        # Rating distribution (single query) --------------------------------
        rating_qs = (
            reviews.values_list('rating')
            .annotate(cnt=Count('id'))
        )
        rating_counts: dict[int, int] = {row[0]: row[1] for row in rating_qs}

        # Visits & conversion -----------------------------------------------
        visits = ReviewVisit.objects.filter(business=business)
        total_visits = visits.count()
        conversion_rate = (
            round(total_reviews / total_visits * 100, 1)
            if total_visits > 0
            else 0
        )

        # Resolution rate ---------------------------------------------------
        resolution_rate = (
            round(resolved_reviews / total_reviews * 100, 1)
            if total_reviews > 0
            else 0
        )

        # Positive / negative rates -----------------------------------------
        positive_rate = (
            round(positive_reviews / total_reviews * 100, 1)
            if total_reviews > 0
            else 0
        )
        negative_rate = (
            round(negative_reviews / total_reviews * 100, 1)
            if total_reviews > 0
            else 0
        )

        # Time-window counts ------------------------------------------------
        cutoff_7 = now - timedelta(days=7)
        cutoff_30 = now - timedelta(days=30)

        reviews_last_7_days = reviews.filter(created_at__gte=cutoff_7).count()
        reviews_last_30_days = reviews.filter(created_at__gte=cutoff_30).count()
        visits_last_7_days = visits.filter(created_at__gte=cutoff_7).count()
        visits_last_30_days = visits.filter(created_at__gte=cutoff_30).count()

        # Daily trend (last 30 days) ----------------------------------------
        trend_qs = (
            reviews.filter(created_at__gte=cutoff_30)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
        )
        trend_map: dict[date, int] = {row['day']: row['count'] for row in trend_qs}

        daily_trend: list[dict] = []
        for i in range(30):
            d = (now - timedelta(days=29 - i)).date()
            daily_trend.append({'date': d.isoformat(), 'count': trend_map.get(d, 0)})

        # Recent reviews (last 5) -------------------------------------------
        recent_reviews = ReviewSerializer(reviews[:5], many=True).data

        return {
            'total_reviews': total_reviews,
            'average_rating': round(float(avg_rating), 1),
            'total_visits': total_visits,
            'conversion_rate': conversion_rate,
            'positive_reviews': positive_reviews,
            'negative_reviews': negative_reviews,
            'positive_rate': positive_rate,
            'negative_rate': negative_rate,
            'new_reviews': new_reviews,
            'contacted_reviews': contacted_reviews,
            'resolved_reviews': resolved_reviews,
            'resolution_rate': resolution_rate,
            'rating_distribution': {
                str(i): rating_counts.get(i, 0) for i in range(1, 6)
            },
            'status_distribution': {
                s: status_counts.get(s, 0)
                for s in ['new', 'read', 'contacted', 'resolved']
            },
            'recent_reviews': recent_reviews,
            'reviews_last_7_days': reviews_last_7_days,
            'reviews_last_30_days': reviews_last_30_days,
            'visits_last_7_days': visits_last_7_days,
            'visits_last_30_days': visits_last_30_days,
            'daily_trend': daily_trend,
            'redirect_threshold': threshold,
            'effective_mode': config.effective_mode,
        }


class ActivateTrialView(APIView):
    """
    POST /api/v1/reviews/trial/activate/
    Starts the 7-day smart-filter trial for Base-plan businesses.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'POST': 'manage_reviews',
    }

    TRIAL_DURATION = timedelta(days=7)

    def post(self, request):
        business = getattr(request, 'business')

        if is_reviews_pro(business):
            logger.info("[Reviews] Trial rejected business=%s reason=already_pro", business.id)
            return Response(
                {'detail': 'Tu plan Pro ya incluye el filtro inteligente.'},
                status=status.HTTP_409_CONFLICT,
            )

        if not trial_available(business):
            logger.info("[Reviews] Trial rejected business=%s reason=already_used", business.id)
            return Response(
                {'detail': 'El período de prueba ya fue utilizado.'},
                status=status.HTTP_409_CONFLICT,
            )

        config = _ensure_review_config(business)

        config.trial_used = True
        config.trial_ends_at = timezone.now() + self.TRIAL_DURATION
        config.mode = ReviewMode.SMART_FILTER
        config.save(update_fields=['trial_used', 'trial_ends_at', 'mode', 'updated_at'])

        logger.info(
            "[Reviews] Trial activated business=%s ends_at=%s",
            business.id, config.trial_ends_at.isoformat(),
        )

        serializer = ReviewConfigSerializer(config)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Public views (no authentication)
# ---------------------------------------------------------------------------

DEDUP_WINDOW = timedelta(minutes=10)
VISIT_DEDUP_WINDOW = timedelta(minutes=5)

# Common bot User-Agent substrings to exclude from visit tracking.
_BOT_UA_FRAGMENTS = (
    'bot', 'crawl', 'spider', 'slurp', 'facebookexternalhit',
    'whatsapp', 'telegrambot', 'twitterbot', 'linkedinbot',
    'preview', 'fetch', 'headless',
)


class PublicReviewLandingView(APIView):
    """
    GET /api/v1/reviews/public/<slug>/
    Returns public config needed for the review landing page.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'public_reviews'

    def get(self, request, slug):
        from apps.business.models import Business

        business = get_object_or_404(Business, slug=slug)
        if business.status not in PUBLISHABLE_STATUSES:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            config = business.review_config
        except ReviewConfig.DoesNotExist:
            logger.warning("[Reviews] Landing 404 slug=%s reason=no_config", slug)
            return Response(
                {'detail': 'Reseñas no configuradas para este negocio.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not config.enabled:
            logger.warning("[Reviews] Landing 404 slug=%s reason=disabled", slug)
            return Response(
                {'detail': 'Reseñas no configuradas para este negocio.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not reviews_allowed(business):
            logger.warning("[Reviews] Landing 404 slug=%s reason=plan_not_allowed", slug)
            return Response(
                {'detail': 'Reseñas no configuradas para este negocio.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Track visit for conversion analytics (skip bots, dedup by IP).
        ua = (request.META.get('HTTP_USER_AGENT') or '').lower()
        is_bot = any(frag in ua for frag in _BOT_UA_FRAGMENTS)
        if not is_bot:
            ip_hash = hash_ip(request)
            cutoff = timezone.now() - VISIT_DEDUP_WINDOW
            if not ReviewVisit.objects.filter(
                business=business, ip_hash=ip_hash, created_at__gte=cutoff,
            ).exists():
                ReviewVisit.objects.create(business=business, ip_hash=ip_hash)

        serializer = PublicReviewConfigSerializer(config, context={'request': request})
        return Response(serializer.data)


class PublicReviewSubmitView(APIView):
    """
    POST /api/v1/reviews/public/<slug>/submit/
    Handles the hybrid review flow:
      - rating >= threshold → redirect action
      - rating < threshold  → creates internal Review
    """
    permission_classes = [AllowAny]
    throttle_classes = [ReviewSubmitThrottle]

    def post(self, request, slug):
        from apps.business.models import Business

        business = get_object_or_404(Business, slug=slug)

        if business.status not in PUBLISHABLE_STATUSES:
            return Response(status=status.HTTP_404_NOT_FOUND)

        try:
            config = business.review_config
        except ReviewConfig.DoesNotExist:
            logger.warning("[Reviews] Submit 404 slug=%s reason=no_config", slug)
            return Response(
                {'detail': 'Reseñas no configuradas para este negocio.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not config.enabled:
            logger.warning("[Reviews] Submit 403 slug=%s reason=disabled", slug)
            return Response(
                {'detail': 'Reseñas no habilitadas.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not reviews_allowed(business):
            logger.warning("[Reviews] Submit 403 slug=%s reason=plan_not_allowed", slug)
            return Response(
                {'detail': 'Reseñas no disponibles para este negocio.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ReviewSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        rating = data['rating']

        # Defense-in-depth: direct mode always redirects, no Review created
        if config.effective_mode == 'direct':
            logger.info(
                "[Reviews] Submit redirect slug=%s rating=%s mode=direct",
                slug, rating,
            )
            return Response({
                'action': 'redirect',
                'redirect_url': config.redirect_url,
                'message': config.thank_you_message,
            })

        ip = hash_ip(request)

        # Deduplication: same ip_hash + business within DEDUP_WINDOW
        cutoff = timezone.now() - DEDUP_WINDOW
        if Review.objects.filter(business=business, ip_hash=ip, created_at__gte=cutoff).exists():
            logger.info("[Reviews] Submit dedup slug=%s", slug)
            return Response(
                {'detail': 'Ya enviaste una reseña recientemente. Intentá más tarde.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # High rating → redirect to external review platform
        if rating >= config.redirect_threshold:
            logger.info(
                "[Reviews] Submit redirect slug=%s rating=%s threshold=%s",
                slug, rating, config.redirect_threshold,
            )
            return Response({
                'action': 'redirect',
                'redirect_url': config.redirect_url,
                'message': config.thank_you_message,
            })

        # Low rating → store internal feedback
        review = Review.objects.create(
            business=business,
            rating=rating,
            comment=data.get('comment', ''),
            contact_info=data.get('contact_info', ''),
            source=data.get('source', 'qr'),
            ip_hash=ip,
        )
        logger.info(
            "[Reviews] Submit stored slug=%s review=%s rating=%s source=%s",
            slug, review.id, rating, review.source,
        )

        return Response({
            'action': 'submitted',
            'message': config.thank_you_message,
        }, status=status.HTTP_201_CREATED)

from __future__ import annotations

import io
import logging
from datetime import date, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from common.ip import hash_ip
from common.qr import build_qr_svg

from .entitlements import (
    is_reviews_pro,
    print_posters_allowed,
    reviews_allowed,
    smart_filter_allowed,
    trial_available,
)
from .models import Review, ReviewConfig, ReviewMode, ReviewQrPosterDesign, ReviewVisit
from .qr_poster_design_serializer import QrPosterDesignSerializer
from .qr_poster_serializer import GenerateQrPosterSerializer
from .qr_posters import render_qr_poster_pdf
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


class HasPrintPostersCapability(BasePermission):
    """
    Plan/bundle gate for QR poster (Carteles) endpoints.

    Allows standalone Pro (``qr_reviews_pro``) and bundle plans that include
    Carteles (Restaurante Inteligente → ``plus``). Membership and role gating
    (``manage_reviews``) are enforced separately by ``HasBusinessMembership``
    and ``HasPermission``.
    """
    message = {
        'code': 'plan_entitlement_required',
        'entitlement': 'qr_reviews.print_posters',
        'reason_code': 'plan_entitlement_required',
        'message': 'Tu plan actual no incluye Carteles QR.',
    }

    def has_permission(self, request, view) -> bool:
        business = getattr(request, 'business', None)
        if business is None:
            return False
        return print_posters_allowed(business)


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
        # PR-A: advanced status management is Pro-only. Base can read feedback
        # but cannot change statuses (new / read / contacted / resolved).
        if not is_reviews_pro(business):
            return Response(
                {'detail': 'La gestión de estados de feedback requiere QR de Reseñas Pro.'},
                status=status.HTTP_403_FORBIDDEN,
            )
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
            return Response(self._filter_for_plan(cached, business))

        logger.debug("[Reviews] Stats cache miss business=%s — recomputing", business.id)
        payload = self._compute_stats(business)
        cache.set(ck, payload, _STATS_CACHE_TTL)
        return Response(self._filter_for_plan(payload, business))

    # PR-A: fields gated behind QR de Reseñas Pro.
    _PRO_ONLY_STATS_FIELDS = frozenset({
        'conversion_rate',
        'resolution_rate',
        'positive_rate',
        'negative_rate',
        'contacted_reviews',
        'resolved_reviews',
        'status_distribution',
        'reviews_last_7_days',
        'reviews_last_30_days',
        'visits_last_7_days',
        'visits_last_30_days',
        'daily_trend',
    })

    @classmethod
    def _filter_for_plan(cls, payload: dict, business) -> dict:
        """Strip Pro-only metrics from the cached payload for non-Pro businesses."""
        if is_reviews_pro(business):
            return payload
        return {k: v for k, v in payload.items() if k not in cls._PRO_ONLY_STATS_FIELDS}

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

    Legacy endpoint: starts the 7-day smart-filter trial.

    NOTE: Smart-filter is now included in the Base tier. This endpoint is
    preserved for backwards-compatibility but will return 409 because any
    active reviews subscription already grants the capability.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'POST': 'manage_reviews',
    }

    TRIAL_DURATION = timedelta(days=7)

    def post(self, request):
        business = getattr(request, 'business')

        # Smart-filter is part of Base tier — no trial needed when allowed.
        from .entitlements import smart_filter_allowed
        if smart_filter_allowed(business):
            logger.info(
                "[Reviews] Trial rejected business=%s reason=already_allowed",
                business.id,
            )
            return Response(
                {'detail': 'Tu plan ya incluye el filtro inteligente.'},
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


# ---------------------------------------------------------------------------
# Carteles QR PRO
# ---------------------------------------------------------------------------

class GenerateQrPosterPdfView(APIView):
    """
    POST /api/v1/reviews/qr-posters/generate-pdf/

    Genera un cartel QR en PDF para QR de Reseñas PRO.

    Acepta application/json (solo color de fondo) o multipart/form-data
    (con campo background_image para imagen de fondo).

    Requiere entitlement 'qr_reviews.print_posters' (plan qr_reviews_pro).
    Usuarios con plan base (qr_reviews / qr_reviews_base) reciben 403.

    Response exitosa: application/pdf con el cartel listo para imprimir.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission, HasPrintPostersCapability]
    permission_map = {
        'POST': 'manage_reviews',
    }

    _MAX_BG_IMAGE_BYTES = 10 * 1024 * 1024          # 10 MB
    _ALLOWED_IMAGE_FORMATS = frozenset({'JPEG', 'PNG'})

    def post(self, request):
        business = request.business

        if not getattr(business, 'slug', None):
            return Response(
                {
                    'code': 'no_slug',
                    'message': 'El negocio no tiene un slug configurado.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = GenerateQrPosterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        background_mode = serializer.validated_data.get('background_mode', 'color')
        background_image_bytes: bytes | None = None

        if background_mode == 'image':
            bg_file = request.FILES.get('background_image')
            if bg_file is None:
                return Response(
                    {'background_image': 'Se requiere una imagen cuando background_mode es "image".'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            raw = bg_file.read()

            if len(raw) > self._MAX_BG_IMAGE_BYTES:
                return Response(
                    {'background_image': 'La imagen no puede superar 10 MB.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                from PIL import Image as _PilImage  # noqa: PLC0415  (Pillow — dep de ReportLab)
                img = _PilImage.open(io.BytesIO(raw))
                img_format = img.format
            except Exception:
                return Response(
                    {'background_image': 'El archivo no es una imagen válida.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if img_format not in self._ALLOWED_IMAGE_FORMATS:
                return Response(
                    {'background_image': f'Solo se aceptan JPG o PNG. Formato recibido: {img_format}.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            background_image_bytes = raw

        try:
            pdf_bytes = render_qr_poster_pdf(
                serializer.validated_data, business, background_image_bytes,
            )
        except Exception:
            logger.exception(
                'GenerateQrPosterPdfView: error generating PDF (business=%s)',
                business.pk,
            )
            return Response(
                {
                    'code': 'pdf_generation_error',
                    'message': 'No se pudo generar el PDF. Intentá nuevamente.',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="cartel-qr-resenas.pdf"'
        return response


# ---------------------------------------------------------------------------
# Historial de diseños QR PRO
# ---------------------------------------------------------------------------

_MAX_DESIGN_IMAGE_BYTES = 10 * 1024 * 1024       # 10 MB
_ALLOWED_DESIGN_IMAGE_FORMATS = frozenset({'JPEG', 'PNG'})


def _validate_design_image(bg_file) -> bytes:
    """
    Validates an uploaded background image file.
    Returns raw bytes if valid.
    Raises rest_framework.exceptions.ValidationError on failure.
    """
    from rest_framework.exceptions import ValidationError  # noqa: PLC0415

    raw = bg_file.read()

    if len(raw) > _MAX_DESIGN_IMAGE_BYTES:
        raise ValidationError({'background_image': 'La imagen no puede superar 10 MB.'})

    try:
        from PIL import Image as _PilImage  # noqa: PLC0415
        img = _PilImage.open(io.BytesIO(raw))
        img_format = img.format
    except Exception:
        raise ValidationError({'background_image': 'El archivo no es una imagen válida.'})

    if img_format not in _ALLOWED_DESIGN_IMAGE_FORMATS:
        raise ValidationError(
            {'background_image': f'Solo se aceptan JPG o PNG. Formato recibido: {img_format}.'}
        )

    return raw


class QrPosterDesignListCreateView(APIView):
    """
    GET  /api/v1/reviews/qr-posters/designs/  — list saved designs for the business.
    POST /api/v1/reviews/qr-posters/designs/  — save a new design (max 5 per business).

    Both methods require entitlement 'qr_reviews.print_posters' (plan qr_reviews_pro).

    POST accepts multipart/form-data when background_mode=image (field: background_image).
    Otherwise accepts application/json.
    The `payload` field must be a valid JSON object matching the cartel configuration.
    """

    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission, HasPrintPostersCapability]
    permission_map = {
        'GET': 'manage_reviews',
        'POST': 'manage_reviews',
    }

    def get(self, request):
        business = request.business
        designs = ReviewQrPosterDesign.objects.filter(business=business)
        serializer = QrPosterDesignSerializer(designs, many=True, context={'request': request})
        return Response({
            'count': designs.count(),
            'limit': ReviewQrPosterDesign.DESIGN_LIMIT,
            'results': serializer.data,
        })

    def post(self, request):
        business = request.business

        # Enforce limit before touching serializer or files
        count = ReviewQrPosterDesign.objects.filter(business=business).count()
        if count >= ReviewQrPosterDesign.DESIGN_LIMIT:
            return Response(
                {
                    'code': 'design_limit_reached',
                    'message': 'Podés guardar hasta 5 diseños.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = QrPosterDesignSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        payload = serializer.validated_data['payload']
        background_mode = payload.get('background_mode', 'color')

        design = ReviewQrPosterDesign(
            business=business,
            name=serializer.validated_data['name'],
            payload=payload,
            created_by=request.user,
            updated_by=request.user,
        )

        if background_mode == 'image':
            bg_file = request.FILES.get('background_image')
            if bg_file is None:
                return Response(
                    {'background_image': 'Se requiere una imagen cuando background_mode es "image".'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            from rest_framework.exceptions import ValidationError as DRFValidationError  # noqa: PLC0415
            try:
                _validate_design_image(bg_file)
            except DRFValidationError as exc:
                return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
            bg_file.seek(0)
            design.background_image.save(bg_file.name, bg_file, save=False)

        design.save()

        logger.info(
            '[Reviews] PosterDesign created business=%s id=%s name=%r',
            business.id, design.id, design.name,
        )
        return Response(QrPosterDesignSerializer(design, context={'request': request}).data, status=status.HTTP_201_CREATED)


class QrPosterDesignDetailView(APIView):
    """
    GET    /api/v1/reviews/qr-posters/designs/<uuid:id>/  — retrieve a design.
    PATCH  /api/v1/reviews/qr-posters/designs/<uuid:id>/  — partial update.
    DELETE /api/v1/reviews/qr-posters/designs/<uuid:id>/  — delete (also removes image file).

    Tenant isolation: queries always filter by business=request.business.
    """

    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission, HasPrintPostersCapability]
    permission_map = {
        'GET': 'manage_reviews',
        'PATCH': 'manage_reviews',
        'DELETE': 'manage_reviews',
    }

    def _get_design(self, request, id):
        return get_object_or_404(ReviewQrPosterDesign, id=id, business=request.business)

    def get(self, request, id):
        design = self._get_design(request, id)
        return Response(QrPosterDesignSerializer(design, context={'request': request}).data)

    def patch(self, request, id):
        design = self._get_design(request, id)

        serializer = QrPosterDesignSerializer(design, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Resolve the updated payload (merge partial with existing)
        existing_payload = design.payload or {}
        new_payload_data = serializer.validated_data.get('payload')
        if new_payload_data is not None:
            payload = new_payload_data
        else:
            payload = existing_payload

        background_mode = payload.get('background_mode', existing_payload.get('background_mode', 'color'))
        from rest_framework.exceptions import ValidationError as DRFValidationError  # noqa: PLC0415

        if background_mode == 'color':
            # Switching to color mode — clean up any stored image
            if design.background_image:
                design.background_image.delete(save=False)
                design.background_image = None
        elif background_mode == 'image':
            bg_file = request.FILES.get('background_image')
            if bg_file is not None:
                # Replace existing image with new one
                try:
                    _validate_design_image(bg_file)
                except DRFValidationError as exc:
                    return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
                if design.background_image:
                    design.background_image.delete(save=False)
                    design.background_image = None
                bg_file.seek(0)
                design.background_image.save(bg_file.name, bg_file, save=False)
            elif not design.background_image:
                # No new file and no existing image — invalid state
                return Response(
                    {'background_image': 'Se requiere una imagen cuando background_mode es "image".'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # else: bg_file is None but design.background_image exists → keep as-is

        if 'name' in serializer.validated_data:
            design.name = serializer.validated_data['name']
        if new_payload_data is not None:
            design.payload = payload
        design.updated_by = request.user
        design.save()

        logger.info(
            '[Reviews] PosterDesign updated business=%s id=%s',
            request.business.id, design.id,
        )
        return Response(QrPosterDesignSerializer(design, context={'request': request}).data)

    def delete(self, request, id):
        design = self._get_design(request, id)

        if design.background_image:
            design.background_image.delete(save=False)

        design.delete()

        logger.info(
            '[Reviews] PosterDesign deleted business=%s id=%s',
            request.business.id, id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class GenerateQrPosterPdfFromDesignView(APIView):
    """
    POST /api/v1/reviews/qr-posters/designs/<uuid:id>/generate-pdf/

    Genera el PDF de un Cartel QR usando un diseño guardado.
    Si el diseño tiene imagen de fondo persistida en storage, la usa directamente
    — el usuario no necesita volver a subir el archivo.

    Tenant isolation: solo accede al diseño si pertenece al business del request.
    Requiere entitlement 'qr_reviews.print_posters'.
    """

    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission, HasPrintPostersCapability]
    permission_map = {
        'POST': 'manage_reviews',
    }

    def post(self, request, id):
        business = request.business

        if not getattr(business, 'slug', None):
            return Response(
                {
                    'code': 'no_slug',
                    'message': 'El negocio no tiene un slug configurado.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        design = get_object_or_404(ReviewQrPosterDesign, id=id, business=business)

        payload = design.payload or {}
        background_mode = payload.get('background_mode', 'color')
        background_image_bytes: bytes | None = None

        if background_mode == 'image':
            if not design.background_image:
                return Response(
                    {
                        'code': 'missing_design_background_image',
                        'message': 'Este diseño no tiene una imagen de fondo guardada.',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            logger.info(
                'GenerateQrPosterPdfFromDesignView: reading bg image '
                'design=%s name=%s url=%s storage=%s',
                design.id,
                getattr(design.background_image, 'name', None),
                getattr(design.background_image, 'url', None),
                design.background_image.storage.__class__.__name__,
            )
            try:
                design.background_image.open('rb')
                background_image_bytes = design.background_image.read()
                design.background_image.close()
            except Exception:
                logger.exception(
                    'GenerateQrPosterPdfFromDesignView: failed to read bg image '
                    '(business=%s design=%s name=%s)',
                    business.pk, design.id,
                    getattr(design.background_image, 'name', None),
                )
                return Response(
                    {
                        'code': 'background_image_read_error',
                        'message': 'No se pudo leer la imagen de fondo del diseño.',
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        try:
            pdf_bytes = render_qr_poster_pdf(payload, business, background_image_bytes)
        except Exception:
            logger.exception(
                'GenerateQrPosterPdfFromDesignView: error generating PDF '
                '(business=%s design=%s)',
                business.pk, id,
            )
            return Response(
                {
                    'code': 'pdf_generation_error',
                    'message': 'No se pudo generar el PDF. Intentá nuevamente.',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="cartel-qr-resenas.pdf"'
        return response

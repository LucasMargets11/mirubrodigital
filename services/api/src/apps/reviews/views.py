from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from common.ip import hash_ip
from common.qr import build_qr_svg

from .entitlements import reviews_allowed
from .models import Review, ReviewConfig, ReviewVisit
from .serializers import (
    PublicReviewConfigSerializer,
    ReviewConfigSerializer,
    ReviewSerializer,
    ReviewStatusUpdateSerializer,
    ReviewSubmitSerializer,
)


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
        return Response(serializer.data)


class ReviewQRCodeView(APIView):
    """
    GET /api/v1/reviews/qr/  — generate QR for /r/<slug>/
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'manage_reviews',
    }

    def get(self, request):
        business = getattr(request, 'business')

        if not reviews_allowed(business):
            return Response(
                {'detail': 'Reseñas no disponibles en tu plan actual.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not business.slug:
            return Response(
                {'detail': 'El negocio no tiene un slug configurado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        public_url = _build_review_landing_url(business.slug)
        qr_svg = build_qr_svg(public_url)

        return Response({
            'slug': business.slug,
            'public_url': public_url,
            'qr_svg': qr_svg,
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
        serializer = ReviewStatusUpdateSerializer(
            data=request.data,
            context={'current_status': review.status},
        )
        serializer.is_valid(raise_exception=True)
        review.status = serializer.validated_data['status']
        review.save(update_fields=['status'])
        return Response(ReviewSerializer(review).data)


class ReviewStatsView(APIView):
    """
    GET /api/v1/reviews/stats/  — analytics overview for the business.

    Metrics:
      - total_reviews, average_rating, total_visits, conversion_rate
      - positive/negative counts and rates (positive = rating >= 4)
      - status breakdown and resolution_rate (resolved / total_reviews)
      - rating_distribution, status_distribution
      - reviews_last_7_days, reviews_last_30_days
      - recent_reviews (latest 5)
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'manage_reviews',
    }

    def get(self, request):
        business = getattr(request, 'business')
        now = timezone.now()

        reviews = Review.objects.filter(business=business)
        total_reviews = reviews.count()

        # Aggregates --------------------------------------------------------
        avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0

        positive_reviews = reviews.filter(rating__gte=4).count()
        negative_reviews = reviews.filter(rating__lte=3).count()

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
        total_visits = ReviewVisit.objects.filter(business=business).count()
        conversion_rate = (
            round(total_reviews / total_visits * 100, 1)
            if total_visits > 0
            else 0
        )

        # Resolution rate: resolved / total_reviews -------------------------
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

        # Trend --------------------------------------------------------------
        reviews_last_7_days = reviews.filter(
            created_at__gte=now - timedelta(days=7),
        ).count()
        reviews_last_30_days = reviews.filter(
            created_at__gte=now - timedelta(days=30),
        ).count()

        # Recent reviews (last 5) -------------------------------------------
        recent_reviews = ReviewSerializer(reviews[:5], many=True).data

        return Response({
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
        })


# ---------------------------------------------------------------------------
# Public views (no authentication)
# ---------------------------------------------------------------------------

DEDUP_WINDOW = timedelta(minutes=10)


class PublicReviewLandingView(APIView):
    """
    GET /api/v1/reviews/public/<slug>/
    Returns public config needed for the review landing page.
    """
    permission_classes = [AllowAny]

    def get(self, request, slug):
        from apps.business.models import Business

        business = get_object_or_404(Business, slug=slug)
        try:
            config = business.review_config
        except ReviewConfig.DoesNotExist:
            return Response(
                {'detail': 'Reseñas no configuradas para este negocio.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not config.enabled:
            return Response(
                {'detail': 'Reseñas no configuradas para este negocio.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not reviews_allowed(business):
            return Response(
                {'detail': 'Reseñas no configuradas para este negocio.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Track visit for conversion analytics
        ReviewVisit.objects.create(business=business)

        serializer = PublicReviewConfigSerializer(config)
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

        try:
            config = business.review_config
        except ReviewConfig.DoesNotExist:
            return Response(
                {'detail': 'Reseñas no configuradas para este negocio.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not config.enabled:
            return Response(
                {'detail': 'Reseñas no habilitadas.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not reviews_allowed(business):
            return Response(
                {'detail': 'Reseñas no disponibles para este negocio.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ReviewSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        rating = data['rating']

        ip = hash_ip(request)

        # Deduplication: same ip_hash + business within DEDUP_WINDOW
        cutoff = timezone.now() - DEDUP_WINDOW
        if Review.objects.filter(business=business, ip_hash=ip, created_at__gte=cutoff).exists():
            return Response(
                {'detail': 'Ya enviaste una reseña recientemente. Intentá más tarde.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # High rating → redirect to external review platform
        if rating >= config.redirect_threshold:
            return Response({
                'action': 'redirect',
                'redirect_url': config.redirect_url,
                'message': config.thank_you_message,
            })

        # Low rating → store internal feedback
        Review.objects.create(
            business=business,
            rating=rating,
            comment=data.get('comment', ''),
            contact_info=data.get('contact_info', ''),
            source=data.get('source', 'qr'),
            ip_hash=ip,
        )

        return Response({
            'action': 'submitted',
            'message': config.thank_you_message,
        }, status=status.HTTP_201_CREATED)

"""
Platform admin views — Promo Codes module.

Exposes PromoCode and PromoCodeRedemption entities for the internal backoffice.
"""
import math

from django.db.models import Count, Q
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.platform_permissions import IsPlatformStaff
from apps.accounts.platform_audit import log_platform_action
from .models import PromoCode, PromoCodeRedemption

PAGE_SIZE = 25


# ══════════════════════════════════════════════════════════════════════════════
# Serializers
# ══════════════════════════════════════════════════════════════════════════════

class PromoCodeListSerializer(serializers.ModelSerializer):
    redemptions_count = serializers.IntegerField(read_only=True)
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = PromoCode
        fields = [
            'id', 'code', 'name', 'description',
            'discount_type', 'discount_value', 'duration_cycles',
            'applies_to_plan_codes', 'applies_to_service', 'applies_to_billing_periods',
            'starts_at', 'ends_at',
            'max_redemptions', 'max_redemptions_per_business',
            'active',
            'redemptions_count',
            'created_by_email',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'redemptions_count', 'created_by_email']

    def get_created_by_email(self, obj):
        if obj.created_by_id:
            return obj.created_by.email
        return None


class PromoCodeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromoCode
        fields = [
            'code', 'name', 'description',
            'discount_type', 'discount_value', 'duration_cycles',
            'applies_to_plan_codes', 'applies_to_service', 'applies_to_billing_periods',
            'starts_at', 'ends_at',
            'max_redemptions', 'max_redemptions_per_business',
            'active',
        ]

    def validate_code(self, value):
        return value.strip().upper()

    def validate_duration_cycles(self, value):
        if value < 1:
            raise serializers.ValidationError('duration_cycles must be at least 1.')
        return value

    def validate_applies_to_plan_codes(self, value):
        if not value or not isinstance(value, list) or len(value) == 0:
            raise serializers.ValidationError('applies_to_plan_codes must contain at least one plan code.')
        return value

    def validate_applies_to_billing_periods(self, value):
        if value:
            allowed = {'monthly'}
            invalid = set(value) - allowed
            if invalid:
                raise serializers.ValidationError(
                    f"Only 'monthly' is supported for billing periods. Invalid: {sorted(invalid)}"
                )
        return value

    def validate_discount_value(self, value):
        if value <= 0:
            raise serializers.ValidationError('discount_value must be greater than 0.')
        return value


class PromoCodePatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromoCode
        fields = [
            'name', 'description',
            'discount_type', 'discount_value', 'duration_cycles',
            'applies_to_plan_codes', 'applies_to_service', 'applies_to_billing_periods',
            'starts_at', 'ends_at',
            'max_redemptions', 'max_redemptions_per_business',
            'active',
        ]

    def validate_duration_cycles(self, value):
        if value < 1:
            raise serializers.ValidationError('duration_cycles must be at least 1.')
        return value

    def validate_applies_to_plan_codes(self, value):
        if value is not None:
            if not isinstance(value, list) or len(value) == 0:
                raise serializers.ValidationError('applies_to_plan_codes must contain at least one plan code.')
        return value

    def validate_applies_to_billing_periods(self, value):
        if value:
            allowed = {'monthly'}
            invalid = set(value) - allowed
            if invalid:
                raise serializers.ValidationError(
                    f"Only 'monthly' is supported for billing periods. Invalid: {sorted(invalid)}"
                )
        return value

    def validate_discount_value(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError('discount_value must be greater than 0.')
        return value


class PromoCodeRedemptionSerializer(serializers.ModelSerializer):
    business_name = serializers.SerializerMethodField()
    business_id   = serializers.IntegerField(source='business.id', read_only=True)
    user_email    = serializers.SerializerMethodField()

    class Meta:
        model = PromoCodeRedemption
        fields = [
            'id',
            'business_id', 'business_name',
            'user_email',
            'status',
            'original_amount', 'discounted_amount',
            'cycles_total', 'cycles_used',
            'price_restored', 'price_restored_at',
            'created_at', 'updated_at',
        ]

    def get_business_name(self, obj):
        return obj.business.name if obj.business_id else None

    def get_user_email(self, obj):
        if obj.user_id:
            return obj.user.email
        return None


# ══════════════════════════════════════════════════════════════════════════════
# AdminPromoCodeListCreateView
# ══════════════════════════════════════════════════════════════════════════════

class AdminPromoCodeListCreateView(APIView):
    """
    GET  /api/v1/platform-admin/promo-codes/       — paginated list
    POST /api/v1/platform-admin/promo-codes/       — create new promo code
    """
    permission_classes = [IsPlatformStaff]

    def get(self, request: Request) -> Response:
        qs = PromoCode.objects.annotate(
            redemptions_count=Count('redemptions', filter=Q(redemptions__status__in=['pending', 'active']))
        ).select_related('created_by').order_by('-created_at')

        # ── Filters ──────────────────────────────────────────────────────
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(code__icontains=search) | Q(name__icontains=search)
            )

        active_filter = request.query_params.get('active', '').strip()
        if active_filter == 'true':
            qs = qs.filter(active=True)
        elif active_filter == 'false':
            qs = qs.filter(active=False)

        # ── Pagination ────────────────────────────────────────────────────
        total = qs.count()
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        total_pages = max(1, math.ceil(total / PAGE_SIZE))
        offset = (page - 1) * PAGE_SIZE
        qs = qs[offset: offset + PAGE_SIZE]

        serializer = PromoCodeListSerializer(qs, many=True)
        return Response({
            'results': serializer.data,
            'total': total,
            'page': page,
            'page_size': PAGE_SIZE,
            'total_pages': total_pages,
        })

    def post(self, request: Request) -> Response:
        serializer = PromoCodeCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        promo = serializer.save(created_by=request.user)
        log_platform_action(
            action='promo_code_created',
            actor=request.user,
            entity_type='PromoCode',
            entity_id=str(promo.id),
            details={'code': promo.code},
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
        out = PromoCodeListSerializer(promo)
        return Response(out.data, status=status.HTTP_201_CREATED)


# ══════════════════════════════════════════════════════════════════════════════
# AdminPromoCodeDetailView
# ══════════════════════════════════════════════════════════════════════════════

class AdminPromoCodeDetailView(APIView):
    """
    GET   /api/v1/platform-admin/promo-codes/<promo_id>/  — detail
    PATCH /api/v1/platform-admin/promo-codes/<promo_id>/  — partial update
    """
    permission_classes = [IsPlatformStaff]

    def _get_promo(self, promo_id: int):
        try:
            return PromoCode.objects.select_related('created_by').get(pk=promo_id)
        except PromoCode.DoesNotExist:
            return None

    def get(self, request: Request, promo_id: int) -> Response:
        promo = self._get_promo(promo_id)
        if promo is None:
            return Response({'detail': 'Promo code not found.'}, status=status.HTTP_404_NOT_FOUND)
        promo.redemptions_count = promo.redemptions.filter(status__in=['pending', 'active']).count()
        serializer = PromoCodeListSerializer(promo)
        return Response(serializer.data)

    def patch(self, request: Request, promo_id: int) -> Response:
        promo = self._get_promo(promo_id)
        if promo is None:
            return Response({'detail': 'Promo code not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PromoCodePatchSerializer(promo, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        updated = serializer.save()
        log_platform_action(
            action='promo_code_updated',
            actor=request.user,
            entity_type='PromoCode',
            entity_id=str(updated.id),
            details={'fields': list(serializer.validated_data.keys())},
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
        updated.redemptions_count = updated.redemptions.filter(status__in=['pending', 'active']).count()
        out = PromoCodeListSerializer(updated)
        return Response(out.data)


# ══════════════════════════════════════════════════════════════════════════════
# AdminPromoCodeRedemptionsView
# ══════════════════════════════════════════════════════════════════════════════

class AdminPromoCodeRedemptionsView(APIView):
    """
    GET /api/v1/platform-admin/promo-codes/<promo_id>/redemptions/
    """
    permission_classes = [IsPlatformStaff]

    def get(self, request: Request, promo_id: int) -> Response:
        try:
            promo = PromoCode.objects.get(pk=promo_id)
        except PromoCode.DoesNotExist:
            return Response({'detail': 'Promo code not found.'}, status=status.HTTP_404_NOT_FOUND)

        qs = (
            PromoCodeRedemption.objects
            .filter(promo_code=promo)
            .select_related('business', 'user')
            .order_by('-created_at')
        )

        status_filter = request.query_params.get('status', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        total = qs.count()
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        total_pages = max(1, math.ceil(total / PAGE_SIZE))
        offset = (page - 1) * PAGE_SIZE
        qs = qs[offset: offset + PAGE_SIZE]

        serializer = PromoCodeRedemptionSerializer(qs, many=True)
        return Response({
            'results': serializer.data,
            'total': total,
            'page': page,
            'page_size': PAGE_SIZE,
            'total_pages': total_pages,
        })


# ══════════════════════════════════════════════════════════════════════════════
# AdminPromoCodeOptionsView
# ══════════════════════════════════════════════════════════════════════════════

_SERVICE_LABELS = {
    'gestion': 'Gestión Comercial',
    'menu_qr': 'Menú QR',
    'qr_reviews': 'Reseñas QR',
    'restaurante': 'Restaurante',
}


def _plan_service(code: str) -> str:
    """Infer canonical service slug from a Plan.code value."""
    if code.startswith('gestion_') or code == 'gestion':
        return 'gestion'
    if code.startswith('menu_qr_') or code == 'menu_qr':
        return 'menu_qr'
    if code.startswith('qr_reviews_') or code == 'qr_reviews':
        return 'qr_reviews'
    if code.startswith('restaurante_') or code.startswith('resto_'):
        return 'restaurante'
    return code.split('_')[0]


class AdminPromoCodeOptionsView(APIView):
    """
    GET /api/v1/platform-admin/promo-codes/options/

    Returns reference data for the promo-code creation form:
      - services:         distinct service slugs derived from active monthly plans
      - plans:            active monthly Plan records (code, label, service, price)
      - billing_periods:  MVP — only 'monthly'
      - discount_types:   percent / fixed_amount
    """
    permission_classes = [IsPlatformStaff]

    def get(self, request: Request) -> Response:
        from .models import Plan

        plans_qs = (
            Plan.objects
            .filter(plan_status='active', interval='monthly')
            .order_by('code')
        )

        plans = []
        seen_services: dict[str, str] = {}
        for p in plans_qs:
            svc = _plan_service(p.code)
            svc_label = _SERVICE_LABELS.get(svc, svc.replace('_', ' ').title())
            seen_services[svc] = svc_label
            plans.append({
                'code': p.code,
                'label': f'{svc_label} · {p.name}',
                'service': svc,
                'service_label': svc_label,
                'billing_period': p.interval,
                'price': str(p.price),
            })

        services = [
            {'value': svc, 'label': label}
            for svc, label in sorted(seen_services.items())
        ]

        return Response({
            'services': services,
            'plans': plans,
            'billing_periods': [{'value': 'monthly', 'label': 'Mensual'}],
            'discount_types': [
                {'value': 'percent', 'label': 'Porcentaje (%)'},
                {'value': 'fixed_amount', 'label': 'Monto fijo (ARS)'},
            ],
        })

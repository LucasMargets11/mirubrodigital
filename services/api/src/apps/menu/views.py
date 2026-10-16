from __future__ import annotations

import hashlib
import hmac
import io
import os
from urllib.parse import quote

import segno
from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, JSONParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from apps.billing.permissions import CheckFeatureAccess
from apps.business.service_policy import require_service
from rest_framework.throttling import ScopedRateThrottle
from .importer import MenuImportError, apply_menu_import, export_menu_to_workbook
from .qr_entitlements import resolve_menu_qr_flags, get_subscription_for_business
from apps.merchant_payments.services import (
    MerchantPaymentConnectionUnavailable,
    get_merchant_mp_client,
)
from .models import (
    MenuBrandingSettings,
    MenuCategory,
    MenuEngagementSettings,
    MenuLayoutBlock,
    MenuLayoutBlockCategory,
    MenuItem,
    PublicMenuConfig,
    TipTransaction,
    ensure_menu_branding,
    ensure_menu_engagement,
    ensure_public_menu_config,
)
from .serializers import (
    MenuCategorySerializer,
    MenuEngagementSettingsSerializer,
    MenuImportUploadSerializer,
    MenuLogoUploadSerializer,
    MenuItemSerializer,
    MenuItemWriteSerializer,
    MenuItemImageUploadSerializer,
    MenuLayoutBlockSerializer,
    MenuLayoutBlockReorderSerializer,
    MenuStructureCategorySerializer,
    PublicMenuConfigSerializer,
    PublicMenuCategorySerializer,
    PublicMenuLayoutBlockSerializer,
    MenuBrandingSettingsSerializer,
    TipCreatePreferenceSerializer,
    TipTransactionSerializer,
)

import logging
logger = logging.getLogger(__name__)

# Businesses with these statuses are visible on public pages.
# trialing/active/past_due keep the page up; everything else returns 404.
PUBLISHABLE_STATUSES = frozenset({'active', 'trialing', 'past_due'})


class MenuCategoryListCreateView(generics.ListCreateAPIView):
    serializer_class = MenuCategorySerializer
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'view_menu',
        'POST': 'manage_menu',
    }

    def get_queryset(self):
        business = getattr(self.request, 'business')
        return (
            MenuCategory.objects.filter(business=business)
            .select_related('product_category')
            .annotate(item_count=Count('items'))
            .order_by('position', 'name')
        )

    def perform_create(self, serializer):
        serializer.save(business=getattr(self.request, 'business'))


class MenuCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MenuCategorySerializer
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'view_menu',
        'PATCH': 'manage_menu',
        'DELETE': 'manage_menu',
    }

    def get_queryset(self):
        business = getattr(self.request, 'business')
        return (
            MenuCategory.objects.filter(business=business)
            .select_related('product_category')
            .annotate(item_count=Count('items'))
            .order_by('position', 'name')
        )


class MenuCategoryImageView(APIView):
    """
    POST   /api/v1/menu/categories/<uuid>/image/  — Upload or replace category image.
    DELETE /api/v1/menu/categories/<uuid>/image/  — Remove category image.

    Reuses the same 'menu_item_images' billing feature gate as item images.
    """
    parser_classes = [MultiPartParser]
    permission_classes = [
        IsAuthenticated,
        HasBusinessMembership,
        HasPermission,
        CheckFeatureAccess,
    ]
    permission_map = {
        'POST': 'manage_menu',
        'DELETE': 'manage_menu',
    }
    required_feature = 'menu_item_images'

    def _get_category(self, request, pk):
        business = getattr(request, 'business')
        return get_object_or_404(MenuCategory, pk=pk, business=business)

    def post(self, request, pk):
        category = self._get_category(request, pk)
        serializer = MenuItemImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data['file']
        if category.image:
            category.image.delete(save=False)

        category.image = uploaded_file
        category.image_updated_at = timezone.now()
        category.save(update_fields=['image', 'image_updated_at'])

        url = category.image.url
        if url.startswith('/'):
            url = request.build_absolute_uri(url)
        return Response({'image_url': url}, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        category = self._get_category(request, pk)
        if not category.image:
            return Response({'detail': 'Esta categoría no tiene imagen.'}, status=status.HTTP_404_NOT_FOUND)

        category.image.delete(save=False)
        category.image = None
        category.image_updated_at = None
        category.save(update_fields=['image', 'image_updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuItemListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'view_menu',
        'POST': 'manage_menu',
    }

    def get_queryset(self):
        business = getattr(self.request, 'business')
        queryset = MenuItem.objects.filter(business=business).select_related('category', 'product', 'product__category')

        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        availability = self.request.query_params.get('available')
        if availability in {'true', 'false'}:
            queryset = queryset.filter(is_available=(availability == 'true'))

        search = (self.request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(tags__icontains=search)
                | Q(sku__icontains=search)
            )

        return queryset.order_by('position', 'name')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MenuItemWriteSerializer
        return MenuItemSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def perform_create(self, serializer):
        serializer.save(business=getattr(self.request, 'business'))


class MenuItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'view_menu',
        'PATCH': 'manage_menu',
        'DELETE': 'manage_menu',
    }

    def get_queryset(self):
        business = getattr(self.request, 'business')
        return MenuItem.objects.filter(business=business).select_related('category', 'product', 'product__category')

    def get_serializer_class(self):
        if self.request.method in {'PATCH', 'PUT'}:
            return MenuItemWriteSerializer
        return MenuItemSerializer

    def perform_update(self, serializer):
        serializer.save()


class MenuStructureView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'view_menu'

    def get(self, request):
        business = getattr(request, 'business')
        items_qs = (
            MenuItem.objects.filter(business=business, is_available=True)
            .select_related('category', 'product', 'product__category')
            .order_by('position', 'name')
        )
        categories = (
            MenuCategory.objects.filter(business=business, is_active=True)
            .select_related('product_category')
            .prefetch_related(Prefetch('items', queryset=items_qs))
            .order_by('position', 'name')
        )
        serializer = MenuStructureCategorySerializer(categories, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# MenuLayoutBlock — admin CRUD + preset apply
# ---------------------------------------------------------------------------

class MenuLayoutBlockListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_menu'

    def get(self, request):
        business = getattr(request, 'business')
        blocks = (
            MenuLayoutBlock.objects.filter(business=business)
            .prefetch_related(
                Prefetch(
                    'block_categories',
                    queryset=MenuLayoutBlockCategory.objects.select_related('category')
                    .order_by('position', 'category__name'),
                )
            )
            .order_by('position', 'title')
        )
        serializer = MenuLayoutBlockSerializer(blocks, many=True)
        return Response(serializer.data)

    def post(self, request):
        business = getattr(request, 'business')
        serializer = MenuLayoutBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(business=business)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MenuLayoutBlockDetailView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_menu'

    def _get_block(self, request, pk):
        business = getattr(request, 'business')
        return get_object_or_404(MenuLayoutBlock, pk=pk, business=business)

    def get(self, request, pk):
        block = self._get_block(request, pk)
        return Response(MenuLayoutBlockSerializer(block).data)

    def patch(self, request, pk):
        block = self._get_block(request, pk)
        serializer = MenuLayoutBlockSerializer(block, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        block = self._get_block(request, pk)
        block.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MenuLayoutBlockReorderView(APIView):
    """PATCH /layout/blocks/reorder/ — bulk-update positions."""
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_menu'

    def patch(self, request):
        business = getattr(request, 'business')
        serializer = MenuLayoutBlockReorderSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        for item in serializer.validated_data:
            MenuLayoutBlock.objects.filter(pk=item['id'], business=business).update(
                position=item['position']
            )
        return Response({'detail': 'Reordenado correctamente.'})


class MenuLayoutBlockApplyPresetView(APIView):
    """POST /layout/blocks/apply-preset/ — destroy & rebuild from template."""
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_menu'

    def post(self, request):
        template = (request.data.get('template') or '').strip()
        if template not in ('drinks_first', 'food_first'):
            return Response(
                {'detail': 'template debe ser "drinks_first" o "food_first".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        business = getattr(request, 'business')
        from .layout_presets import apply_preset
        apply_preset(business, template)
        blocks = MenuLayoutBlock.objects.filter(business=business).prefetch_related(
            Prefetch(
                'block_categories',
                queryset=MenuLayoutBlockCategory.objects.select_related('category')
                .order_by('position', 'category__name'),
            )
        ).order_by('position', 'title')
        return Response(MenuLayoutBlockSerializer(blocks, many=True).data)


class MenuImportView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'import_menu'

    def post(self, request):
        serializer = MenuImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = serializer.validated_data['file']
        business = getattr(request, 'business')
        try:
            result = apply_menu_import(file_obj, business=business)
        except MenuImportError as exc:
            return Response({'file': [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class MenuLogoUploadView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_menu_branding'

    def post(self, request):
        raw_file = request.data.get('file')
        if raw_file and hasattr(raw_file, 'size') and raw_file.size > 5 * 1024 * 1024:
            return Response(
                {'error': 'El archivo supera el límite de 5 MB.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = MenuLogoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = serializer.validated_data['file']
        
        business = getattr(request, 'business')
        branding = ensure_menu_branding(business)
        
        # Safe filename
        ext = file_obj.name.split('.')[-1] if '.' in file_obj.name else 'png'
        filename = f"business/{business.id}/menu-logo-{int(timezone.now().timestamp())}.{ext}"

        branding.logo_image.save(filename, ContentFile(file_obj.read()), save=True)
        url = branding.logo_url or ''
        if url.startswith('/'):
            url = request.build_absolute_uri(url)

        config = ensure_public_menu_config(business)
        update_fields: list[str] = []
        if config.logo_url != url:
            config.logo_url = url
            update_fields.append('logo_url')
        # Keep theme_json in sync so the public menu page shows the logo
        # without requiring a separate "Guardar Cambios" click.
        theme = config.theme_json or {}
        if theme.get('menuLogoUrl') != url:
            theme['menuLogoUrl'] = url
            config.theme_json = theme
            update_fields.append('theme_json')
        if update_fields:
            config.save(update_fields=update_fields)

        return Response({'url': url})


class MenuExportView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'export_menu'

    def get(self, request):
        business = getattr(request, 'business')
        content = export_menu_to_workbook(business=business)
        filename = f"carta-{timezone.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class PublicMenuConfigView(generics.RetrieveUpdateAPIView):
    serializer_class = PublicMenuConfigSerializer
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'manage_menu',
        'PUT': 'manage_menu',
        'PATCH': 'manage_menu',
    }

    def get_object(self):
        business = getattr(self.request, 'business')
        config = ensure_public_menu_config(business)
        branding = ensure_menu_branding(business)
        if not config.brand_name:
            config.brand_name = branding.display_name
            config.save(update_fields=['brand_name'])
        return config


class MenuBrandingSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = MenuBrandingSettingsSerializer
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'manage_menu_branding',
        'PATCH': 'manage_menu_branding',
    }

    def get_object(self):
        business = getattr(self.request, 'business')
        return ensure_menu_branding(business)


class PublicMenuBySlugView(APIView):
    permission_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'public_menu'

    def get(self, request, slug):
        config = get_object_or_404(
            PublicMenuConfig.objects.select_related('business'),
            slug=slug,
            enabled=True,
        )
        if config.business.status not in PUBLISHABLE_STATUSES:
            return Response(status=status.HTTP_404_NOT_FOUND)
        branding = ensure_menu_branding(config.business)
        items_qs = (
            MenuItem.objects.filter(business=config.business, is_available=True)
            .filter(Q(product__isnull=True) | Q(product__is_active=True))
            .select_related('product', 'product__category')
            .order_by('position', 'name')
        )
        categories = (
            MenuCategory.objects.filter(business=config.business, is_active=True)
            .select_related('product_category')
            .prefetch_related(Prefetch('items', queryset=items_qs))
            .order_by('position', 'name')
        )

        menu_data = PublicMenuCategorySerializer(
            categories, many=True, context={'request': request}
        ).data
        branding_data = MenuBrandingSettingsSerializer(branding, context={'request': request}).data
        config_data = PublicMenuConfigSerializer(config).data

        # Layout blocks (template-driven)
        layout_blocks_qs = (
            MenuLayoutBlock.objects.filter(business=config.business)
            .prefetch_related(
                Prefetch(
                    'block_categories',
                    queryset=MenuLayoutBlockCategory.objects.select_related('category')
                    .prefetch_related(
                        Prefetch(
                            'category__items',
                            queryset=items_qs,
                        )
                    )
                    .order_by('position', 'category__name'),
                )
            )
            .order_by('position', 'title')
        )
        layout_blocks_data = PublicMenuLayoutBlockSerializer(
            layout_blocks_qs, many=True, context={'request': request}
        ).data

        # Build safe public engagement data
        engagement = _build_public_engagement(config.business, request)

        return Response({
            'business': {
                'name': config.business.name,
            },
            'slug': config.slug,
            'public_url': build_public_menu_url(config.slug),
            'config': config_data,
            'branding': branding_data,
            'categories': menu_data,
            'layout_blocks': layout_blocks_data,
            'engagement': engagement,
        })


class PublicMenuResolveView(APIView):
    permission_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'public_menu'

    def get(self, request, public_id):
        config = get_object_or_404(
            PublicMenuConfig.objects.select_related('business'),
            public_id=public_id,
            enabled=True,
        )
        if config.business.status not in PUBLISHABLE_STATUSES:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({"slug": config.slug})


class MenuQRCodeView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission, require_service('menu_qr')]
    required_permission = 'view_menu_admin'

    def get(self, request, business_id: int):
        business = getattr(request, 'business')
        if business.id != business_id:
            return Response({'detail': 'No puedes acceder al QR de otro negocio.'}, status=status.HTTP_403_FORBIDDEN)

        config = ensure_public_menu_config(business)
        if not config.enabled:
            config.enabled = True
            config.save(update_fields=['enabled'])
        public_url = build_public_menu_url(config.slug)
        qr_svg = build_qr_svg(public_url)

        return Response({
            'business_id': business.id,
            'slug': config.slug,
            'public_url': public_url,
            'qr_svg': qr_svg,
            'generated_at': timezone.now(),
        })


class MenuItemImageView(APIView):
    """
    POST   /api/v1/menu/items/<uuid>/image/  — Upload or replace product image.
    DELETE /api/v1/menu/items/<uuid>/image/  — Remove product image.

    Both endpoints require the business subscription to include the
    'menu_item_images' billing module (Plan QR Visual or QR Marca).
    """
    parser_classes = [MultiPartParser]
    permission_classes = [
        IsAuthenticated,
        HasBusinessMembership,
        HasPermission,
        CheckFeatureAccess,
    ]
    permission_map = {
        'POST': 'manage_menu',
        'DELETE': 'manage_menu',
    }
    # CheckFeatureAccess reads this attribute:
    required_feature = 'menu_item_images'

    def _get_item(self, request, pk):
        business = getattr(request, 'business')
        return get_object_or_404(MenuItem, pk=pk, business=business)

    def post(self, request, pk):
        item = self._get_item(request, pk)
        serializer = MenuItemImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data['file']
        # Delete old image file from storage if present
        if item.image:
            item.image.delete(save=False)

        item.image = uploaded_file
        item.image_updated_at = timezone.now()
        item.save(update_fields=['image', 'image_updated_at'])

        # Build absolute URL for the response
        url = item.image.url
        if url.startswith('/'):
            url = request.build_absolute_uri(url)

        return Response({'image_url': url}, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        item = self._get_item(request, pk)
        if not item.image:
            return Response({'detail': 'Este producto no tiene imagen.'}, status=status.HTTP_404_NOT_FOUND)

        item.image.delete(save=False)
        item.image = None
        item.image_updated_at = None
        item.save(update_fields=['image', 'image_updated_at'])

        return Response(status=status.HTTP_204_NO_CONTENT)


def build_public_menu_url(slug: str) -> str:
    base_url = getattr(settings, 'PUBLIC_MENU_BASE_URL', None) or getattr(settings, 'FRONTEND_URL', None) or 'http://localhost:3000'
    return f"{base_url.rstrip('/')}/m/{slug}/"


def build_qr_svg(public_url: str) -> str:
    """Delegate to shared utility.  Kept for backward-compat imports."""
    from common.qr import build_qr_svg as _shared_build_qr_svg
    return _shared_build_qr_svg(public_url)


# ---------------------------------------------------------------------------
# Engagement helpers
# ---------------------------------------------------------------------------

def _build_public_engagement(business, request) -> dict:
    """Build the safe public engagement payload for a menu response."""
    try:
        eng = business.menu_engagement_settings
    except MenuEngagementSettings.DoesNotExist:
        return _empty_engagement()

    # ── Plan-level entitlement gate ───────────────────────────────────────
    # Resolve what the plan allows; override DB toggles if plan restricts.
    subscription = get_subscription_for_business(business)
    qr_flags = resolve_menu_qr_flags(subscription)

    tips_enabled = eng.tips_enabled and qr_flags['tips_allowed']
    tips_mode = eng.tips_mode
    mp_tip_url = None
    mp_qr_image_url = None

    if tips_enabled:
        if tips_mode in ('mp_link', 'mp_qr_image'):
            mp_tip_url = eng.mp_tip_url or None
        if tips_mode == 'mp_qr_image' and eng.mp_qr_image:
            url = eng.mp_qr_image.url
            if request and url.startswith('/'):
                url = request.build_absolute_uri(url)
            mp_qr_image_url = url
        # Only expose mp_tip_url when mode is mp_link, hide if only QR
        if tips_mode == 'mp_qr_image' and not eng.mp_tip_url:
            mp_tip_url = None

    # ── Reviews: prefer ReviewConfig (new domain), fallback to legacy ─────
    reviews_enabled_effective = False
    write_review_url = None
    reviews_hybrid = False

    try:
        review_config = business.review_config
        if review_config.enabled and qr_flags['reviews_allowed']:
            reviews_enabled_effective = True
            write_review_url = review_config.redirect_url
            reviews_hybrid = True
    except Exception:
        # ReviewConfig doesn't exist yet — fallback to legacy engagement fields
        legacy_url = eng.google_write_review_url
        reviews_enabled_effective = (eng.reviews_enabled or bool(legacy_url)) and qr_flags['reviews_allowed']
        write_review_url = legacy_url if reviews_enabled_effective else None

    return {
        'tips_enabled': tips_enabled,
        'tips_mode': tips_mode,
        'mp_tip_url': mp_tip_url,
        'mp_qr_image_url': mp_qr_image_url,
        'reviews_enabled': reviews_enabled_effective,
        'google_write_review_url': write_review_url,
        'reviews_hybrid': reviews_hybrid,
    }


def _empty_engagement() -> dict:
    return {
        'tips_enabled': False,
        'tips_mode': 'mp_link',
        'mp_tip_url': None,
        'mp_qr_image_url': None,
        'reviews_enabled': False,
        'google_write_review_url': None,
        'reviews_hybrid': False,
    }


# ---------------------------------------------------------------------------
# Private: Engagement settings (admin panel)
# ---------------------------------------------------------------------------

class MenuEngagementSettingsView(generics.RetrieveUpdateAPIView):
    """GET/PATCH engagement settings for the authenticated business."""
    serializer_class = MenuEngagementSettingsSerializer
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    parser_classes = [MultiPartParser, JSONParser]
    permission_map = {
        'GET': 'manage_menu',
        'PATCH': 'manage_menu',
        'PUT': 'manage_menu',
    }

    def get_object(self):
        return ensure_menu_engagement(getattr(self.request, 'business'))


class MenuEngagementQRUploadView(APIView):
    """Upload the Mercado Pago QR screenshot for the tip modal."""
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'manage_menu'

    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'detail': 'No se proporcionó ningún archivo.'}, status=status.HTTP_400_BAD_REQUEST)

        allowed_types = {'image/jpeg', 'image/png', 'image/webp'}
        content_type = getattr(file_obj, 'content_type', None)
        if content_type and content_type not in allowed_types:
            return Response({'detail': 'Formato no válido. JPG, PNG o WebP.'}, status=status.HTTP_400_BAD_REQUEST)

        max_size = 5 * 1024 * 1024
        if file_obj.size > max_size:
            return Response({'detail': 'Imagen demasiado grande. Máximo 5 MB.'}, status=status.HTTP_400_BAD_REQUEST)

        business = getattr(request, 'business')
        engagement = ensure_menu_engagement(business)

        # Remove old QR image
        if engagement.mp_qr_image:
            engagement.mp_qr_image.delete(save=False)

        ext = file_obj.name.rsplit('.', 1)[-1] if '.' in file_obj.name else 'png'
        filename = f"business/{business.id}/tip-qr-{int(timezone.now().timestamp())}.{ext}"
        engagement.mp_qr_image.save(filename, ContentFile(file_obj.read()), save=True)

        url = engagement.mp_qr_image.url
        if url.startswith('/'):
            url = request.build_absolute_uri(url)

        return Response({'url': url}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Mercado Pago OAuth per-business views moved to apps.merchant_payments
# (Slice 5A extraction) — see apps/merchant_payments/views.py. Tips resolves
# its MP client via apps.merchant_payments.services (Slice 5B.1), imported
# above.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Public: Tip preference creation (Fase 2)
# ---------------------------------------------------------------------------

class PublicTipCreatePreferenceView(APIView):
    """
    POST /api/v1/menu/public/slug/{slug}/tips/create-preference/
    Creates a TipTransaction + MP preference and returns the init_point.
    Requires the business to have an active merchant Mercado Pago connection
    (apps.merchant_payments) — no fallback to the platform's global token.
    """
    permission_classes = [AllowAny]

    def post(self, request, slug):
        config = get_object_or_404(PublicMenuConfig.objects.select_related('business'), slug=slug, enabled=True)
        business = config.business

        # Validate engagement settings
        try:
            eng = business.menu_engagement_settings
        except MenuEngagementSettings.DoesNotExist:
            return Response({'detail': 'Propinas no disponibles.'}, status=status.HTTP_400_BAD_REQUEST)

        # Plan-level gate: check if tips are allowed for this business's subscription
        subscription = get_subscription_for_business(business)
        qr_flags = resolve_menu_qr_flags(subscription)
        if not qr_flags['tips_allowed']:
            return Response({'detail': 'Propinas no disponibles en el plan actual.'}, status=status.HTTP_403_FORBIDDEN)

        if not eng.tips_enabled or eng.tips_mode != 'mp_oauth_checkout':
            return Response({'detail': 'Propinas dinámicas no habilitadas para este menú.'}, status=status.HTTP_400_BAD_REQUEST)

        # ── Resolve merchant MP client ───────────────────────────────────────
        # Merchant-side payments (Customer → Business) MUST use the Business's
        # own Mercado Pago connection. No fallback to the platform's global
        # token — that belongs to apps.billing (Business → MiRubro) only.
        try:
            sdk = get_merchant_mp_client(business)
        except MerchantPaymentConnectionUnavailable as exc:
            logger.warning(f"[TipPreference] {exc}")
            return Response(
                {'detail': 'Pago no disponible. Este negocio no tiene Mercado Pago conectado.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = TipCreatePreferenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data['amount']
        table_ref = serializer.validated_data.get('table_ref', '')

        # Create TipTransaction
        import uuid as _uuid
        ext_ref = f"TIP-{_uuid.uuid4().hex[:20].upper()}"
        tip = TipTransaction.objects.create(
            business=business,
            amount=amount,
            currency='ARS',
            status='created',
            external_reference=ext_ref,
            menu_slug=slug,
            table_ref=table_ref,
        )

        # Build preference via MP (sdk resolved above from the business's own connection)
        # back_urls point to the *frontend* (user's browser is redirected here after payment)
        # build_public_menu_url() uses PUBLIC_MENU_BASE_URL / FRONTEND_URL — correct for browser redirects
        base_url = build_public_menu_url(slug).rstrip('/')
        back_urls = {
            'success': f"{base_url}/tip/success?tip_id={tip.id}",
            'pending': f"{base_url}/tip/pending?tip_id={tip.id}",
            'failure': f"{base_url}/tip/failure?tip_id={tip.id}",
        }
        pref_data: dict = {
            'items': [
                {
                    'title': f"Propina - {business.name}",
                    'quantity': 1,
                    'unit_price': float(amount),
                    'currency_id': 'ARS',
                }
            ],
            'external_reference': ext_ref,
            'back_urls': back_urls,
            'auto_return': 'approved',
            'metadata': {
                'tip_id': str(tip.id),
                'business_id': business.id,
                'table_ref': table_ref,
            },
        }
        # notification_url must be the API's public URL (ngrok in DEV, real domain in prod).
        # Only BASE_PUBLIC_URL is appropriate here — frontend URLs (FRONTEND_URL / PUBLIC_MENU_BASE_URL)
        # point to port 3000 (Next.js) and would cause MP to misdeliver webhook POSTs.
        #
        # flow=tip&ref=<external_reference> lets the webhook resolve the owning
        # Business from the local TipTransaction BEFORE it re-fetches the payment,
        # so the re-fetch can use that Business's own Mercado Pago connection
        # instead of the platform's global token. MP echoes the notification_url
        # query string verbatim on every callback; it is never client-supplied.
        api_public_url = getattr(settings, 'BASE_PUBLIC_URL', None)
        if api_public_url:
            webhook_base = f"{api_public_url.rstrip('/')}/api/v1/billing/mercadopago/webhook"
            pref_data['notification_url'] = f"{webhook_base}?flow=tip&ref={quote(ext_ref)}"
        else:
            logger.warning("[TipPreference] BASE_PUBLIC_URL not set — notification_url omitted. MP webhooks will NOT fire in DEV.")

        try:
            result = sdk.preference().create(pref_data)
            if result['status'] not in (200, 201):
                logger.error(f"[TipPreference] MP error: {result}")
                tip.status = 'cancelled'
                tip.save(update_fields=['status'])
                return Response({'detail': 'Error al crear preferencia de pago.'}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as exc:
            logger.error(f"[TipPreference] Exception: {exc}", exc_info=True)
            tip.status = 'cancelled'
            tip.save(update_fields=['status'])
            return Response({'detail': 'Error al procesar el pago.'}, status=status.HTTP_502_BAD_GATEWAY)

        pref_response = result['response']
        tip.mp_preference_id = pref_response.get('id')
        tip.status = 'pending'
        tip.save(update_fields=['mp_preference_id', 'status', 'updated_at'])

        return Response({
            'tip_id': str(tip.id),
            'init_point': pref_response.get('init_point'),
            'external_reference': ext_ref,
        }, status=status.HTTP_201_CREATED)


class PublicTipStatusView(APIView):
    """GET /api/v1/menu/public/tips/{tip_id}/status/ — public tip status polling."""
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'public_tips'

    def get(self, request, tip_id):
        tip = get_object_or_404(TipTransaction, id=tip_id)
        return Response({
            'id': str(tip.id),
            'amount': str(tip.amount),
            'currency': tip.currency,
            'status': tip.status,
            'external_reference': tip.external_reference,
            'created_at': tip.created_at,
        })


class PublicTipVerifyView(APIView):
    """
    GET /api/v1/menu/public/tips/<tip_id>/verify/?payment_id=<mp_payment_id>

    DEV/TEST: verify a tip payment via the MP Payments API (no webhook needed).
    - Validates payment.external_reference matches TipTransaction.external_reference.
    - Updates TipTransaction.status from MP.
    - Idempotent: safe to call multiple times.
    Also accepts `collection_id` as fallback (MP sometimes uses that param name).
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'public_tips'

    # MP status → TipTransaction status
    _STATUS_MAP = {
        'approved': 'approved',
        'pending': 'pending',
        'in_process': 'pending',
        'authorized': 'pending',
        'rejected': 'rejected',
        'cancelled': 'cancelled',
        'refunded': 'cancelled',
        'charged_back': 'cancelled',
    }

    def get(self, request, tip_id):
        tip = get_object_or_404(TipTransaction, id=tip_id)

        payment_id = (
            request.query_params.get('payment_id')
            or request.query_params.get('collection_id')
        )
        if not payment_id:
            return Response(
                {'detail': 'Parámetro payment_id requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Resolve merchant MP client (same rule as create-preference: the
        # business's own connection, never the platform's global token) ─────
        try:
            sdk = get_merchant_mp_client(tip.business)
        except MerchantPaymentConnectionUnavailable as exc:
            logger.warning(f"[TipVerify] {exc}")
            return Response(
                {'detail': 'No hay credenciales de Mercado Pago configuradas para este negocio.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # ── Query MP Payments API ────────────────────────────────────────────
        try:
            result = sdk.payment().get(payment_id)
        except Exception as exc:
            logger.error(f'[TipVerify] SDK error for payment {payment_id}: {exc}', exc_info=True)
            return Response(
                {'detail': 'Error al consultar Mercado Pago.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if result.get('status') not in (200, 201):
            logger.warning(f'[TipVerify] MP returned status={result.get("status")} for payment {payment_id}')
            return Response(
                {'detail': 'Pago no encontrado en Mercado Pago.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        mp_payment = result['response']
        mp_ext_ref = mp_payment.get('external_reference') or ''

        # ── Security: validate payment belongs to this tip ───────────────────
        if mp_ext_ref != tip.external_reference:
            logger.warning(
                f'[TipVerify] external_reference mismatch: payment has "{mp_ext_ref}", '
                f'tip has "{tip.external_reference}" (tip_id={tip_id})'
            )
            return Response(
                {'detail': 'El pago no corresponde a esta propina.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mp_status = mp_payment.get('status', '')
        mp_status_detail = mp_payment.get('status_detail', '')
        new_status = self._STATUS_MAP.get(mp_status, 'pending')

        # ── Idempotent update ────────────────────────────────────────────────
        fields_to_update = []
        if tip.mp_payment_id != str(payment_id):
            tip.mp_payment_id = str(payment_id)
            fields_to_update.append('mp_payment_id')
        if tip.status != new_status:
            tip.status = new_status
            fields_to_update.append('status')
        if fields_to_update:
            fields_to_update.append('updated_at')
            tip.save(update_fields=fields_to_update)
            logger.info(f'[TipVerify] tip={tip.id} updated: status={new_status}, mp_payment_id={payment_id}')
        else:
            logger.debug(f'[TipVerify] tip={tip.id} no change needed (status already {new_status})')

        return Response({
            'tip_id': str(tip.id),
            'status': tip.status,
            'mp_payment_id': tip.mp_payment_id,
            'amount': str(tip.amount),
            'currency': tip.currency,
            'mp_status': mp_status,
            'mp_status_detail': mp_status_detail,
            'verified_at': tip.updated_at,
        })

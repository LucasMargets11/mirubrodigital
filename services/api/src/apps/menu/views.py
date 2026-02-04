from __future__ import annotations

import base64
import io

import segno
from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from apps.business.service_policy import require_service
from .importer import MenuImportError, apply_menu_import, export_menu_to_workbook
from .models import (
    MenuBrandingSettings,
    MenuCategory,
    MenuItem,
    PublicMenuConfig,
    ensure_menu_branding,
    ensure_public_menu_config,
)
from .serializers import (
    MenuCategorySerializer,
    MenuImportUploadSerializer,
    MenuLogoUploadSerializer,
    MenuItemSerializer,
    MenuItemWriteSerializer,
    MenuStructureCategorySerializer,
    PublicMenuConfigSerializer,
    PublicMenuCategorySerializer,
    MenuBrandingSettingsSerializer,
)


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
            .annotate(item_count=Count('items'))
            .order_by('position', 'name')
        )


class MenuItemListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    permission_map = {
        'GET': 'view_menu',
        'POST': 'manage_menu',
    }

    def get_queryset(self):
        business = getattr(self.request, 'business')
        queryset = MenuItem.objects.filter(business=business).select_related('category')

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
        return MenuItem.objects.filter(business=business).select_related('category')

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
            .select_related('category')
            .order_by('position', 'name')
        )
        categories = (
            MenuCategory.objects.filter(business=business, is_active=True)
            .prefetch_related(Prefetch('items', queryset=items_qs))
            .order_by('position', 'name')
        )
        serializer = MenuStructureCategorySerializer(categories, many=True)
        return Response(serializer.data)


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
        if config.logo_url != url:
            config.logo_url = url
            config.save(update_fields=['logo_url'])

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

    @method_decorator(cache_page(60 * 5))
    def get(self, request, slug):
        config = get_object_or_404(
            PublicMenuConfig.objects.select_related('business'),
            slug=slug,
            enabled=True,
        )
        branding = ensure_menu_branding(config.business)
        items_qs = (
            MenuItem.objects.filter(business=config.business)
            .order_by('position', 'name')
        )
        categories = (
            MenuCategory.objects.filter(business=config.business, is_active=True)
            .prefetch_related(Prefetch('items', queryset=items_qs))
            .order_by('position', 'name')
        )

        menu_data = PublicMenuCategorySerializer(categories, many=True).data
        branding_data = MenuBrandingSettingsSerializer(branding, context={'request': request}).data
        config_data = PublicMenuConfigSerializer(config).data

        return Response({
            'business': {
                'id': config.business_id,
                'name': config.business.name,
            },
            'slug': config.slug,
            'public_url': build_public_menu_url(config.slug),
            'config': config_data,
            'branding': branding_data,
            'categories': menu_data,
        })


class PublicMenuResolveView(APIView):
    permission_classes = []

    def get(self, request, public_id):
        config = get_object_or_404(PublicMenuConfig, public_id=public_id, enabled=True)
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


def build_public_menu_url(slug: str) -> str:
    base_url = getattr(settings, 'PUBLIC_MENU_BASE_URL', None) or getattr(settings, 'FRONTEND_URL', None) or 'http://localhost:3000'
    return f"{base_url.rstrip('/')}/m/{slug}/"


def build_qr_svg(public_url: str) -> str:
    cache_key = f"menu-qr:{public_url}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    qr = segno.make(public_url, micro=False)
    buffer = io.BytesIO()
    qr.save(buffer, kind='svg', scale=6, border=0)
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    data_uri = f"data:image/svg+xml;base64,{encoded}"
    cache.set(cache_key, data_uri, 60 * 60)
    return data_uri

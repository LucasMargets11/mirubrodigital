from __future__ import annotations

from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from .importer import MenuImportError, apply_menu_import, export_menu_to_workbook
from .models import MenuCategory, MenuItem
from .serializers import (
    MenuCategorySerializer,
    MenuImportUploadSerializer,
    MenuItemSerializer,
    MenuItemWriteSerializer,
    MenuStructureCategorySerializer,
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

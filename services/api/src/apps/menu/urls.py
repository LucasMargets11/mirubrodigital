from django.urls import path

from .views import (
    MenuBrandingSettingsView,
    MenuCategoryDetailView,
    MenuCategoryListCreateView,
    MenuExportView,
    MenuImportView,
    MenuLogoUploadView,
    MenuItemDetailView,
    MenuItemListCreateView,
    MenuStructureView,
    PublicMenuConfigView,
    PublicMenuBySlugView,
    PublicMenuResolveView,
)

app_name = 'menu'

urlpatterns = [
    path('categories/', MenuCategoryListCreateView.as_view(), name='category-list'),
    path('categories/<uuid:pk>/', MenuCategoryDetailView.as_view(), name='category-detail'),
    path('items/', MenuItemListCreateView.as_view(), name='item-list'),
    path('items/<uuid:pk>/', MenuItemDetailView.as_view(), name='item-detail'),
    path('structure/', MenuStructureView.as_view(), name='structure'),
    path('import/', MenuImportView.as_view(), name='import'),
    path('export/', MenuExportView.as_view(), name='export'),
    path('public/config/', PublicMenuConfigView.as_view(), name='public-config'),
    path('branding/', MenuBrandingSettingsView.as_view(), name='branding-settings'),
    path('public/logo/', MenuLogoUploadView.as_view(), name='public-logo-upload'),
    path('public/slug/<slug:slug>/', PublicMenuBySlugView.as_view(), name='public-by-slug'),
    path('public/resolve/<uuid:public_id>/', PublicMenuResolveView.as_view(), name='public-resolve'),
]

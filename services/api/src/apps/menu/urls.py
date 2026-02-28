from django.urls import path

from .views import (
    MenuBrandingSettingsView,
    MenuCategoryDetailView,
    MenuCategoryListCreateView,
    MenuEngagementSettingsView,
    MenuEngagementQRUploadView,
    MenuExportView,
    MenuImportView,
    MenuItemImageView,
    MenuLogoUploadView,
    MenuItemDetailView,
    MenuItemListCreateView,
    MenuStructureView,
    MercadoPagoConnectionStatusView,
    MercadoPagoDisconnectView,
    MercadoPagoOAuthCallbackView,
    MercadoPagoOAuthStartView,
    PublicMenuConfigView,
    PublicMenuBySlugView,
    PublicMenuResolveView,
    PublicTipCreatePreferenceView,
    PublicTipStatusView,
    PublicTipVerifyView,
)

app_name = 'menu'

urlpatterns = [
    # ── Admin: categories & items ──────────────────────────────────────────
    path('categories/', MenuCategoryListCreateView.as_view(), name='category-list'),
    path('categories/<uuid:pk>/', MenuCategoryDetailView.as_view(), name='category-detail'),
    path('items/', MenuItemListCreateView.as_view(), name='item-list'),
    path('items/<uuid:pk>/', MenuItemDetailView.as_view(), name='item-detail'),
    path('items/<uuid:pk>/image/', MenuItemImageView.as_view(), name='item-image'),
    path('structure/', MenuStructureView.as_view(), name='structure'),
    path('import/', MenuImportView.as_view(), name='import'),
    path('export/', MenuExportView.as_view(), name='export'),
    # ── Admin: config & branding ───────────────────────────────────────────
    path('public/config/', PublicMenuConfigView.as_view(), name='public-config'),
    path('branding/', MenuBrandingSettingsView.as_view(), name='branding-settings'),
    path('public/logo/', MenuLogoUploadView.as_view(), name='public-logo-upload'),
    # ── Admin: engagement settings (tips + reviews) ────────────────────────
    path('engagement/', MenuEngagementSettingsView.as_view(), name='engagement-settings'),
    path('engagement/upload-qr/', MenuEngagementQRUploadView.as_view(), name='engagement-upload-qr'),
    # ── Admin: Mercado Pago OAuth per-business (Fase 2) ────────────────────
    path('mercadopago/connect/start/', MercadoPagoOAuthStartView.as_view(), name='mp-oauth-start'),
    path('mercadopago/connect/callback/', MercadoPagoOAuthCallbackView.as_view(), name='mp-oauth-callback'),
    path('mercadopago/connect/status/', MercadoPagoConnectionStatusView.as_view(), name='mp-oauth-status'),
    path('mercadopago/connect/', MercadoPagoDisconnectView.as_view(), name='mp-oauth-disconnect'),
    # ── Public: menu by slug ───────────────────────────────────────────────
    path('public/slug/<slug:slug>/', PublicMenuBySlugView.as_view(), name='public-by-slug'),
    path('public/resolve/<uuid:public_id>/', PublicMenuResolveView.as_view(), name='public-resolve'),
    # ── Public: tips (Fase 2) ─────────────────────────────────────────────
    path('public/slug/<slug:slug>/tips/create-preference/', PublicTipCreatePreferenceView.as_view(), name='public-tip-create'),
    path('public/tips/<uuid:tip_id>/status/', PublicTipStatusView.as_view(), name='public-tip-status'),
    path('public/tips/<uuid:tip_id>/verify/', PublicTipVerifyView.as_view(), name='public-tip-verify'),
]

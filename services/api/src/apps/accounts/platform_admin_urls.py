from django.urls import path

from .platform_admin_views import (
    AdminMeView,
    AdminDashboardMetricsView,
)
from .platform_auth_views import (
    AdminLoginView,
    AdminMFAVerifyView,
    AdminMFARecoveryView,
    AdminMFAEnrollView,
    AdminMFAConfirmView,
    AdminMFADisableView,
    AdminLogoutView,
)
from .platform_admin_clients_views import (
    AdminClientListView,
    AdminClientDetailView,
    AdminClientKPIsView,
)
from .platform_admin_subscriptions_views import (
    AdminSubscriptionListView,
    AdminSubscriptionDetailView,
    AdminSubscriptionKPIsView,
)
from .platform_admin_notes_views import (
    AdminInternalNoteListCreateView,
)
from .platform_admin_support_views import (
    AdminTicketListView,
    AdminTicketCreateView,
    AdminTicketDetailView,
    AdminTicketUpdateView,
    AdminTicketMessageCreateView,
    AdminTicketKPIsView,
    AdminStaffListView,
)
from .platform_admin_reporting_views import (
    AdminReportingOverviewView,
    AdminReportingAlertsView,
)
from apps.blog.admin_views import (
    AdminBlogPostListView,
    AdminBlogPostCreateView,
    AdminBlogPostKPIsView,
    AdminBlogPostDetailView,
    AdminBlogPostUpdateView,
    AdminBlogPostPublishView,
    AdminBlogPostUnpublishView,
    AdminBlogPostArchiveView,
    AdminBlogPostScheduleView,
    AdminBlogCategoryListCreateView,
    AdminBlogCategoryUpdateView,
)

urlpatterns = [
    # ── Auth (Phase 1.1 hardening) ───────────────────────────────────────
    path('auth/login/', AdminLoginView.as_view(), name='platform-admin-login'),
    path('auth/mfa-verify/', AdminMFAVerifyView.as_view(), name='platform-admin-mfa-verify'),
    path('auth/mfa-recovery/', AdminMFARecoveryView.as_view(), name='platform-admin-mfa-recovery'),
    path('auth/mfa-enroll/', AdminMFAEnrollView.as_view(), name='platform-admin-mfa-enroll'),
    path('auth/mfa-confirm/', AdminMFAConfirmView.as_view(), name='platform-admin-mfa-confirm'),
    path('auth/mfa-disable/', AdminMFADisableView.as_view(), name='platform-admin-mfa-disable'),
    path('auth/logout/', AdminLogoutView.as_view(), name='platform-admin-logout'),
    # ── Data endpoints ───────────────────────────────────────────────────
    path('me/', AdminMeView.as_view(), name='platform-admin-me'),
    path('dashboard/metrics/', AdminDashboardMetricsView.as_view(), name='platform-admin-dashboard-metrics'),
    # ── Clients (Phase 2) ────────────────────────────────────────────────
    path('clients/', AdminClientListView.as_view(), name='platform-admin-clients'),
    path('clients/kpis/', AdminClientKPIsView.as_view(), name='platform-admin-clients-kpis'),
    path('clients/<int:business_id>/', AdminClientDetailView.as_view(), name='platform-admin-client-detail'),
    # ── Subscriptions (Phase 2) ──────────────────────────────────────────
    path('subscriptions/', AdminSubscriptionListView.as_view(), name='platform-admin-subscriptions'),
    path('subscriptions/kpis/', AdminSubscriptionKPIsView.as_view(), name='platform-admin-subscriptions-kpis'),
    path('subscriptions/<str:subscription_id>/', AdminSubscriptionDetailView.as_view(), name='platform-admin-subscription-detail'),
    # ── Internal Notes (Phase 2) ─────────────────────────────────────────
    path('notes/', AdminInternalNoteListCreateView.as_view(), name='platform-admin-notes'),
    # ── Support Tickets (Phase 3) ────────────────────────────────────────
    path('tickets/', AdminTicketListView.as_view(), name='platform-admin-tickets'),
    path('tickets/create/', AdminTicketCreateView.as_view(), name='platform-admin-ticket-create'),
    path('tickets/kpis/', AdminTicketKPIsView.as_view(), name='platform-admin-tickets-kpis'),
    path('tickets/<str:ticket_id>/', AdminTicketDetailView.as_view(), name='platform-admin-ticket-detail'),
    path('tickets/<str:ticket_id>/update/', AdminTicketUpdateView.as_view(), name='platform-admin-ticket-update'),
    path('tickets/<str:ticket_id>/messages/', AdminTicketMessageCreateView.as_view(), name='platform-admin-ticket-messages'),
    # ── Staff (Phase 3) ──────────────────────────────────────────────────
    path('staff/', AdminStaffListView.as_view(), name='platform-admin-staff'),
    # ── Reports / Monitoring (Phase 4) ───────────────────────────────────
    path('reports/overview/', AdminReportingOverviewView.as_view(), name='platform-admin-reports-overview'),
    path('reports/alerts/', AdminReportingAlertsView.as_view(), name='platform-admin-reports-alerts'),
    # ── Blog CMS (Phase 5) ───────────────────────────────────────────────
    path('blog/posts/', AdminBlogPostListView.as_view(), name='platform-admin-blog-posts'),
    path('blog/posts/create/', AdminBlogPostCreateView.as_view(), name='platform-admin-blog-post-create'),
    path('blog/posts/kpis/', AdminBlogPostKPIsView.as_view(), name='platform-admin-blog-post-kpis'),
    path('blog/posts/<str:post_id>/', AdminBlogPostDetailView.as_view(), name='platform-admin-blog-post-detail'),
    path('blog/posts/<str:post_id>/update/', AdminBlogPostUpdateView.as_view(), name='platform-admin-blog-post-update'),
    path('blog/posts/<str:post_id>/publish/', AdminBlogPostPublishView.as_view(), name='platform-admin-blog-post-publish'),
    path('blog/posts/<str:post_id>/unpublish/', AdminBlogPostUnpublishView.as_view(), name='platform-admin-blog-post-unpublish'),
    path('blog/posts/<str:post_id>/archive/', AdminBlogPostArchiveView.as_view(), name='platform-admin-blog-post-archive'),
    path('blog/posts/<str:post_id>/schedule/', AdminBlogPostScheduleView.as_view(), name='platform-admin-blog-post-schedule'),
    path('blog/categories/', AdminBlogCategoryListCreateView.as_view(), name='platform-admin-blog-categories'),
    path('blog/categories/<int:category_id>/', AdminBlogCategoryUpdateView.as_view(), name='platform-admin-blog-category-update'),
]

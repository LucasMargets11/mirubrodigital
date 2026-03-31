"""
Platform admin (internal backoffice) API views.

These endpoints are protected by IsPlatformStaff and serve the /admin panel
in the frontend.  They operate across the entire platform, not scoped to a
single tenant/business.
"""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import AccessAuditLog
from apps.accounts.platform_permissions import (
    IsPlatformStaff,
    HasInternalRole,
    get_authorized_sections,
)
from apps.accounts.support_ticket import SupportTicket
from apps.business.models import Business, Subscription

User = get_user_model()


class AdminMeView(APIView):
    """
    GET /api/v1/platform-admin/me/

    Returns the internal profile of the current platform staff user.
    Used by the frontend admin shell to bootstrap navigation and identity.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request: Request) -> Response:
        user = request.user
        profile = user.account_profile
        sections = get_authorized_sections(profile.internal_role or '')

        return Response({
            'user': {
                'id': user.id,
                'email': user.email,
                'name': user.get_full_name() or user.get_username(),
            },
            'internal_role': profile.internal_role,
            'authorized_sections': sections,
        })


class AdminDashboardMetricsView(APIView):
    """
    GET /api/v1/platform-admin/dashboard/metrics/

    Returns placeholder / real platform-wide metrics for the admin dashboard.
    Accessible to any platform staff member with dashboard access.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request: Request) -> Response:
        now = timezone.now()

        # Active businesses (not onboarding, not canceled)
        active_businesses = Business.objects.filter(
            status__in=['active', 'trialing'],
            parent__isnull=True,  # Only HQ, not branches
        ).count()

        # Trial businesses
        trial_businesses = Business.objects.filter(
            status='trialing',
            parent__isnull=True,
        ).count()

        # Businesses with payment issues
        past_due_businesses = Business.objects.filter(
            status='past_due',
            parent__isnull=True,
        ).count()

        # Total registered users (platform-wide)
        total_users = User.objects.filter(is_active=True).count()

        # Recent audit log entries (last 24h)
        recent_cutoff = now - timezone.timedelta(hours=24)
        recent_activity_count = AccessAuditLog.objects.filter(
            created_at__gte=recent_cutoff,
        ).count()

        # Recent audit entries for activity feed (last 10)
        recent_activity = list(
            AccessAuditLog.objects.select_related('actor', 'business')
            .order_by('-created_at')[:10]
            .values(
                'id', 'action', 'created_at',
                'actor__email', 'business__name',
                'entity_type', 'entity_id',
            )
        )

        # ── Ticket KPIs ──────────────────────────────────────────────────
        seven_days_ago = now - timezone.timedelta(days=7)
        open_tickets = SupportTicket.objects.filter(
            status__in=[SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS],
        ).count()
        waiting_on_client = SupportTicket.objects.filter(
            status=SupportTicket.STATUS_WAITING,
        ).count()
        urgent_unassigned = SupportTicket.objects.filter(
            priority=SupportTicket.PRIORITY_URGENT,
            assigned_to__isnull=True,
        ).exclude(status__in=[SupportTicket.STATUS_RESOLVED, SupportTicket.STATUS_CLOSED]).count()
        new_last_7_days = SupportTicket.objects.filter(
            created_at__gte=seven_days_ago,
        ).count()

        ticket_kpis = {
            'open_tickets': open_tickets,
            'waiting_on_client': waiting_on_client,
            'urgent_unassigned': urgent_unassigned,
            'new_last_7_days': new_last_7_days,
        }

        # ── Alerts ────────────────────────────────────────────────────────
        alerts = []
        if past_due_businesses > 0:
            alerts.append({
                'type': 'warning',
                'message': f'{past_due_businesses} negocio(s) con pago pendiente',
            })
        if urgent_unassigned > 0:
            alerts.append({
                'type': 'error',
                'message': f'{urgent_unassigned} ticket(s) urgente(s) sin asignar',
            })
        if not alerts:
            alerts.append({
                'type': 'info',
                'message': 'Sin alertas operativas',
            })

        return Response({
            'kpis': {
                'active_businesses': active_businesses,
                'trial_businesses': trial_businesses,
                'past_due_businesses': past_due_businesses,
                'total_users': total_users,
            },
            'ticket_kpis': ticket_kpis,
            'alerts': alerts,
            'recent_activity': [
                {
                    'id': entry['id'],
                    'action': entry['action'],
                    'actor_email': entry['actor__email'] or 'Sistema',
                    'business_name': entry['business__name'] or '—',
                    'entity_type': entry['entity_type'],
                    'entity_id': entry['entity_id'],
                    'created_at': entry['created_at'].isoformat() if entry['created_at'] else None,
                }
                for entry in recent_activity
            ],
            'recent_activity_count_24h': recent_activity_count,
        })

"""
Admin Reporting & Monitoring views (Phase 4).

Endpoints:
  GET /api/v1/platform-admin/reports/overview/   → full overview (KPIs + distributions + alerts + activity)
  GET /api/v1/platform-admin/reports/alerts/      → alerts only, optional ?severity=critical|warning

Role matrix:
┌──────────────────────────┬────────────┬────────────┬───────────────┬───────────────┐
│ Endpoint                 │ superadmin │ operations │ support_agent │ content_admin │
├──────────────────────────┼────────────┼────────────┼───────────────┼───────────────┤
│ reports/overview/        │     ✓      │     ✓      │       ✗       │       ✗       │
│ reports/alerts/          │     ✓      │     ✓      │       ✗       │       ✗       │
└──────────────────────────┴────────────┴────────────┴───────────────┴───────────────┘
"""
import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.platform_permissions import HasInternalRole, IsPlatformStaff
from apps.accounts.platform_admin_reporting import (
    get_distributions,
    get_global_kpis,
    get_operational_alerts,
    get_recent_activity,
)
from apps.accounts.platform_audit import log_platform_action

logger = logging.getLogger(__name__)


class AdminReportingOverviewView(APIView):
    """
    GET /api/v1/platform-admin/reports/overview/

    Returns platform-wide overview: KPIs, distributions, alerts, recent activity.
    Single endpoint to minimize round-trips from the frontend.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def get(self, request: Request) -> Response:
        kpis = get_global_kpis()
        distributions = get_distributions()
        alerts = get_operational_alerts()
        activity = get_recent_activity(limit=15)

        log_platform_action(
            action='ADMIN_REPORT_VIEWED',
            actor=request.user,
            entity_type='report',
            entity_id='overview',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        return Response({
            'kpis': kpis,
            'distributions': distributions,
            'alerts': alerts,
            'recent_activity': activity,
        })


class AdminReportingAlertsView(APIView):
    """
    GET /api/v1/platform-admin/reports/alerts/
    GET /api/v1/platform-admin/reports/alerts/?severity=critical

    Returns only operational alerts, with optional severity filter.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def get(self, request: Request) -> Response:
        severity = request.query_params.get('severity')
        if severity and severity not in ('critical', 'warning'):
            severity = None

        alerts = get_operational_alerts(severity=severity)

        log_platform_action(
            action='ADMIN_ALERTS_VIEWED',
            actor=request.user,
            entity_type='report',
            entity_id='alerts',
            details={'severity_filter': severity},
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        return Response({
            'alerts': alerts,
            'total': len(alerts),
            'critical_count': sum(1 for a in alerts if a['severity'] == 'critical'),
            'warning_count': sum(1 for a in alerts if a['severity'] == 'warning'),
        })

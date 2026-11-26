"""PROD-02E3B — Platform Admin, read-only commercial AI usage of a client.

  GET /api/v1/platform-admin/clients/<business_id>/ai-usage/
  GET /api/v1/platform-admin/clients/<business_id>/ai-usage/history/?limit=&offset=
  GET /api/v1/platform-admin/clients/<business_id>/ai-usage/policies/?limit=&offset=

Access: platform staff (`AccountProfile.is_platform_staff`) with internal role
`superadmin` or `operations` — the roles that already see clients and
subscriptions. A merchant owner/admin (Membership) never qualifies: these views
do not read memberships at all. Business is a client HQ (same rule as the
client detail). No `now`/`at` parameters: server time only. Strictly
read-only (no sessions, charges, policies, subscription or audit writes; the
view itself does not log an access audit entry so it stays write-free).
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.platform_permissions import HasInternalRole, IsPlatformStaff
from apps.billing.services.ai_usage_admin import (
    CHANGES_DEFAULT_LIMIT, CHANGES_MAX_LIMIT, HISTORY_DEFAULT_LIMIT, HISTORY_MAX_LIMIT,
    admin_ai_usage_history, admin_ai_usage_overview, admin_reception_policies, clamp, offset_of,
)
from apps.business.models import Business


class _AdminAIUsageView(APIView):
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def business(self, business_id):
        return Business.objects.filter(pk=business_id, parent__isnull=True).first()

    def respond(self, business_id, build):
        business = self.business(business_id)
        if business is None:
            response = Response({'detail': 'Cliente no encontrado.'}, status=404)
        else:
            response = Response(build(business))
        response['Cache-Control'] = 'no-store'
        return response


class AdminClientAIUsageView(_AdminAIUsageView):

    def get(self, request, business_id: int):
        return self.respond(business_id, admin_ai_usage_overview)


class AdminClientAIUsageHistoryView(_AdminAIUsageView):

    def get(self, request, business_id: int):
        limit = clamp(request.query_params.get('limit'), HISTORY_DEFAULT_LIMIT, HISTORY_MAX_LIMIT)
        offset = offset_of(request.query_params.get('offset'))
        return self.respond(business_id, lambda b: admin_ai_usage_history(b, limit=limit, offset=offset))


class AdminClientAIPoliciesView(_AdminAIUsageView):

    def get(self, request, business_id: int):
        limit = clamp(request.query_params.get('limit'), CHANGES_DEFAULT_LIMIT, CHANGES_MAX_LIMIT)
        offset = offset_of(request.query_params.get('offset'))
        return self.respond(business_id, lambda b: admin_reception_policies(b, limit=limit, offset=offset))


class AdminClientOperationalMetricsView(_AdminAIUsageView):
    """PROD-02E4D: GET .../clients/<id>/operational-metrics/?date_from=&date_to=

    OpenAI activity + estimated costs, WhatsApp activity and commercial AI
    sessions of the period, as independent blocks (see
    apps.leads.services.operational_metrics). Same roles, HQ rule, server
    time, no-store and zero writes as the AI usage views.
    """

    def get(self, request, business_id: int):
        from apps.leads.services.operational_metrics import OperationalMetricsRangeError, operational_metrics

        business = self.business(business_id)
        if business is None:
            response = Response({'detail': 'Cliente no encontrado.'}, status=404)
        else:
            try:
                response = Response(operational_metrics(
                    business, request.query_params.get('date_from'), request.query_params.get('date_to'),
                ))
            except OperationalMetricsRangeError as exc:
                response = Response({'code': 'invalid_period', 'detail': str(exc)}, status=400)
        response['Cache-Control'] = 'no-store'
        return response

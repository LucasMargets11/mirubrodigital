"""PROD-02E3A — `GET /api/v1/ai-usage/`: the merchant's commercial AI consumption.

Product-neutral (Recepcionista IA or Turnos IA, whichever is the Business's
single AI source). Read-only: no sessions, charges, receipts, policy changes,
renewals or settlements; no caller-controlled instant (server time only).

Access: authenticated user, valid membership of the Business resolved from the
authenticated context (never a query parameter), effective `view_ai_usage`
(owner/admin by default; PROD-02C capability owner), and a contracted AI
service — no AI subscription at all answers 403 `ai_service_not_contracted`.
Billing enforcement is bypassed on purpose so a suspended merchant gets an
explicit `suspended` status instead of a generic block (read-only, own tenant).
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from apps.billing.services.ai_usage_summary import NOT_CONTRACTED, get_ai_usage_summary


class AIUsageSummaryView(APIView):
    http_method_names = ['get', 'head', 'options']
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
    required_permission = 'view_ai_usage'
    billing_enforcement_bypass = True

    def get(self, request):
        summary = get_ai_usage_summary(request.business)
        if summary['status'] == NOT_CONTRACTED:
            return Response(
                {'code': 'ai_service_not_contracted', 'message': 'El negocio no tiene un servicio de IA contratado.'},
                status=403,
            )
        response = Response(summary)
        response['Cache-Control'] = 'no-store'
        return response

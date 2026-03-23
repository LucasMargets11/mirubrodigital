"""
billing/cancellation_views.py — API views for subscription cancellation.

Endpoints:
  GET  /api/v1/billing/subscription-status/   → current subscription + plan info
  POST /api/v1/billing/cancel-subscription/    → schedule cancellation
  POST /api/v1/billing/undo-cancel/            → undo scheduled cancellation
"""
from __future__ import annotations

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership

from .cancellation_service import (
    CancellationError,
    schedule_cancellation,
    undo_cancellation,
)
from .commercial_plans import get_plan_config
from .models import Plan, SubscriptionV2
from .runtime import resolve_subscription, _extract_plan_tier

logger = logging.getLogger(__name__)


# ── Plan display names ──────────────────────────────────────────────────────
_PLAN_DISPLAY_NAMES: dict[str, str] = {
    'start': 'Start',
    'starter': 'Starter',
    'pro': 'Pro',
    'business': 'Business',
    'enterprise': 'Enterprise',
    'plus': 'Plus',
    'menu_qr': 'Menú QR',
    'menu_qr_visual': 'Menú QR Visual',
    'menu_qr_marca': 'Menú QR Marca',
    'menu_qr_lite': 'Menú QR Lite',
    'menu_qr_pro': 'Menú QR Pro',
    'menu_qr_premium': 'Menú QR Premium',
}


def _get_active_subscription_v2(business) -> SubscriptionV2 | None:
    """Return the active (non-canceled) SubscriptionV2 for a business."""
    service_type = business.service_type or business.default_service or 'gestion'
    return (
        SubscriptionV2.objects
        .filter(business=business, service_type=service_type)
        .exclude(status=SubscriptionV2.Status.CANCELED)
        .order_by('-created_at')
        .first()
    )


def _serialize_subscription_v2(sub: SubscriptionV2) -> dict:
    """Serialize a SubscriptionV2 for the frontend."""
    # Resolve plan name: DB Plan → commercial catalog → display-name map → raw code
    plan_name = sub.plan_code
    try:
        plan_obj = Plan.objects.filter(code=sub.plan_code).first()
        if plan_obj:
            plan_name = plan_obj.name
    except Exception:
        pass

    # Resolve plan limits from the commercial catalog
    plan_tier = _extract_plan_tier(sub.plan_code)
    plan_cfg = get_plan_config(plan_tier)
    max_seats = None
    max_branches = None
    if plan_cfg:
        # Use catalog name as fallback if DB Plan didn't resolve a friendly name
        if plan_name == sub.plan_code:
            plan_name = plan_cfg['name']
        max_seats = plan_cfg['limits']['seats_included']
        max_branches = plan_cfg['limits']['branches_included']
    else:
        # Final fallback for plan name
        fallback = _PLAN_DISPLAY_NAMES.get(plan_tier)
        if fallback and plan_name == sub.plan_code:
            plan_name = fallback

    cancel_effective_at = None
    if sub.cancel_at_period_end and sub.current_period_end:
        cancel_effective_at = sub.current_period_end.isoformat()

    return {
        'id': str(sub.pk),
        'plan_code': sub.plan_code,
        'plan_name': plan_name,
        'service_type': sub.service_type,
        'status': sub.status,
        'status_display': sub.get_status_display(),
        'provider': sub.provider,
        'current_period_start': sub.current_period_start.isoformat() if sub.current_period_start else None,
        'current_period_end': sub.current_period_end.isoformat() if sub.current_period_end else None,
        'cancel_at_period_end': sub.cancel_at_period_end,
        'cancel_requested_at': sub.cancel_requested_at.isoformat() if sub.cancel_requested_at else None,
        'cancel_effective_at': cancel_effective_at,
        'cancel_reason': sub.cancel_reason or '',
        'canceled_at': sub.canceled_at.isoformat() if sub.canceled_at else None,
        'is_active': sub.is_active,
        'created_at': sub.created_at.isoformat(),
        'source': 'v2',
        'can_manage_cancellation': sub.status not in SubscriptionV2.TERMINAL_STATUSES,
        'max_seats': max_seats,
        'max_branches': max_branches,
    }


def _serialize_resolved(resolved) -> dict | None:
    """Serialize a ResolvedSubscription (V2 or legacy) for the frontend."""
    if resolved.source == 'none' or not resolved.access_granted:
        return None

    # V2 subscription — use the rich serializer
    if resolved.subscription_v2 is not None:
        return _serialize_subscription_v2(resolved.subscription_v2)

    # Legacy subscription — build a compatible shape
    legacy = resolved.legacy_sub
    if legacy is None:
        return None

    plan_code = getattr(legacy, 'plan', 'start')
    plan_name = _PLAN_DISPLAY_NAMES.get(plan_code, plan_code.replace('_', ' ').title())
    renews_at = getattr(legacy, 'renews_at', None)

    return {
        'id': str(legacy.pk),
        'plan_code': plan_code,
        'plan_name': plan_name,
        'service_type': getattr(legacy, 'service', resolved.service_type or 'gestion'),
        'status': resolved.status or 'active',
        'status_display': 'Activo' if resolved.status == 'active' else (resolved.status or '').replace('_', ' ').title(),
        'provider': 'legacy',
        'current_period_start': None,
        'current_period_end': renews_at.isoformat() if renews_at else None,
        'cancel_at_period_end': False,
        'cancel_requested_at': None,
        'cancel_effective_at': None,
        'cancel_reason': '',
        'canceled_at': None,
        'is_active': True,
        'created_at': legacy.created_at.isoformat() if hasattr(legacy, 'created_at') and legacy.created_at else None,
        'source': 'legacy',
        'can_manage_cancellation': False,
        'max_seats': getattr(legacy, 'max_seats', None),
        'max_branches': getattr(legacy, 'max_branches', None),
    }


class SubscriptionStatusView(APIView):
    """
    GET /api/v1/billing/subscription-status/

    Returns the current subscription status and plan information for the
    authenticated user's business. Accessible by any authenticated member.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    billing_enforcement_bypass = True

    def get(self, request):
        membership = resolve_request_membership(request)
        if not membership:
            return Response(
                {'detail': 'No se encontró membresía.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        business = membership.business
        resolved = resolve_subscription(business)
        sub_data = _serialize_resolved(resolved)

        if not sub_data:
            return Response({
                'has_subscription': False,
                'subscription': None,
                'role': membership.role,
            })

        return Response({
            'has_subscription': True,
            'subscription': sub_data,
            'role': membership.role,
        })


class CancelSubscriptionView(APIView):
    """
    POST /api/v1/billing/cancel-subscription/

    Schedule the cancellation of the current subscription.
    Only the OWNER can perform this action.

    Body (optional):
        { "reason": "string" }
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    billing_enforcement_bypass = True

    def post(self, request):
        membership = resolve_request_membership(request)
        if not membership:
            return Response(
                {'detail': 'No se encontró membresía.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if membership.role != 'owner':
            return Response(
                {'detail': 'Solo el propietario puede cancelar la suscripción.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        business = membership.business
        sub = _get_active_subscription_v2(business)

        if not sub:
            return Response(
                {'detail': 'No hay suscripción activa para cancelar.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        reason = (request.data.get('reason') or '').strip()[:255]

        try:
            sub = schedule_cancellation(sub, reason=reason)
        except CancellationError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "[cancel-subscription] Cancellation scheduled by user=%s business=%s sub=%s",
            request.user.pk, business.pk, sub.pk,
        )

        return Response({
            'detail': 'Baja programada correctamente.',
            'subscription': _serialize_subscription_v2(sub),
        })


class UndoCancelSubscriptionView(APIView):
    """
    POST /api/v1/billing/undo-cancel/

    Undo a scheduled cancellation.
    Only the OWNER can perform this action.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    billing_enforcement_bypass = True

    def post(self, request):
        membership = resolve_request_membership(request)
        if not membership:
            return Response(
                {'detail': 'No se encontró membresía.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if membership.role != 'owner':
            return Response(
                {'detail': 'Solo el propietario puede revertir la cancelación.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        business = membership.business
        sub = _get_active_subscription_v2(business)

        if not sub:
            return Response(
                {'detail': 'No hay suscripción activa.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            sub = undo_cancellation(sub)
        except CancellationError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "[undo-cancel] Cancellation undone by user=%s business=%s sub=%s",
            request.user.pk, business.pk, sub.pk,
        )

        return Response({
            'detail': 'La baja fue revertida exitosamente.',
            'subscription': _serialize_subscription_v2(sub),
        })

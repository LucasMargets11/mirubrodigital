"""
reviews_views.py — In-place upgrade / downgrade endpoints for QR de Reseñas.

Upgrade (Base → Pro):
  POST /api/v1/billing/reviews/upgrade/  → create MP preference, return checkout_url

Downgrade (Pro → Base):
  POST /api/v1/billing/reviews/downgrade/ → immediate plan change, no payment

Webhook handling:
  The existing MercadoPagoWebhookView.process_payment_event recognises the
  ``reviews_upgrade_`` external-reference prefix and calls
  ``apply_reviews_plan_upgrade()`` on approved payment.
"""
from __future__ import annotations

import logging
import uuid as _uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership
from apps.business.models import Business
from .canonical_pricing import plan_price
from .models import PendingSubscriptionChange, SubscriptionV2
from .mp_service import MercadoPagoService

logger = logging.getLogger(__name__)

# Plans eligible for in-place upgrade to Pro.
_UPGRADEABLE_PLANS = frozenset({'qr_reviews', 'qr_reviews_base'})
_TARGET_PLAN = 'qr_reviews_pro'

# Plans eligible for downgrade back to Base.
_DOWNGRADEABLE_PLANS = frozenset({'qr_reviews_pro'})
_BASE_PLAN = 'qr_reviews_base'


class ReviewsUpgradeView(APIView):
    """Initiate upgrade from qr_reviews_base → qr_reviews_pro."""

    permission_classes = [IsAuthenticated, HasBusinessMembership]
    billing_enforcement_bypass = True

    def post(self, request):
        business: Business = getattr(request, 'business', None)
        if not business:
            return Response({'detail': 'Business not found'}, status=status.HTTP_404_NOT_FOUND)

        # Only the owner can manage billing.
        membership = request.user.memberships.filter(business=business).first()
        if not membership or membership.role != 'owner':
            return Response(
                {'detail': 'Solo el propietario puede cambiar el plan.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Verify current plan is base.
        subscription = getattr(business, 'subscription', None)
        if subscription is None:
            return Response(
                {'detail': 'No se encontró suscripción activa.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_plan = getattr(subscription, 'plan', '')
        if current_plan not in _UPGRADEABLE_PLANS:
            if current_plan == _TARGET_PLAN:
                return Response({'detail': 'Ya tenés el plan Reseñas Pro.'}, status=status.HTTP_409_CONFLICT)
            return Response(
                {'detail': 'Solo se puede actualizar desde Reseñas Base.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------- Idempotency: reuse existing pending change if any ----------
        existing_pending = (
            PendingSubscriptionChange.objects
            .filter(
                business=business,
                target_plan_code=_TARGET_PLAN,
                status='pending_payment',
            )
            .order_by('-created_at')
            .first()
        )
        if existing_pending and existing_pending.mp_init_point:
            return Response({
                'pending_change_id': existing_pending.id,
                'checkout_url': existing_pending.mp_init_point,
                'message': 'Actualización a Reseñas Pro',
            })

        # ---------- Pricing from canonical source ----------
        price = plan_price(_TARGET_PLAN, 'monthly')

        line_items = [{
            'description': 'Reseñas Pro — Mensual',
            'quantity': 1,
            'unit_price': price,
            'total': price,
            'is_recurring': True,
        }]

        pending = PendingSubscriptionChange.objects.create(
            business=business,
            user=request.user,
            target_plan_code=_TARGET_PLAN,
            billing_cycle='monthly',
            config_snapshot={},
            line_items=line_items,
            total_amount=price,
            requires_checkout=True,
            is_upgrade=True,
            status='pending_payment',
        )

        # ---------- MercadoPago preference ----------
        try:
            mp_service = MercadoPagoService()
            base_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            back_urls = {
                'success': f'{base_url}/app/resenas?upgrade=success&change_id={pending.id}',
                'failure': f'{base_url}/app/resenas?upgrade=failure&change_id={pending.id}',
                'pending': f'{base_url}/app/resenas?upgrade=pending&change_id={pending.id}',
            }

            preference = mp_service.create_preference(
                items=[{
                    'title': 'Reseñas Pro — Mensual',
                    'quantity': 1,
                    'unit_price': float(price),
                    'currency_id': 'ARS',
                }],
                external_reference=f'reviews_upgrade_{pending.id}',
                back_urls=back_urls,
                metadata={
                    'business_id': business.id,
                    'pending_change_id': pending.id,
                    'plan_code': _TARGET_PLAN,
                },
            )

            pending.mp_preference_id = preference.get('id')
            pending.mp_init_point = preference.get('init_point')
            pending.save()

            return Response({
                'pending_change_id': pending.id,
                'checkout_url': preference.get('init_point'),
                'message': 'Actualización a Reseñas Pro',
            })
        except Exception as exc:
            logger.error('[ReviewsUpgrade] MP preference creation failed: %s', exc)
            pending.status = 'failed'
            pending.save()
            return Response(
                {'detail': 'No pudimos iniciar el pago. Intentalo de nuevo.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )


# ── Apply helper (called by webhook) ──────────────────────────────────────────

def apply_reviews_plan_upgrade(business: Business, target_plan_code: str) -> None:
    """
    Apply a QR Reviews plan upgrade.

    Updates the legacy business.Subscription.plan AND syncs SubscriptionV2.
    Called by the webhook handler when a ``reviews_upgrade_`` payment is approved.
    """
    with transaction.atomic():
        sub = business.subscription
        sub.plan = target_plan_code
        sub.save(update_fields=['plan', 'updated_at'])
        logger.info(
            '[apply_reviews_plan_upgrade] business=%s plan updated to %s',
            business.id, target_plan_code,
        )

    # ── Sync SubscriptionV2 (non-fatal) ──────────────────────────────────
    try:
        v2 = (
            SubscriptionV2.objects
            .filter(business=business, service_type='qr_reviews')
            .exclude(status=SubscriptionV2.Status.CANCELED)
            .first()
        )
        if v2:
            v2.plan_code = target_plan_code
            v2.status = SubscriptionV2.Status.ACTIVE
            v2.save(update_fields=['plan_code', 'status', 'updated_at'])
            logger.info('[apply_reviews_plan_upgrade] Synced SubscriptionV2 %s', v2.pk)
        else:
            SubscriptionV2.objects.create(
                business=business,
                service_type='qr_reviews',
                plan_code=target_plan_code,
                provider=SubscriptionV2.Provider.MERCADOPAGO,
                external_reference=f'SUB-{_uuid.uuid4()}',
                status=SubscriptionV2.Status.ACTIVE,
            )
            logger.info('[apply_reviews_plan_upgrade] Created SubscriptionV2 for business=%s', business.pk)
    except Exception as exc:
        logger.warning('[apply_reviews_plan_upgrade] V2 sync failed (non-fatal): %s', exc)


# ── Downgrade view ─────────────────────────────────────────────────────────────

class ReviewsDowngradeView(APIView):
    """Downgrade from qr_reviews_pro → qr_reviews_base (immediate, no payment)."""

    permission_classes = [IsAuthenticated, HasBusinessMembership]
    billing_enforcement_bypass = True

    def post(self, request):
        business: Business = getattr(request, 'business', None)
        if not business:
            return Response({'detail': 'Business not found'}, status=status.HTTP_404_NOT_FOUND)

        # Only the owner can manage billing.
        membership = request.user.memberships.filter(business=business).first()
        if not membership or membership.role != 'owner':
            return Response(
                {'detail': 'Solo el propietario puede cambiar el plan.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        subscription = getattr(business, 'subscription', None)
        if subscription is None:
            return Response(
                {'detail': 'No se encontró suscripción activa.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        current_plan = getattr(subscription, 'plan', '')
        if current_plan not in _DOWNGRADEABLE_PLANS:
            if current_plan in _UPGRADEABLE_PLANS:
                return Response(
                    {'detail': 'Ya estás en el plan Reseñas Base.'},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(
                {'detail': 'No se puede hacer downgrade desde este plan.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Require explicit confirmation.
        if not request.data.get('confirm'):
            return Response(
                {'detail': 'Se requiere confirmación explícita.', 'requires_confirm': True},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Apply immediately.
        apply_reviews_plan_downgrade(business, _BASE_PLAN, user=request.user)

        return Response({
            'plan': _BASE_PLAN,
            'previous_plan': current_plan,
            'message': 'Tu plan volvió a Reseñas Base.',
        })


def apply_reviews_plan_downgrade(
    business: Business,
    target_plan_code: str,
    *,
    user=None,
) -> None:
    """
    Apply a QR Reviews plan downgrade.

    Updates legacy business.Subscription.plan AND syncs SubscriptionV2.
    Immediate — no payment, no scheduling.

    The ReviewConfig.mode is NOT changed; ``effective_mode`` property already
    falls back to ``direct`` when ``smart_filter_allowed`` returns False.
    Historical data (reviews, feedback) is preserved.
    """
    with transaction.atomic():
        sub = business.subscription
        previous_plan = sub.plan
        sub.plan = target_plan_code
        sub.save(update_fields=['plan', 'updated_at'])
        logger.info(
            '[apply_reviews_plan_downgrade] business=%s plan %s → %s',
            business.id, previous_plan, target_plan_code,
        )

        # Record the change for audit purposes.
        PendingSubscriptionChange.objects.create(
            business=business,
            user=user,
            target_plan_code=target_plan_code,
            billing_cycle='monthly',
            config_snapshot={'previous_plan': previous_plan},
            line_items=[],
            total_amount=0,
            requires_checkout=False,
            is_downgrade=True,
            status='completed',
        )

    # ── Sync SubscriptionV2 (non-fatal) ──────────────────────────────────
    try:
        v2 = (
            SubscriptionV2.objects
            .filter(business=business, service_type='qr_reviews')
            .exclude(status=SubscriptionV2.Status.CANCELED)
            .first()
        )
        if v2:
            v2.plan_code = target_plan_code
            v2.save(update_fields=['plan_code', 'updated_at'])
            logger.info('[apply_reviews_plan_downgrade] Synced SubscriptionV2 %s', v2.pk)
    except Exception as exc:
        logger.warning('[apply_reviews_plan_downgrade] V2 sync failed (non-fatal): %s', exc)

"""
accounts/onboarding_views.py — Authenticated onboarding step endpoints.

These endpoints power the in-app onboarding funnel introduced in Wave 3:

  Step 1  GET  /api/v1/auth/onboarding/        → OnboardingStatusView
  Step 2  POST /api/v1/auth/onboarding/set-service/ → OnboardingSetServiceView

Both views require authentication but explicitly bypass billing enforcement so
they are always reachable regardless of subscription state.  They also bypass
the email-verification gate because a user who hasn't verified email yet must
still be able to see which step they are on (and be prompted to verify).

For onboarding purposes the "business" is resolved directly from the user's
first membership rather than through the full resolve_request_membership()
path, so the rollout.NEW_ONBOARDING flag can be checked before full membership
resolution is needed.

Flow summary
------------
1. Login returns {onboarding: true} when business.status == 'onboarding'.
2. Frontend navigates to /app/onboarding/servicio.
3. servicio page: GET /auth/onboarding/ to confirm step, then renders service selector.
4. User picks service_type → POST /auth/onboarding/set-service/   
5. Frontend navigates to /app/onboarding/plan.
6. plan page: GET /billing/modules/?vertical=<service_type> for plan catalog.
7. User picks plan → frontend navigates to /app/servicios?plan=<code> (billing hub handles checkout).
8. After checkout, webhook activates business → status='active'|'trialing'.
9. Next /auth/me/ call returns updated status; frontend routes to /app.
"""
from __future__ import annotations

import logging
from typing import Dict

from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from apps.accounts.models import AccessAuditLog, Membership
from apps.accounts.permissions import RequiresEmailVerified
from apps.accounts.rollout import rollout
from apps.business.models import Business

logger = logging.getLogger(__name__)
User = get_user_model()

# ── Service type validation ────────────────────────────────────────────────────
VALID_SERVICE_TYPES = frozenset(['gestion', 'restaurante', 'menu_qr', 'qr_reviews'])

# ── Onboarding step computation ────────────────────────────────────────────────

def _compute_onboarding_step(business: Business) -> str:
    """
    Return the current onboarding step key for a business.

    Steps (ordered, mutually exclusive):
      'no_service_type'  — service_type not yet selected by the user
      'plan_selection'   — service_type confirmed; user hasn't started checkout
      'checkout_pending' — checkout in flight (MpCheckoutSession / SubscriptionV2
                           CHECKOUT_PENDING exists); awaiting payment confirmation
      'done'             — business has left onboarding state (status != 'onboarding')

    Note: 'no_email_verification' is surfaced via can_proceed=False in the
    status response rather than as a separate step, because unverified users
    can still browse steps 1 and 2.  The gate fires at checkout initiation.
    """
    if business.status != 'onboarding':
        return 'done'

    # Fast path: if an active SubscriptionV2 already exists for this business,
    # the activation webhook arrived and set is_active=True on the subscription
    # but (due to a partial failure or race) didn't flip Business.status.
    # Heal it in-place so the user gets routed to /app on the next page load,
    # and report 'done' so the frontend redirects immediately.
    try:
        from apps.billing.models import SubscriptionV2
        active_sub = SubscriptionV2.objects.filter(
            business=business, is_active=True,
        ).first()
        if active_sub:
            from django.utils import timezone as _tz
            updated = Business.objects.filter(
                pk=business.pk, status='onboarding',
            ).update(status='active', activated_at=_tz.now())
            if updated:
                logger.warning(
                    "[onboarding] Healed Business %s status onboarding→active "
                    "(active SubscriptionV2 %s already existed — partial write detected).",
                    business.pk, active_sub.pk,
                )
            return 'done'
    except Exception as exc:
        logger.warning("[onboarding] Active-sub check failed for business=%s: %s", business.pk, exc)

    # A CHECKOUT_PENDING SubscriptionV2 or open MpCheckoutSession means the
    # user has already initiated the MP payment flow and is waiting for a
    # webhook confirmation.
    if _has_pending_checkout(business):
        return 'checkout_pending'

    # service_type is the canonical user-selected field (set by set-service).
    # default_service is a legacy fallback that defaults to 'gestion' for all
    # new businesses — it does NOT indicate an explicit user choice.
    if business.service_type:
        return 'plan_selection'

    return 'no_service_type'


def _has_pending_checkout(business: Business) -> bool:
    """
    Return True if this business has an in-flight checkout that hasn't activated yet.

    Checks (in order):
      1. A CHECKOUT_PENDING SubscriptionV2 — webhooks have already fired and
         linked a subscription but payment has not yet been confirmed.
      2. An open MpCheckoutSession (created / checkout_created / awaiting_webhook
         / linked) — covers the window after the user is redirected to MP but
         before the subscription_preapproval webhook arrives.

    Both conditions are considered "checkout_pending" from the user's perspective
    so the onboarding funnel shows the payment-in-progress screen.
    """
    try:
        from apps.billing.models import MpCheckoutSession, SubscriptionV2
        if SubscriptionV2.objects.filter(
            business=business,
            status=SubscriptionV2.Status.CHECKOUT_PENDING,
        ).exists():
            return True
        # Fallback: open checkout session that hasn't produced a SubscriptionV2 yet.
        return MpCheckoutSession.objects.filter(
            tenant=business,
            status__in=MpCheckoutSession.OPEN_STATUSES,
        ).exists()
    except Exception:
        return False


def _get_pending_checkout_info(business: Business) -> Dict[str, str] | None:
    """
    When step is 'checkout_pending', return {checkout_session_id, plan_code}.

    Lookup order:
      1. Most recent CHECKOUT_PENDING SubscriptionV2 → its checkout_session
      2. Most recent open MpCheckoutSession on the business (fallback)

    Returns None if no open session is found.
    """
    try:
        from apps.billing.models import MpCheckoutSession, SubscriptionV2

        # Primary: via SubscriptionV2 → checkout_session
        v2 = (
            SubscriptionV2.objects
            .select_related('checkout_session', 'checkout_session__plan')
            .filter(business=business, status=SubscriptionV2.Status.CHECKOUT_PENDING)
            .order_by('-created_at')
            .first()
        )
        if v2 and v2.checkout_session:
            sess = v2.checkout_session
            plan_code = sess.plan.code if sess.plan else v2.plan_code or ''
            return {
                'checkout_session_id': str(sess.id),
                'plan_code': plan_code,
            }

        # Fallback: open MpCheckoutSession directly on the tenant
        sess = (
            MpCheckoutSession.objects
            .select_related('plan')
            .filter(tenant=business, status__in=MpCheckoutSession.OPEN_STATUSES)
            .order_by('-created_at')
            .first()
        )
        if sess:
            return {
                'checkout_session_id': str(sess.id),
                'plan_code': sess.plan.code if sess.plan else '',
            }

        return None
    except Exception as exc:
        logger.warning(
            "[onboarding] _get_pending_checkout_info failed for business=%s: %s",
            business.pk, exc,
        )
        return None


def _resolve_onboarding_business(user) -> Business | None:
    """
    Return the onboarding business for this user.

    Uses the user's first membership ordered by creation date.  If a user has
    multiple memberships (rare in onboarding context), returns the first one
    found with status='onboarding' — otherwise returns None.
    """
    membership = (
        Membership.objects
        .select_related('business')
        .filter(user=user)
        .order_by('id')
        .first()
    )
    if membership is None:
        return None
    return membership.business


# ── Views ──────────────────────────────────────────────────────────────────────


class OnboardingStatusView(APIView):
    """
    GET /api/v1/auth/onboarding/

    Returns the current onboarding state for the authenticated user.

    Response:
        {
            "business_status": "onboarding",
            "step": "no_service_type",       // or "checkout_pending" | "done"
            "service_type": null,            // the selected service, if any
            "email_verified": true,
            "can_proceed": true,             // false if email not verified
            "rollout_active": true           // NEW_ONBOARDING flag value
        }

    'done' means the business is no longer in onboarding; frontend should
    redirect to /app.
    """
    permission_classes = [IsAuthenticated]
    billing_enforcement_bypass = True
    email_verification_bypass = True

    def get(self, request: Request) -> Response:
        business = _resolve_onboarding_business(request.user)
        if business is None:
            return Response(
                {'detail': 'No business found for this user.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        profile = getattr(request.user, 'account_profile', None)
        email_verified = profile.email_verified if profile else False

        step = _compute_onboarding_step(business)

        # For checkout_pending step, expose session + plan so the frontend can
        # resume the payment flow without re-initiating a new MP checkout.
        checkout_info: Dict | None = None
        if step == 'checkout_pending':
            checkout_info = _get_pending_checkout_info(business)

        return Response({
            'business_status': business.status,
            'step': step,
            'service_type': business.service_type,
            'email_verified': email_verified,
            # can_proceed: email must be verified before checkout can be initiated.
            # Users CAN navigate steps 1 and 2 while unverified; the gate fires
            # at /auth/onboarding/start-checkout/ (RequiresEmailVerified on that view).
            'can_proceed': email_verified,
            'rollout_active': rollout.is_enabled(rollout.NEW_ONBOARDING),
            # checkout_pending context — only non-null when step='checkout_pending'
            'checkout_session_id': checkout_info['checkout_session_id'] if checkout_info else None,
            'pending_plan_code':   checkout_info['plan_code'] if checkout_info else None,
        })


class OnboardingSetServiceView(APIView):
    """
    POST /api/v1/auth/onboarding/set-service/

    Saves the user's service_type selection during onboarding step 1.

    Body:
        {"service_type": "gestion" | "restaurante" | "menu_qr"}

    Validation:
      - business.status must be 'onboarding' (cannot change service after activation)
      - service_type must be one of VALID_SERVICE_TYPES

    Response:
        {
            "status": "ok",
            "service_type": "gestion",
            "next_step": "plan_selection"
        }

    Audit: logs ONBOARDING_SERVICE_SELECTED to AccessAuditLog.
    """
    permission_classes = [IsAuthenticated]
    billing_enforcement_bypass = True
    email_verification_bypass = True

    def post(self, request: Request) -> Response:
        service_type = request.data.get('service_type', '').strip().lower()

        if not service_type:
            return Response(
                {'detail': 'service_type es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if service_type not in VALID_SERVICE_TYPES:
            return Response(
                {
                    'detail': f"service_type inválido. Opciones válidas: {sorted(VALID_SERVICE_TYPES)}",
                    'code': 'invalid_service_type',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        business = _resolve_onboarding_business(request.user)
        if business is None:
            return Response(
                {'detail': 'No business found for this user.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if business.status != 'onboarding':
            return Response(
                {
                    'detail': 'El tipo de servicio solo puede cambiarse durante el onboarding.',
                    'code': 'business_not_in_onboarding',
                    'business_status': business.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        previous_service = business.service_type

        # Write canonical service_type + keep default_service in sync for
        # backward compatibility with legacy resolve paths.
        business.service_type = service_type
        business.default_service = service_type
        business.save(update_fields=['service_type', 'default_service'])

        # Audit log (best-effort; failure must not block the response).
        try:
            AccessAuditLog.objects.create(
                action='ONBOARDING_SERVICE_SELECTED',
                actor=request.user,
                target_user=request.user,
                business=business,
                actor_type='USER',
                entity_type='Business',
                entity_id=str(business.pk),
                before_json={'service_type': previous_service},
                after_json={'service_type': service_type},
            )
        except Exception as exc:
            logger.warning(
                "[onboarding] Failed to write audit log for ONBOARDING_SERVICE_SELECTED "
                "user=%s business=%s: %s",
                request.user.pk, business.pk, exc,
            )

        logger.info(
            "[onboarding] Service selected: user=%s business=%s service_type=%s",
            request.user.pk, business.pk, service_type,
        )

        return Response({
            'status': 'ok',
            'service_type': service_type,
            'next_step': 'plan_selection',
        })


class OnboardingStartCheckoutView(APIView):
    """
    POST /api/v1/auth/onboarding/start-checkout/

    Wave 4 — Initiate MP checkout for an onboarding business.

    This is the canonical in-app checkout initiation endpoint for new users
    going through the guided onboarding funnel.  It delegates to the
    idempotent checkout_session_service so double-submits, browser refreshes,
    and frontend retries are all safe.

    Preconditions
    -------------
    - User must be authenticated (IsAuthenticated).
    - Email must be verified (RequiresEmailVerified — no-op while
      ROLLOUT_EMAIL_VERIFICATION flag is False).
    - business.status must be 'onboarding'.
    - business.service_type must be set (POST set-service was called).
    - plan_code must match an active Plan entry.

    Body
    ----
    {"plan_code": "start"}

    Response (200 or 201)
    -----
    {
        "checkout_session_id": "<uuid>",
        "init_point": "<mercadopago_checkout_url>",
        "status": "checkout_created",
        "reused": false
    }

    Errors
    ------
    400 — Missing/invalid plan_code, or service_type not yet selected.
    403 — Email not verified (when ROLLOUT_EMAIL_VERIFICATION is on).
    404 — No business found for this user.
    409 — Business has already left onboarding (already active).
    503 — MP API error during checkout session creation.

    Audit
    -----
    Writes ONBOARDING_CHECKOUT_STARTED to AccessAuditLog (best-effort).
    """
    permission_classes = [IsAuthenticated, RequiresEmailVerified]
    billing_enforcement_bypass = True
    # email_verification_bypass is intentionally NOT set here — this view
    # is the gate that requires email verification before MP checkout can start.

    def post(self, request: Request) -> Response:
        from apps.billing.checkout_session_service import start_checkout
        from django.conf import settings as django_settings

        business = _resolve_onboarding_business(request.user)
        if business is None:
            return Response(
                {'detail': 'No business found for this user.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if business.status != 'onboarding':
            # Business has already completed onboarding (activated by a previous
            # webhook).  Frontend should redirect to /app.
            return Response(
                {
                    'detail': 'Tu cuenta ya está activa.',
                    'code': 'already_active',
                    'business_status': business.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        if not business.service_type:
            return Response(
                {
                    'detail': 'Elegí un tipo de servicio antes de iniciar el pago.',
                    'code': 'no_service_type',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan_code = (request.data.get('plan_code') or '').strip()
        if not plan_code:
            return Response(
                {'detail': 'plan_code es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Optional promotional code — normalised to uppercase, None if absent/blank.
        promo_code: str | None = (request.data.get('promo_code') or '').strip().upper() or None

        frontend_url = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000')

        try:
            result = start_checkout(
                user=request.user,
                tenant=business,
                plan_code=plan_code,
                frontend_url=frontend_url,
                promo_code=promo_code,
            )
        except ValueError as exc:
            # Invalid plan_code or business validation error from the service.
            return Response(
                {'detail': str(exc), 'code': 'invalid_plan'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception(
                "[OnboardingStartCheckoutView] start_checkout failed "
                "user=%s business=%s plan=%s: %s",
                request.user.pk, business.pk, plan_code, exc,
            )
            return Response(
                {'detail': 'No pudimos iniciar el pago. Intentalo nuevamente en unos segundos.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Audit log (best-effort; must not block the checkout response).
        try:
            AccessAuditLog.objects.create(
                action='ONBOARDING_CHECKOUT_STARTED',
                actor=request.user,
                target_user=request.user,
                business=business,
                actor_type='USER',
                entity_type='MpCheckoutSession',
                entity_id=result.get('checkout_session_id', ''),
                after_json={
                    'plan_code': plan_code,
                    'checkout_session_id': result.get('checkout_session_id'),
                    'reused': result.get('reused'),
                },
            )
        except Exception as exc:
            logger.warning(
                "[OnboardingStartCheckoutView] audit log failed (non-fatal) "
                "user=%s business=%s: %s",
                request.user.pk, business.pk, exc,
            )

        logger.info(
            "[OnboardingStartCheckoutView] Checkout initiated "
            "user=%s business=%s plan=%s session=%s reused=%s",
            request.user.pk, business.pk, plan_code,
            result.get('checkout_session_id'), result.get('reused'),
        )

        return Response(result, status=status.HTTP_200_OK)

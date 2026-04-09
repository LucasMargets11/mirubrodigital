"""
billing/checkout_session_service.py
=====================================
Idempotent "start subscription" service.

Design rationale
----------------
The central idempotency contract is:

    At most ONE open MpCheckoutSession per (user, plan) pair.

An "open" session is one in status: created / checkout_created /
awaiting_webhook / linked.

When a user double-clicks, the browser retries, or a frontend re-POSTs, this
service returns the *same* session and the *same* init_point instead of
hammering the MP plan API.

A new session is created only when:
  - No open session exists, OR
  - The only existing session is expired (→ marked expired, new one created)

Activation flow reminder
------------------------
This service does NOT activate the tenant or create a BillingSubscription.
Activation happens exclusively in subscription_activator.py, triggered by the
webhook processor after server-to-server verification with MP.

Correlation key index
---------------------
session.idempotency_key      = sha256(user.pk + ":" + plan.code)
session.mp_external_reference = "SESS-{uuid}"  (sent to MP, not used for lookup)
session.provider_preapproval_plan_id = MP plan template ID
  → used by webhook_processor to find the session from an inbound webhook
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import MpCheckoutSession, Plan

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model
    from apps.business.models import Business

    User = get_user_model()

logger = logging.getLogger(__name__)

# How long a session stays valid after creation without any MP confirmation.
# After this window, the session is considered expired on next access.
# The periodic task also expires sessions proactively.
CHECKOUT_SESSION_TTL_MINUTES = getattr(settings, 'CHECKOUT_SESSION_TTL_MINUTES', 60)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_idempotency_key(user_pk, plan_code: str, tenant_pk=None) -> str:
    """
    Deterministic, collision-resistant idempotency key.
    sha256(user_pk + ":" + tenant_pk + ":" + plan_code) — 64-char hex string.

    Including tenant_pk prevents cross-tenant collisions when a user owns
    multiple businesses and subscribes both to the same plan.
    For new signups where tenant_pk is unknown, pass None — the key will
    be scoped to (user, plan) only which is correct for that path.
    """
    raw = f"{user_pk}:{tenant_pk or ''}:{plan_code}"
    return hashlib.sha256(raw.encode()).hexdigest()


def start_checkout(
    *,
    user,
    tenant,
    plan_code: str,
    frontend_url: str | None = None,
) -> dict:
    """
    Idempotent entry point for starting a subscription checkout.

    Returns a dict::

        {
            "checkout_session_id": str(uuid),
            "init_point": str,
            "status": str,          # checkout_created
            "reused": bool,         # True if an existing session was returned
        }

    Raises ValueError for validation errors.
    Raises Exception if the MP API call fails.

    Thread safety
    -------------
    Uses ``select_for_update`` inside an atomic transaction to prevent
    concurrent requests for the same (user, plan) from creating duplicate
    sessions or duplicate MP plans.
    """
    try:
        plan = Plan.objects.get(code=plan_code, plan_status='active')
    except Plan.DoesNotExist:
        raise ValueError(f"Plan '{plan_code}' not found or inactive.")

    idempotency_key = build_idempotency_key(
        user.pk, plan_code, tenant_pk=getattr(tenant, 'pk', None)
    )

    with transaction.atomic():
        # Lock any open session for this (user, tenant, plan) to prevent race conditions.
        # Filtering by tenant avoids cross-business collisions for users that own
        # multiple tenants subscribed to the same plan.
        _open_filter: dict = dict(user=user, plan=plan, status__in=MpCheckoutSession.OPEN_STATUSES)
        if tenant is not None:
            _open_filter['tenant'] = tenant
        else:
            _open_filter['tenant__isnull'] = True

        existing = (
            MpCheckoutSession.objects
            .select_for_update()
            .filter(**_open_filter)
            .first()
        )

        if existing:
            if existing.is_expired():
                # Expire the stale session so a new one can be created.
                logger.info(
                    "[checkout_session] Session %s expired (expires_at=%s) — creating new one. "
                    "user=%s plan=%s",
                    existing.id, existing.expires_at, user.pk, plan_code,
                )
                existing.status = MpCheckoutSession.Status.EXPIRED
                existing.save(update_fields=['status', 'updated_at'])
                # Fall through to create a new session.
            else:
                # Reuse the existing open session.
                existing.last_seen_at = timezone.now()
                existing.save(update_fields=['last_seen_at', 'updated_at'])
                logger.info(
                    "[checkout_session] Reusing existing session %s "
                    "status=%s plan=%s user=%s",
                    existing.id, existing.status, plan_code, user.pk,
                )
                return {
                    "checkout_session_id": str(existing.id),
                    "init_point": existing.provider_checkout_url or '',
                    "status": existing.status,
                    "reused": True,
                }

        # ── Create a new checkout session ─────────────────────────────────────
        session_external_ref = f"SESS-{uuid.uuid4()}"
        expires_at = timezone.now() + timedelta(minutes=CHECKOUT_SESSION_TTL_MINUTES)

        session = MpCheckoutSession.objects.create(
            user=user,
            tenant=tenant,
            plan=plan,
            status=MpCheckoutSession.Status.CREATED,
            provider_mode=_detect_mode(),
            idempotency_key=idempotency_key,
            mp_external_reference=session_external_ref,
            return_url=_build_return_url(frontend_url),
            expires_at=expires_at,
            last_seen_at=timezone.now(),
        )

        logger.info(
            "[checkout_session] New session %s created user=%s plan=%s mode=%s",
            session.id, user.pk, plan_code, session.provider_mode,
        )

        # ── Create MP ephemeral plan ───────────────────────────────────────────
        # One plan per checkout session — this is intentional and specified in the design.
        # The plan ID is the primary correlation key between webhooks and the local session.
        try:
            session = _create_mp_plan_for_session(session, plan, frontend_url)
        except Exception as exc:
            session.status = MpCheckoutSession.Status.FAILED
            session.save(update_fields=['status', 'updated_at'])
            logger.error(
                "[checkout_session] MP plan creation failed for session=%s: %s",
                session.id, exc,
            )
            raise

    return {
        "checkout_session_id": str(session.id),
        "init_point": session.provider_checkout_url or '',
        "status": session.status,
        "reused": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _detect_mode() -> str:
    """Returns 'sandbox' if the MP token starts with 'TEST-', else 'prod'."""
    token = str(getattr(settings, 'MP_ACCESS_TOKEN', ''))
    return 'sandbox' if token.startswith('TEST-') else 'prod'


def _build_return_url(frontend_url: str | None) -> str:
    base = (frontend_url or getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')).rstrip('/')
    return f"{base}/subscribe/return"


def _build_back_url(session_id: str, frontend_url: str | None) -> str:
    """
    back_url sent to MP. When the user finishes the MP checkout (success,
    failure or pending), MP redirects them here.

    IMPORTANT: The frontend must NOT trust this redirect as a confirmation.
    It should poll GET /billing/checkout-sessions/:id instead.
    The checkout_session_id is included so the return page can begin polling.
    """
    base = (frontend_url or getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')).rstrip('/')
    return f"{base}/subscribe/return?checkout_session_id={session_id}"


def _create_mp_plan_for_session(
    session: MpCheckoutSession,
    plan: Plan,
    frontend_url: str | None,
) -> MpCheckoutSession:
    """
    Calls MP to create an ephemeral preapproval plan and persists the result.
    Returns the updated session.

    The plan is "ephemeral" in the sense that it is created specifically for
    this checkout session — not reused across sessions.  This is the only valid
    strategy for maintaining the 1-session : 1-plan-id correlation required for
    webhook traceability.
    """
    from .mp_service import MercadoPagoService
    from .canonical_pricing import assert_not_centavos, get_plan as get_canonical_plan

    mp = MercadoPagoService()

    # Guard: Plan.price must be in ARS pesos (not centavos).
    # Only enforced for plans present in the canonical pricing catalogue.
    # Restaurant / legacy plans are NOT yet canonical — skip guard to avoid
    # blocking their checkout flow (tracked as TODO Deploy 4).
    if get_canonical_plan(plan.code) is not None:
        assert_not_centavos(int(plan.price), f"Plan.price:{plan.code}")

    auto_recurring = {
        "frequency": plan.frequency,
        "frequency_type": plan.frequency_type,
        "transaction_amount": float(plan.price),  # ARS pesos → MP float
        "currency_id": plan.currency,
    }

    back_url = _build_back_url(str(session.id), frontend_url)

    logger.info(
        "[checkout_session] Creating MP plan for session=%s plan=%s amount=%s",
        session.id, plan.code, plan.price,
    )

    mp_plan = mp.create_preapproval_plan(
        reason=f"Suscripción a {plan.name}",
        auto_recurring=auto_recurring,
        back_url=back_url,
        external_reference=session.mp_external_reference,
    )

    mp_plan_id = mp_plan.get('id')
    if not mp_plan_id:
        raise ValueError("MP plan response missing 'id'")

    # Pick the right checkout URL based on token mode.
    is_test = _detect_mode() == 'sandbox'
    if is_test:
        checkout_url = mp_plan.get('sandbox_init_point') or mp_plan.get('init_point')
    else:
        checkout_url = mp_plan.get('init_point') or mp_plan.get('sandbox_init_point')

    session.provider_preapproval_plan_id = mp_plan_id
    session.provider_checkout_url = checkout_url
    session.status = MpCheckoutSession.Status.CHECKOUT_CREATED
    session.save(update_fields=[
        'provider_preapproval_plan_id', 'provider_checkout_url', 'status', 'updated_at',
    ])

    logger.info(
        "[checkout_session] MP plan created plan_id=%s session=%s checkout_url set",
        mp_plan_id, session.id,
    )

    return session

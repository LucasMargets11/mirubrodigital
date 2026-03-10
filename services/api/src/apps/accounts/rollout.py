"""
accounts/rollout.py — Platform-level feature rollout flags.

These flags gate new platform behaviours that are not yet safe to enable
for all tenants simultaneously.  They are controlled via environment
variables (no DB model needed; deploy-time, not tenant-level switches).

Usage::

    from apps.accounts.rollout import rollout

    if rollout.is_enabled(rollout.SUBSCRIPTION_STATUS_ENFORCEMENT):
        # enforce email_verified gate
        ...

Flag names map 1-to-1 to ROLLOUT_FLAGS dict keys in settings.py.
Default value is always False so new flags never fire in existing envs
until explicitly enabled.
"""
from __future__ import annotations

from django.conf import settings


class _RolloutFlags:
    """Lazy accessor for ROLLOUT_FLAGS from Django settings."""

    # ── Flag name constants ───────────────────────────────────────────────────
    NEW_ONBOARDING = 'new_onboarding_enabled'
    """
    When True, brand-new accounts are steered through the dedicated 7-step
    onboarding funnel instead of landing directly on the billing hub.
    """

    OWNER_USER_MANAGEMENT_V2 = 'owner_user_management_v2_enabled'
    """
    When True, the v2 owner management endpoints (change_role, suspend_member,
    remove_member) are visible in the UI and enforced by the owner guard.
    V1 endpoints (disable_account) remain active in both modes.
    """

    SUBSCRIPTION_STATUS_ENFORCEMENT = 'subscription_status_enforcement_enabled'
    """
    When True, HasBusinessMembership additionally blocks accounts whose
    AccountProfile.account_status == 'suspended'.
    Safe to enable once all active accounts have been backfilled (migration 0013).
    """

    EMAIL_VERIFICATION_ENFORCEMENT = 'email_verification_enforcement_enabled'
    """
    When True, commercial activation endpoints (billing/subscribe,
    billing/commercial/checkout, billing/commercial/addon-checkout) require
    the requesting user to have email_verified=True.

    Enforcement is centralised in RequiresEmailVerified (permissions.py).
    Endpoints opt in by adding RequiresEmailVerified to their permission_classes.
    Views that must remain accessible without verification (e.g. resend-verification,
    onboarding status/service-select) must NOT include this class.

    Safe to enable for all new deployments; existing backfilled users already
    have email_verified=True (migration 0013).
    """

    def is_enabled(self, flag_name: str) -> bool:
        """Return True if *flag_name* is enabled in settings.ROLLOUT_FLAGS."""
        flags: dict = getattr(settings, 'ROLLOUT_FLAGS', {})
        return bool(flags.get(flag_name, False))


# Module-level singleton — import as ``from apps.accounts.rollout import rollout``
rollout = _RolloutFlags()

"""
Entitlements resolver for the QR de Reseñas domain.

Determines whether a business is allowed to use reviews, checking:
  1. Standalone ``qr_reviews`` plan (base / pro / legacy)
  2. Carta Online (menu_qr) plans that include reviews
  3. Restaurant / plus plans that include reviews

Smart-filter access is granted to **any** active reviews subscription
(Base, Pro, legacy, or Carta-Online-bundled). Pro is reserved for
advanced capabilities (status management, advanced analytics,
conversion metrics, professional posters, advanced customisation).
"""

from __future__ import annotations

from django.utils import timezone

from apps.menu.qr_entitlements import resolve_menu_qr_flags, get_subscription_for_business

# Plan codes that map to the Pro tier of QR de Reseñas.
_PRO_PLAN_CODES = frozenset({'qr_reviews_pro'})

# All standalone QR de Reseñas plan codes (Base/Pro/legacy/empresarial).
_QR_REVIEWS_PLAN_CODES = frozenset({
    'qr_reviews',
    'qr_reviews_base',
    'qr_reviews_pro',
    'qr_reviews_empresarial',
})


def reviews_allowed(business) -> bool:
    """
    Return True if *business* has access to the reviews product.

    Resolution order:
      1. ``billing.runtime.resolve_subscription`` (SubscriptionV2-first) —
         grants access when V2 is active/trialing/past-due-in-grace for a
         qr_reviews-compatible plan.  This blinds the gate from any drift
         between SubscriptionV2 and the legacy ``business.Subscription`` row.
      2. Legacy path via ``menu.qr_entitlements`` — preserves existing
         behaviour for menu_qr plans and businesses that have not been
         migrated to SubscriptionV2.
    """
    # ── V2-first ─────────────────────────────────────────────────────────────
    try:
        from apps.billing.runtime import resolve_subscription
        resolved = resolve_subscription(business, service_type='qr_reviews')
        if (
            resolved.source == 'v2'
            and resolved.access_granted
            and resolved.plan in _QR_REVIEWS_PLAN_CODES
        ):
            return True
    except Exception:  # noqa: BLE001 — fall through to legacy path
        pass

    # ── Legacy fallback (menu_qr + non-V2 businesses) ────────────────────────
    subscription = get_subscription_for_business(business)
    flags = resolve_menu_qr_flags(subscription)
    return flags['reviews_allowed']


def is_reviews_pro(business) -> bool:
    """Return True if the business is on the qr_reviews_pro plan."""
    # V2-first
    try:
        from apps.billing.runtime import resolve_subscription
        resolved = resolve_subscription(business, service_type='qr_reviews')
        if (
            resolved.source == 'v2'
            and resolved.access_granted
            and resolved.plan in _PRO_PLAN_CODES
        ):
            return True
    except Exception:  # noqa: BLE001
        pass

    subscription = get_subscription_for_business(business)
    if subscription is None:
        return False
    return getattr(subscription, 'plan', '') in _PRO_PLAN_CODES


# Bundle plans that ship QR de Reseñas Carteles as part of a larger package
# (e.g. Restaurante Inteligente → resolves to tier 'plus'). These businesses
# get Carteles even though they are not on the standalone qr_reviews_pro tier.
_POSTER_BUNDLE_PLAN_CODES = frozenset({'plus'})


def print_posters_allowed(business) -> bool:
    """
    Return True if *business* can generate printable QR posters (Carteles).

    Granted to:
      - Standalone Pro tier (``qr_reviews_pro``) — via :func:`is_reviews_pro`.
      - Bundle plans that include Carteles as part of a larger package
        (Restaurante Inteligente → ``plus``), provided reviews access is
        currently active.

    Standalone Base (``qr_reviews`` / ``qr_reviews_base``) does **not** get
    Carteles — it remains a Pro-tier upsell for the standalone product.
    """
    if is_reviews_pro(business):
        return True

    # Bundle path: Restaurante Inteligente includes Carteles for businesses
    # whose reviews access is active.
    try:
        from apps.billing.runtime import resolve_subscription
        resolved = resolve_subscription(business)
        if resolved.access_granted and resolved.plan in _POSTER_BUNDLE_PLAN_CODES:
            return reviews_allowed(business)
    except Exception:  # noqa: BLE001 — defensive, fall through to deny
        pass

    return False


def smart_filter_allowed(business) -> bool:
    """
    Return True if the business can use ``mode=smart_filter``.

    Smart-filter is part of the Base tier (and above): any active QR de
    Reseñas subscription — including Carta-Online-bundled access — grants
    smart-filter capability. Pro tier remains the differentiator for
    advanced analytics, status management and professional posters.

    A 7-day trial flag is still honoured for backwards-compatibility with
    legacy accounts that activated the trial before smart-filter was
    moved to Base.
    """
    if reviews_allowed(business):
        return True
    return trial_active(business)


def trial_active(business) -> bool:
    """Return True if the smart-filter trial is currently running."""
    from .models import ReviewConfig
    try:
        config = business.review_config
    except ReviewConfig.DoesNotExist:
        return False
    if config.trial_ends_at is None:
        return False
    return config.trial_ends_at > timezone.now()


def trial_available(business) -> bool:
    """Return True if the 7-day trial can still be activated (never used)."""
    from .models import ReviewConfig
    try:
        config = business.review_config
    except ReviewConfig.DoesNotExist:
        return True  # Config not created yet → trial hasn't been used
    return not config.trial_used

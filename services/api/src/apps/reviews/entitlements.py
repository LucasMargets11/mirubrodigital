"""
Entitlements resolver for the QR de Reseñas domain.

Determines whether a business is allowed to use reviews, checking:
  1. Standalone ``qr_reviews`` plan (base / pro / legacy)
  2. Carta Online (menu_qr) plans that include reviews
  3. Restaurant / plus plans that include reviews

Also resolves smart-filter access (Pro plan or active trial).
"""

from __future__ import annotations

from django.utils import timezone

from apps.menu.qr_entitlements import resolve_menu_qr_flags, get_subscription_for_business

# Plan codes that map to the Pro tier of QR de Reseñas.
_PRO_PLAN_CODES = frozenset({'qr_reviews_pro'})

# All standalone QR de Reseñas plan codes.
_QR_REVIEWS_PLAN_CODES = frozenset({'qr_reviews', 'qr_reviews_base', 'qr_reviews_pro'})


def reviews_allowed(business) -> bool:
    """
    Return True if *business* has access to the reviews product.

    Uses the same subscription resolution already in place for the menu QR
    entitlements (single source of truth) so standalone qr_reviews plans,
    menu_qr plans with reviews enabled, and restaurant/plus plans all work.
    """
    subscription = get_subscription_for_business(business)
    flags = resolve_menu_qr_flags(subscription)
    return flags['reviews_allowed']


def is_reviews_pro(business) -> bool:
    """Return True if the business is on the qr_reviews_pro plan."""
    subscription = get_subscription_for_business(business)
    if subscription is None:
        return False
    return getattr(subscription, 'plan', '') in _PRO_PLAN_CODES


def smart_filter_allowed(business) -> bool:
    """
    Return True if the business can use ``mode=smart_filter``.

    Allowed when:
      - The subscription plan is qr_reviews_pro, OR
      - A smart-filter trial is currently active.
    """
    if is_reviews_pro(business):
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

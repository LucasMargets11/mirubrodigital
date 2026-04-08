"""
Entitlements resolver for the QR de Reseñas domain.

Determines whether a business is allowed to use reviews, checking:
  1. Standalone ``qr_reviews`` plan
  2. Carta Online (menu_qr) plans that include reviews
  3. Restaurant / plus plans that include reviews
"""

from __future__ import annotations

from apps.menu.qr_entitlements import resolve_menu_qr_flags, get_subscription_for_business


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

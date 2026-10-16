"""Regla única de disponibilidad de la página pública de Turnos `/t/<slug>`.

La usan tanto los endpoints públicos (`public_views._resolve_public_business`)
como el panel (sesión → "Página de reservas"), para que el negocio vea
exactamente el mismo criterio que aplica el backend público.
"""
from __future__ import annotations

from django.conf import settings

from apps.business.service_policy import business_has_service

# Mismo criterio que las landings públicas de Menú QR / Reseñas: un negocio
# sigue siendo visible públicamente en trialing/past_due (grace period),
# pero no en onboarding/suspended/canceled.
PUBLISHABLE_STATUSES = frozenset({'active', 'trialing', 'past_due'})

PUBLIC_BOOKING_PATH = '/t/'


def public_booking_unavailable_reason(business) -> str | None:
  """Motivo por el que la página pública NO está disponible, o None si lo está.

  Códigos cerrados: `missing_slug`, `service_disabled`, `not_publishable`.
  """
  if not business.slug:
    return 'missing_slug'
  if not business_has_service(business, 'appointments'):
    return 'service_disabled'
  if business.status not in PUBLISHABLE_STATUSES:
    return 'not_publishable'
  return None


def build_public_booking_url(slug: str) -> str:
  """URL pública canónica de reservas. Misma base que Menú QR / Reseñas."""
  base_url = (
    getattr(settings, 'PUBLIC_MENU_BASE_URL', None)
    or getattr(settings, 'FRONTEND_URL', None)
    or 'http://localhost:3000'
  )
  return f"{base_url.rstrip('/')}{PUBLIC_BOOKING_PATH}{slug}"


def public_booking_snapshot(business) -> dict:
  """Estado de la página pública del Business actual para el panel.

  Solo expone la URL `/t/<slug>` (sin ids, tokens ni datos de pago) y
  únicamente cuando la página está realmente disponible.
  """
  reason = public_booking_unavailable_reason(business)
  return {
    'available': reason is None,
    'url': build_public_booking_url(business.slug) if reason is None else None,
    'reason': reason,
  }

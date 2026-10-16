"""Disponibilidad de canales de contacto operativo de un Customer (CUSTOMER 07D.1).

Única regla que decide si un canal se puede usar. La consume la ficha (para
mostrar avisos) y la consumirá la infraestructura de envío (07D.2) antes de
mandar cualquier cosa. No envía nada.

Un canal es `usable` solo si, en este orden:
1. el Customer no pidió `do_not_contact` (gana sobre cualquier flag);
2. el canal está permitido (`*_enabled`);
3. hay un dato de contacto válido para ese canal (no se inventan datos);
4. (WhatsApp/email) hay un destino autorizado registrado (`*_consent_value`);
5. (WhatsApp/email) el destino ACTUAL normalizado es exactamente el autorizado
   (CUSTOMER 07D.1.1).

El consentimiento queda ligado al destino concreto: se compara siempre contra
el teléfono/email actual del Customer, así que cualquier camino que lo
modifique (ficha, POS, API, futuros imports) queda cubierto sin que tenga que
limpiar nada. Comparación estricta: si el destino vuelve al valor autorizado
(A → B → A), A vuelve a ser usable, porque es exactamente el destino que el
cliente autorizó y ese consentimiento nunca se revocó.

Llamadas es un canal MANUAL: aunque esté `usable`, nunca entra en
`AUTOMATIC_CHANNELS`. Las acciones manuales de la ficha (CUSTOMER 06) no se
bloquean por esto; solo muestran una advertencia con `do_not_contact`.
"""
from __future__ import annotations

from apps.business.whatsapp import normalize_whatsapp_phone

from .models import Customer, CustomerContactPreferences

Channel = CustomerContactPreferences.Channel

CHANNELS = (Channel.WHATSAPP, Channel.EMAIL, Channel.PHONE)
# Los únicos que un proceso automático podrá usar (07D.2).
AUTOMATIC_CHANNELS = (Channel.WHATSAPP, Channel.EMAIL)
# Activarlos exige confirmar consentimiento.
CONSENT_CHANNELS = AUTOMATIC_CHANNELS

REASON_DO_NOT_CONTACT = 'do_not_contact'
REASON_DISABLED = 'disabled'
REASON_MISSING_PHONE = 'missing_phone'
REASON_INVALID_PHONE = 'invalid_phone'
REASON_MISSING_EMAIL = 'missing_email'
REASON_CONSENT_MISSING = 'consent_missing'
REASON_CONSENT_DESTINATION_CHANGED = 'consent_destination_changed'


def normalize_email(raw) -> str | None:
  """Email para comparar destinos: trim + lowercase (misma convención que el
  chequeo `iexact` de duplicados del Customer). Vacío → None."""
  value = (raw or '').strip().lower() if isinstance(raw, str) else ''
  return value or None


def consent_destination(customer: Customer, channel: str) -> str | None:
  """Destino actual canónico del canal, o None si no hay uno válido.

  WhatsApp: dígitos E.164 (mismo normalizador que la página pública), así
  `11 5555-0101` y `+54 9 11 5555 0101` son el mismo destino. Email: trim +
  lowercase. No se inventa nada: sin dato válido no hay destino.
  """
  if channel == Channel.WHATSAPP:
    country = getattr(customer.business, 'country', None) or 'AR'
    return normalize_whatsapp_phone((customer.phone or '').strip(), country=country)
  if channel == Channel.EMAIL:
    return normalize_email(customer.email)
  return None


def _contact_data_reason(customer: Customer, channel: str) -> str | None:
  if channel == Channel.EMAIL:
    return None if (customer.email or '').strip() else REASON_MISSING_EMAIL
  phone = (customer.phone or '').strip()
  if not phone:
    return REASON_MISSING_PHONE
  if channel == Channel.WHATSAPP:
    country = getattr(customer.business, 'country', None) or 'AR'
    if normalize_whatsapp_phone(phone, country=country) is None:
      return REASON_INVALID_PHONE
  return None


def _consent_reason(customer: Customer, prefs: CustomerContactPreferences, channel: str) -> str | None:
  if channel not in CONSENT_CHANNELS:
    return None
  authorized = getattr(prefs, f'{channel}_consent_value')
  if not authorized or getattr(prefs, f'{channel}_consent_at') is None:
    return REASON_CONSENT_MISSING
  if consent_destination(customer, channel) != authorized:
    return REASON_CONSENT_DESTINATION_CHANGED
  return None


def channel_status(customer: Customer, prefs: CustomerContactPreferences, channel: str) -> dict:
  """{'usable': bool, 'reason': str | None} para un canal (primera razón que aplica)."""
  if prefs.do_not_contact:
    reason = REASON_DO_NOT_CONTACT
  elif not prefs.is_channel_enabled(channel):
    reason = REASON_DISABLED
  else:
    reason = _contact_data_reason(customer, channel) or _consent_reason(customer, prefs, channel)
  return {'usable': reason is None, 'reason': reason}


def channels_status(customer: Customer, prefs: CustomerContactPreferences) -> dict:
  return {channel.value: channel_status(customer, prefs, channel) for channel in CHANNELS}


REASON_NOT_AUTOMATIC = 'channel_not_automatic'


def automatic_channel_status(customer: Customer, channel: str, prefs: CustomerContactPreferences | None = None) -> dict:
  """Misma regla que `can_contact_automatically`, con el motivo (CUSTOMER 07D.2).

  La usa la infraestructura de envío para guardar POR QUÉ un Delivery quedó
  `skipped`. Lee siempre los datos actuales (sin fila = defaults).
  """
  if channel not in AUTOMATIC_CHANNELS:
    return {'usable': False, 'reason': REASON_NOT_AUTOMATIC}
  prefs = prefs if prefs is not None else CustomerContactPreferences.for_customer(customer)
  return channel_status(customer, prefs, channel)


def can_contact_automatically(customer: Customer, channel: str, prefs: CustomerContactPreferences | None = None) -> bool:
  """Gate para 07D.2: ¿un proceso automático puede usar `channel` con este Customer?"""
  return automatic_channel_status(customer, channel, prefs)['usable']

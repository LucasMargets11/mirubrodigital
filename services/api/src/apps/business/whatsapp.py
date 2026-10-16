"""WhatsApp de contacto público del Business (Slice 6D).

Fuente canónica: `BusinessBranding.whatsapp_phone` (opt-in explícito del
negocio como contacto público; se guarda normalizado como `+<E.164>`).
No se usa `BusinessBillingProfile.phone` (dato fiscal) ni el teléfono de
los profesionales.

Solo se generan links `https://wa.me/<dígitos>?text=<mensaje codificado>`:
el cliente abre WhatsApp y envía manualmente. No hay integración con
ninguna API de Meta.
"""
from __future__ import annotations

import re
from urllib.parse import quote

WHATSAPP_BASE_URL = 'https://wa.me/'

# E.164: sin el '+', 8 a 15 dígitos, nunca empieza con 0.
_E164_DIGITS = re.compile(r'^[1-9]\d{7,14}$')
# Caracteres que un humano usa al escribir un teléfono.
_ALLOWED_INPUT = re.compile(r'^\+?[\d\s\-().]+$')

_AR_COUNTRY_CODE = '54'
_AR_MOBILE_PREFIX = '9'
_AR_NATIONAL_DIGITS = 10  # código de área + número, sin 0 ni 15


def _normalize_ar(digits: str) -> str | None:
  """`54...` → `549` + 10 dígitos (formato que usa WhatsApp para móviles AR)."""
  rest = digits[len(_AR_COUNTRY_CODE):]
  if rest.startswith(_AR_MOBILE_PREFIX) and len(rest) == _AR_NATIONAL_DIGITS + 1:
    return digits
  if len(rest) == _AR_NATIONAL_DIGITS and not rest.startswith('0'):
    return f'{_AR_COUNTRY_CODE}{_AR_MOBILE_PREFIX}{rest}'
  return None


def normalize_whatsapp_phone(raw, *, country: str = 'AR') -> str | None:
  """Teléfono ingresado por el negocio → dígitos E.164 (sin '+'), o None.

  Acepta formato internacional (`+54 9 11 1234-5678`, `0054...`) y, para
  Argentina, el nacional sin 15 (`011 1234-5678`, `11 1234 5678`). Todo lo
  que no se pueda normalizar sin adivinar devuelve None.
  """
  if not isinstance(raw, str):
    return None
  value = raw.strip()
  if not value or len(value) > 32 or not _ALLOWED_INPUT.match(value):
    return None

  digits = re.sub(r'\D', '', value)
  international = value.startswith('+')
  if not international and digits.startswith('00'):
    digits = digits[2:]
    international = True

  if not international:
    if (country or 'AR').upper() != 'AR':
      return None
    national = digits[1:] if digits.startswith('0') else digits
    if len(national) == _AR_NATIONAL_DIGITS:
      digits = f'{_AR_COUNTRY_CODE}{_AR_MOBILE_PREFIX}{national}'
    elif digits.startswith(_AR_COUNTRY_CODE):
      international = True
    else:
      return None

  if digits.startswith(_AR_COUNTRY_CODE):
    digits = _normalize_ar(digits)
    if digits is None:
      return None

  return digits if _E164_DIGITS.match(digits) else None


def build_whatsapp_url(phone, text: str) -> str | None:
  """Link `https://wa.me/...` con el mensaje URL-encoded, o None si el
  teléfono no es utilizable. Nunca devuelve otro esquema ni host."""
  digits = normalize_whatsapp_phone(phone)
  if digits is None or not text:
    return None
  return f'{WHATSAPP_BASE_URL}{digits}?text={quote(text, safe="")}'

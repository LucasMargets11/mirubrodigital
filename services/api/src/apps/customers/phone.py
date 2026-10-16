"""Normalización de teléfono para matching de `Customer` (Turnos CUSTOMER 01).

`Customer.phone` es texto libre (lo que escribió el negocio o el cliente) y
no tiene un campo normalizado dedicado. Para deduplicar sin adivinar se usa
una regla mínima y determinística:

- el valor solo puede contener dígitos, espacios, guiones, puntos,
  paréntesis y un `+` inicial (lo que un humano usa al escribir un
  teléfono); cualquier otra cosa (letras, `int. 2`, `/`, etc.) → no
  normalizable;
- la clave de matching son sus dígitos, en orden, sin nada más;
- 6 a 15 dígitos (E.164 tiene como máximo 15).

Deliberadamente NO se infiere país ni prefijos (`0`, `15`, `9` de móviles
AR): `011 1234-5678` y `+54 9 11 1234-5678` son claves distintas. Para eso
existe `apps.business.whatsapp.normalize_whatsapp_phone`, que sí infiere el
formato AR para armar links de WhatsApp — usarla acá podría fusionar
números ambiguos (un fijo con un móvil) y además no es reproducible en SQL.
"""
from __future__ import annotations

import re

from django.db.models import F, Func, QuerySet, Value

_ALLOWED_INPUT = re.compile(r'^\+?[\d\s\-().]+$')
_ALLOWED_INPUT_SQL = r'^\s*\+?[0-9\s().-]+\s*$'
_MIN_DIGITS = 6
_MAX_DIGITS = 15


def normalize_phone_for_matching(raw) -> str | None:
  """Teléfono → clave de matching (solo dígitos) o None si no es utilizable."""
  if not isinstance(raw, str):
    return None
  value = raw.strip()
  if not value or not _ALLOWED_INPUT.match(value):
    return None
  digits = re.sub(r'\D', '', value)
  if not (_MIN_DIGITS <= len(digits) <= _MAX_DIGITS):
    return None
  return digits


def filter_by_phone_key(queryset: QuerySet, phone_key: str) -> QuerySet:
  """Filtra `Customer`s cuyo `phone` normaliza (misma regla, en SQL) a `phone_key`.

  No filtra por `business`: el caller SIEMPRE debe pasar un queryset ya
  acotado al negocio.
  """
  return queryset.filter(phone__regex=_ALLOWED_INPUT_SQL).annotate(
    _phone_key=Func(F('phone'), Value(r'[^0-9]'), Value(''), Value('g'), function='regexp_replace'),
  ).filter(_phone_key=phone_key)

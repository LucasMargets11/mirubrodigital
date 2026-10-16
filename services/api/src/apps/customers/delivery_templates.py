"""Templates versionados en código para entregas al Customer (CUSTOMER 07D.3A).

Sin editor ni DB: cada `template_key` del Delivery tiene un renderer acá
(`appointment_reminder_v1`; `no_show_followup_v1` desde CUSTOMER 07D.4A). El
renderer usa SOLO el `context` congelado al preparar (`build_delivery_context`),
nunca vuelve a consultar el ORM: lo que se manda es lo que se programó.

    render_email(template_key, context) → RenderedEmail(subject, text_body, html_body)

Errores de template/contexto → `TemplateRenderError` (con `code` estable): el
proveedor lo traduce a un fallo definitivo SIN llamar al servicio externo.
Todo valor interpolado en HTML se escapa (`format_html`).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from types import SimpleNamespace

from django.utils.html import format_html, format_html_join

from apps.appointments.services.availability import resolve_business_timezone

from .models import CustomerMessageDelivery

TemplateKey = CustomerMessageDelivery.TemplateKey

ERROR_TEMPLATE_UNSUPPORTED = 'template_unsupported'
ERROR_CONTEXT_INVALID = 'template_context_invalid'

_WEEKDAYS = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')
_MONTHS = (
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
)


class TemplateRenderError(ValueError):
  def __init__(self, code: str, message: str):
    super().__init__(message)
    self.code = code


@dataclass(frozen=True)
class RenderedEmail:
  subject: str
  text_body: str
  html_body: str


def _single_line(value) -> str:
  """Texto de una línea (sin CR/LF: nada de inyección de headers en el subject)."""
  return ' '.join(str(value or '').split())


def _required(context: dict, key: str) -> str:
  value = _single_line(context.get(key))
  if not value:
    raise TemplateRenderError(ERROR_CONTEXT_INVALID, f'Missing context field: {key}')
  return value


def _appointment_local_start(context: dict) -> dt.datetime:
  raw = _required(context, 'appointment_start_at')
  tz_name = _required(context, 'business_timezone')
  try:
    start = dt.datetime.fromisoformat(raw)
  except ValueError:
    raise TemplateRenderError(ERROR_CONTEXT_INVALID, 'Invalid appointment_start_at') from None
  if start.tzinfo is None:
    raise TemplateRenderError(ERROR_CONTEXT_INVALID, 'appointment_start_at must be timezone-aware')
  # Helper canónico de Turnos (Business.timezone, con el mismo fallback).
  return start.astimezone(resolve_business_timezone(SimpleNamespace(timezone=tz_name)))


def format_date_es(value: dt.datetime) -> str:
  """'lunes 6 de octubre de 2026' (sin depender del locale del worker)."""
  return f'{_WEEKDAYS[value.weekday()]} {value.day} de {_MONTHS[value.month - 1]} de {value.year}'


def _appointment_reminder_v1(context: dict) -> RenderedEmail:
  customer_name = _required(context, 'customer_name')
  business_name = _required(context, 'business_name')
  start = _appointment_local_start(context)
  service_name = _single_line(context.get('service_name'))
  date_label = format_date_es(start)
  time_label = start.strftime('%H:%M')

  rows = [('Fecha', date_label), ('Hora', f'{time_label} hs')]
  if service_name:
    rows.append(('Servicio', service_name))

  subject = f'Recordatorio de turno - {business_name}'
  text_body = '\n'.join([
    f'Hola {customer_name},',
    '',
    f'Te recordamos tu turno en {business_name}.',
    '',
    *[f'{label}: {value}' for label, value in rows],
    '',
    'Si necesitás modificar tu turno, comunicate con el negocio.',
    '',
    '--',
    'MiRubro actúa como plataforma tecnológica.',
    '',
  ])
  html_rows = format_html_join(
    '', '<tr><td style="padding:4px 12px 4px 0;color:#64748b">{}</td><td style="padding:4px 0;font-weight:600">{}</td></tr>', rows,
  )
  html_body = format_html(
    '<!doctype html><html lang="es"><body style="margin:0;padding:24px;font-family:Arial,Helvetica,sans-serif;color:#0f172a;background:#ffffff">'
    '<p>Hola {},</p>'
    '<p>Te recordamos tu turno en <strong>{}</strong>.</p>'
    '<table role="presentation" style="border-collapse:collapse;margin:16px 0">{}</table>'
    '<p>Si necesitás modificar tu turno, comunicate con el negocio.</p>'
    '<p style="margin-top:32px;font-size:12px;color:#94a3b8">MiRubro actúa como plataforma tecnológica.</p>'
    '</body></html>',
    customer_name, business_name, html_rows,
  )
  return RenderedEmail(subject=subject, text_body=text_body, html_body=str(html_body))


def _no_show_followup_v1(context: dict) -> RenderedEmail:
  """Seguimiento operativo por inasistencia (CUSTOMER 07D.4A): sin promociones."""
  customer_name = _required(context, 'customer_name')
  business_name = _required(context, 'business_name')
  start = _appointment_local_start(context)
  service_name = _single_line(context.get('service_name'))
  when = f'del {format_date_es(start)} a las {start.strftime("%H:%M")} hs'
  what = f'tu turno de {service_name} {when}' if service_name else f'tu turno {when}'

  subject = f'Te esperamos en tu próximo turno - {business_name}'
  text_body = '\n'.join([
    f'Hola {customer_name},',
    '',
    f'Notamos que no pudiste asistir a {what} en {business_name}.',
    '',
    'Si querés reprogramarlo, comunicate con el negocio.',
    '',
    '--',
    'MiRubro actúa como plataforma tecnológica.',
    '',
  ])
  html_body = format_html(
    '<!doctype html><html lang="es"><body style="margin:0;padding:24px;font-family:Arial,Helvetica,sans-serif;color:#0f172a;background:#ffffff">'
    '<p>Hola {},</p>'
    '<p>Notamos que no pudiste asistir a {} en <strong>{}</strong>.</p>'
    '<p>Si querés reprogramarlo, comunicate con el negocio.</p>'
    '<p style="margin-top:32px;font-size:12px;color:#94a3b8">MiRubro actúa como plataforma tecnológica.</p>'
    '</body></html>',
    customer_name, what, business_name,
  )
  return RenderedEmail(subject=subject, text_body=text_body, html_body=str(html_body))


_EMAIL_RENDERERS = {
  TemplateKey.APPOINTMENT_REMINDER_V1: _appointment_reminder_v1,
  TemplateKey.NO_SHOW_FOLLOWUP_V1: _no_show_followup_v1,
}


def render_email(template_key: str | None, context: dict | None) -> RenderedEmail:
  renderer = _EMAIL_RENDERERS.get(template_key or '')
  if renderer is None:
    raise TemplateRenderError(ERROR_TEMPLATE_UNSUPPORTED, f'No email template for: {template_key}')
  return renderer(dict(context or {}))

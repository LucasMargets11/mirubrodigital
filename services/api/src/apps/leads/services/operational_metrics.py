"""PROD-02E4D — métricas operativas de un Business para Platform Admin.

Bloques independientes, nunca sumados entre sí:
  * `openai_activity` / `openai_costs` — `ai_execution_metrics` (intentos reales
    registrados por el agente; costo ESTIMADO en USD con tarifas verificadas).
  * `whatsapp` — `whatsapp_metrics` (mensajes registrados por el agente).
  * `commercial_ai_sessions` — sesiones comerciales de IA (la unidad de
    consumo de 24 h por conversación) que EMPEZARON en el período; no son
    conversaciones ni mensajes.

Período: días locales del Business (`timezone`), `date_from`..`date_to`
inclusive → [date_from 00:00, date_to+1 00:00) en esa zona. Por defecto los
últimos 30 días hasta hoy; máximo 92 días. Server time only. Solo lectura.
Nada de esto indica el estado actual de la conexión de WhatsApp.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .ai_execution_metrics import ai_execution_metrics
from .whatsapp_metrics import MAX_RANGE_DAYS, _business_tz, whatsapp_metrics

DEFAULT_DAYS = 30


class OperationalMetricsRangeError(ValueError):
    pass


def _parse(raw, name) -> date | None:
    if raw in (None, ''):
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError as exc:
        raise OperationalMetricsRangeError(f'{name} must be YYYY-MM-DD.') from exc


def resolve_period(business, raw_from=None, raw_to=None) -> dict:
    tz = _business_tz(business)
    today = timezone.now().astimezone(tz).date()
    date_to = _parse(raw_to, 'date_to') or today
    date_from = _parse(raw_from, 'date_from') or (date_to - timedelta(days=DEFAULT_DAYS - 1))
    if date_from > date_to:
        raise OperationalMetricsRangeError('date_from must be on or before date_to.')
    days = (date_to - date_from).days + 1
    if days > MAX_RANGE_DAYS:
        raise OperationalMetricsRangeError(f'The period cannot exceed {MAX_RANGE_DAYS} days.')
    start = datetime.combine(date_from, time(), tzinfo=tz)
    end = datetime.combine(date_to + timedelta(days=1), time(), tzinfo=tz)
    return {
        'tz': tz, 'start': start, 'end': end, 'days': [date_from + timedelta(days=i) for i in range(days)],
        'block': {
            'timezone': str(tz), 'date_from': date_from.isoformat(), 'date_to': date_to.isoformat(),
            'days': days, 'start': start.isoformat(), 'end': end.isoformat(),
            'bounds': 'start inclusive, end exclusive (local midnights)',
        },
    }


def operational_metrics(business, raw_from=None, raw_to=None) -> dict:
    from apps.appointments.models import AppointmentAIUsageSession

    period = resolve_period(business, raw_from, raw_to)
    start, end, tz = period['start'], period['end'], period['tz']
    ai = ai_execution_metrics(business, start=start, end=end, tz=tz, days=period['days'])
    whatsapp = whatsapp_metrics(business, start=start, end=end)
    sessions = AppointmentAIUsageSession.objects.filter(business=business, started_at__gte=start, started_at__lt=end)
    return {
        'contract_version': 1,
        'business_id': business.pk,
        'period': period['block'],
        'openai_activity': ai['activity'],
        'openai_costs': ai['costs'],
        'whatsapp': whatsapp,
        'commercial_ai_sessions': {
            'definition': '24h AI session per conversation (commercial billing unit) started in the period',
            'started': sessions.count(),
        },
        'coverage': {
            'openai': {
                'source': 'agent_ai_execution',
                'counts_real_provider_attempts': True,
                'requires_agent_telemetry_enabled': True,
                'tokens_reported': ai['activity']['tokens']['input']['reported'],
                'tokens_unknown': ai['activity']['tokens']['input']['unknown'],
            },
            'whatsapp': whatsapp['coverage'],
            'notes': [
                'blocks_are_not_additive',
                'costs_are_estimates_not_invoices',
                'no_meta_costs',
                'activity_is_not_current_connection_status',
            ],
        },
    }

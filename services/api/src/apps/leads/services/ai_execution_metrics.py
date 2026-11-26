"""PROD-02E4D — métricas agregadas y costo ESTIMADO de las ejecuciones de IA.

Fuente: `AgentAIExecution` (un intento real contra el proveedor informado por
el agente, PROD-02E4A/B), por Business y rango [start, end) sobre
`executed_at` (hora original de ejecución). Independiente del consumo
comercial (sesiones/cargos): cuenta intentos, no sesiones. Solo lectura.

Costo (USD, Decimal, nunca float), por ejecución y con la tarifa `verified`
de `AIProviderRate` vigente en su `executed_at`:

    ((input - cached) × input_rate + cached × cached_rate + output × output_rate) / 1_000_000

Sin estimación (y con su motivo) cuando falta input/output (`tokens_unknown`),
falta `cached` (`cached_tokens_unknown`, no se puede separar la entrada),
no hay tarifa verificada vigente (`no_rate`) o hay más de una (`ambiguous_rate`).
Una ejecución fallida/desconocida NO vale 0: si no informó tokens no se estima.
El total es parcial (`complete: false`) si alguna ejecución no se pudo estimar.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from django.db.models import Q

from ..models import AgentAIExecution, AIProviderRate

CONTRACT_VERSION = 1
MILLION = Decimal(1_000_000)
COST_QUANTUM = Decimal('0.0000000001')  # 1e-10 USD in the contract
P95_MIN_SAMPLES = 20

NO_COST_REASONS = ('tokens_unknown', 'cached_tokens_unknown', 'no_rate', 'ambiguous_rate')


def _money(value: Decimal) -> str:
    return format(value.quantize(COST_QUANTUM), 'f')  # never exponent notation


def _p95(values: list[int]) -> Optional[int]:
    if len(values) < P95_MIN_SAMPLES:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]  # nearest-rank


class _Rates:
    """Verified rates of the models in play, resolved per execution instant."""

    def __init__(self, models: set[tuple[str, str]]):
        self.by_model: dict[tuple[str, str], list[AIProviderRate]] = defaultdict(list)
        if models:
            query = Q()
            for provider, model in models:
                query |= Q(provider=provider, model=model)
            for rate in AIProviderRate.objects.filter(query, status=AIProviderRate.Status.VERIFIED):
                self.by_model[(rate.provider, rate.model)].append(rate)

    def resolve(self, provider: str, model: str, at: datetime):
        matches = [
            r for r in self.by_model.get((provider, model), ())
            if r.valid_from <= at and (r.valid_until is None or at < r.valid_until)
        ]
        if not matches:
            return None, 'no_rate'
        if len(matches) > 1:
            return None, 'ambiguous_rate'
        return matches[0], None


def execution_cost(row: dict, rates: _Rates) -> tuple[Optional[Decimal], Optional[str], Optional[AIProviderRate]]:
    input_tokens, output_tokens, cached = row['input_tokens'], row['output_tokens'], row['cached_input_tokens']
    if input_tokens is None or output_tokens is None:
        return None, 'tokens_unknown', None
    if cached is None:
        return None, 'cached_tokens_unknown', None
    rate, reason = rates.resolve(row['provider'], row['model'], row['executed_at'])
    if rate is None:
        return None, reason, None
    cost = (
        Decimal(input_tokens - cached) * rate.input_per_million
        + Decimal(cached) * rate.cached_input_per_million
        + Decimal(output_tokens) * rate.output_per_million
    ) / MILLION
    return cost, None, rate


def ai_execution_metrics(business, *, start: datetime, end: datetime, tz: ZoneInfo, days: list) -> dict:
    """(activity, costs) blocks for [start, end). Range validated by the caller."""
    rows = list(
        AgentAIExecution.objects
        .filter(business=business, channel__business=business, executed_at__gte=start, executed_at__lt=end)
        .values('provider', 'model', 'operation', 'status', 'input_tokens', 'output_tokens',
                'cached_input_tokens', 'latency_ms', 'executed_at')
        .order_by()
    )
    rates = _Rates({(r['provider'], r['model']) for r in rows})

    def token_block(field):
        known = [r[field] for r in rows if r[field] is not None]
        return {'total': sum(known) if known else None, 'reported': len(known), 'unknown': len(rows) - len(known)}

    latencies = [r['latency_ms'] for r in rows if r['latency_ms'] is not None]
    statuses = {s: 0 for s in AgentAIExecution.Status.values}
    by_model: dict[tuple, dict] = {}
    by_operation: dict[str, int] = defaultdict(int)
    daily = {day: {'executions': 0, 'input_tokens': 0, 'output_tokens': 0, 'cost': Decimal(0),
                   'costed': 0, 'uncosted': 0} for day in days}
    cost_total, costed, reasons = Decimal(0), 0, {reason: 0 for reason in NO_COST_REASONS}
    cost_by_model: dict[tuple, dict] = {}
    rates_used: dict = {}

    for r in rows:
        statuses[r['status']] += 1
        model_key = (r['provider'], r['model'])
        entry = by_model.setdefault(model_key, {'provider': r['provider'], 'model': r['model'], 'executions': 0,
                                                'succeeded': 0, 'failed': 0, 'unknown': 0})
        entry['executions'] += 1
        entry[r['status']] += 1
        by_operation[r['operation']] += 1
        bucket = daily[r['executed_at'].astimezone(tz).date()]
        bucket['executions'] += 1
        bucket['input_tokens'] += r['input_tokens'] or 0
        bucket['output_tokens'] += r['output_tokens'] or 0
        cost, reason, rate = execution_cost(r, rates)
        model_cost = cost_by_model.setdefault(model_key, {'provider': r['provider'], 'model': r['model'],
                                                          'cost': Decimal(0), 'costed': 0, 'uncosted': 0})
        if cost is None:
            reasons[reason] += 1
            bucket['uncosted'] += 1
            model_cost['uncosted'] += 1
            continue
        costed += 1
        cost_total += cost
        bucket['cost'] += cost
        bucket['costed'] += 1
        model_cost['cost'] += cost
        model_cost['costed'] += 1
        rates_used[rate.pk] = rate

    uncosted = len(rows) - costed
    activity = {
        'executions': len(rows),
        'by_status': statuses,
        'by_model': sorted(by_model.values(), key=lambda e: (e['provider'], e['model'])),
        'by_operation': dict(sorted(by_operation.items())),
        'tokens': {
            'input': token_block('input_tokens'),
            'output': token_block('output_tokens'),
            'cached_input': token_block('cached_input_tokens'),
        },
        'latency_ms': {
            'reported': len(latencies),
            'average': round(sum(latencies) / len(latencies), 1) if latencies else None,
            'p95': _p95(latencies),
            'p95_min_samples': P95_MIN_SAMPLES,
        },
        'daily': [
            {
                'date': day.isoformat(),
                'executions': b['executions'],
                # Daily sums of the REPORTED tokens only (unknown ones are counted in `tokens`)
                'input_tokens_reported': b['input_tokens'],
                'output_tokens_reported': b['output_tokens'],
            }
            for day, b in sorted(daily.items())
        ],
    }
    costs = {
        'currency': 'USD',
        'kind': 'estimated',
        'estimated_total': _money(cost_total),
        'complete': uncosted == 0,
        'costed_executions': costed,
        'uncosted_executions': uncosted,
        'uncosted_reasons': reasons,
        'by_model': [
            {**{k: v for k, v in e.items() if k != 'cost'}, 'estimated_cost': _money(e['cost']),
             'complete': e['uncosted'] == 0}
            for e in sorted(cost_by_model.values(), key=lambda e: (e['provider'], e['model']))
        ],
        'daily': [
            {'date': day.isoformat(), 'estimated_cost': _money(b['cost']), 'costed': b['costed'],
             'uncosted': b['uncosted'], 'complete': b['uncosted'] == 0}
            for day, b in sorted(daily.items())
        ],
        'rates_used': [
            {
                'id': str(rate.pk), 'provider': rate.provider, 'model': rate.model,
                'input_per_million': str(rate.input_per_million),
                'cached_input_per_million': str(rate.cached_input_per_million),
                'output_per_million': str(rate.output_per_million),
                'valid_from': rate.valid_from.isoformat(),
                'valid_until': rate.valid_until.isoformat() if rate.valid_until else None,
                'source_reference': rate.source_reference,
            }
            for rate in sorted(rates_used.values(), key=lambda r: (r.model, r.valid_from))
        ],
        'formula': '((input - cached) * input_rate + cached * cached_rate + output * output_rate) / 1e6',
    }
    return {'contract_version': CONTRACT_VERSION, 'activity': activity, 'costs': costs}

"""Historial humano/operativo del Lead (LEADS 04B.4).

Solo se llama desde las acciones humanas de la API CRM (PATCH y reconocer
atención), DENTRO de su transacción y después de guardar el Lead: si algo
falla, el cambio y su actividad se revierten juntos. El receiver del agente
nunca registra actividad.
"""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from ..contract import format_utc
from ..models import Lead, LeadActivity

K = LeadActivity.Kind


def _link_kind(previous, new, *, linked, changed, unlinked) -> str:
    if previous is None:
        return linked
    if new is None:
        return unlinked
    return changed


def _raw(value) -> Any:
    # JSON-safe: user id int, UUID → str, choices → str.
    return str(value) if value is not None and not isinstance(value, (int, str)) else value


def build_update_events(previous: dict[str, Any], lead: Lead) -> list[dict[str, Any]]:
    """Eventos de un PATCH (orden canónico). `previous` = valores `*_id`/status/outcome antes del cambio."""
    events: list[dict[str, Any]] = []

    def add(kind, before=None, after=None, **metadata):
        events.append({'kind': kind, 'previous_value': _raw(before), 'new_value': _raw(after), 'metadata': metadata})

    if previous['status'] != lead.status:
        if lead.status == Lead.Status.CLOSED:
            # Cierre = un solo evento; el outcome elegido viaja en metadata.
            add(K.CLOSED, previous['status'], lead.status, outcome=lead.outcome)
        else:
            add(K.STATUS_CHANGED, previous['status'], lead.status)
    elif previous['outcome'] != lead.outcome:
        add(K.OUTCOME_CHANGED, previous['outcome'], lead.outcome)

    if previous['assigned_to_id'] != lead.assigned_to_id:
        add(
            _link_kind(previous['assigned_to_id'], lead.assigned_to_id,
                       linked=K.ASSIGNED, changed=K.REASSIGNED, unlinked=K.UNASSIGNED),
            previous['assigned_to_id'], lead.assigned_to_id,
        )
    if previous['customer_id'] != lead.customer_id:
        add(
            _link_kind(previous['customer_id'], lead.customer_id,
                       linked=K.CUSTOMER_LINKED, changed=K.CUSTOMER_CHANGED, unlinked=K.CUSTOMER_UNLINKED),
            previous['customer_id'], lead.customer_id,
        )
    if previous['appointment_id'] != lead.appointment_id:
        add(
            _link_kind(previous['appointment_id'], lead.appointment_id,
                       linked=K.APPOINTMENT_LINKED, changed=K.APPOINTMENT_CHANGED, unlinked=K.APPOINTMENT_UNLINKED),
            previous['appointment_id'], lead.appointment_id,
        )
    return events


def snapshot_for_activity(lead: Lead) -> dict[str, Any]:
    return {
        'status': lead.status,
        'outcome': lead.outcome,
        'assigned_to_id': lead.assigned_to_id,
        'customer_id': lead.customer_id,
        'appointment_id': lead.appointment_id,
    }


def record_update_activity(lead: Lead, previous: dict[str, Any], *, actor) -> list[LeadActivity]:
    """Registra los eventos de un PATCH ya guardado. Sin cambios relevantes → nada."""
    events = build_update_events(previous, lead)
    if not events:
        return []
    occurred_at = timezone.now()
    return [
        LeadActivity.objects.create(
            business_id=lead.business_id, lead=lead, actor=actor, created_at=occurred_at, position=position, **event,
        )
        for position, event in enumerate(events)
    ]


def record_attention_acknowledged(lead: Lead, *, actor) -> LeadActivity:
    """Reconocimiento efectivo (no el no-op idempotente). Usa el mismo instante que `acknowledged_at`."""
    return LeadActivity.objects.create(
        business_id=lead.business_id, lead=lead, actor=actor, kind=K.ATTENTION_ACKNOWLEDGED,
        created_at=lead.acknowledged_at,
        metadata={'needs_attention_at': format_utc(lead.needs_attention_at)},
    )

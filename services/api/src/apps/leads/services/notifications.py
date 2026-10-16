"""Aviso personal de asignación de Lead (LEADS 04B.3).

Cuando un humano cambia `Lead.assigned_to` a otra persona, esa persona recibe
una `BusinessNotification` `lead_assigned` con `recipient` = ella (solo la ve
ella). No se avisa al desasignar, al reenviar la misma asignación, al
auto-asignarse ni al asignado anterior.

Idempotencia: el PATCH bloquea el Lead (`select_for_update`) y compara contra
el valor bloqueado, así dos PATCH iguales concurrentes generan un solo cambio.
La clave usa el `updated_at` de ESE guardado → una por evento de asignación
(reasignar A → B → A vuelve a avisar a A). Post-commit y fail-safe
(`on_commit_safely`): un fallo nunca revierte la asignación.
"""
from __future__ import annotations

from apps.notifications.business_notifications import create_business_notification, on_commit_safely
from apps.notifications.models import BusinessNotification

from ..contract import format_utc
from ..models import Lead

ASSIGNED_NOTIFICATION_TITLE = 'Te asignaron una consulta'
ASSIGNED_NOTIFICATION_MESSAGE = 'Una consulta quedó asignada a vos.'


def schedule_lead_assigned_notification(lead: Lead, *, actor) -> None:
    """Llamar dentro de la transacción del PATCH, después de guardar un cambio de `assigned_to`."""
    recipient_id = lead.assigned_to_id
    if recipient_id is None or recipient_id == getattr(actor, 'pk', None):
        return
    lead_id, business_id = lead.pk, lead.business_id
    dedupe_key = f'lead_assigned:{lead_id}:{recipient_id}:{format_utc(lead.updated_at)}'

    def _notify():
        # Si otra reasignación ya commiteó, este aviso quedó viejo.
        if not Lead.objects.filter(pk=lead_id, assigned_to_id=recipient_id).exists():
            return
        create_business_notification(
            business_id=business_id,
            kind=BusinessNotification.Kind.LEAD_ASSIGNED,
            dedupe_key=dedupe_key,
            title=ASSIGNED_NOTIFICATION_TITLE,
            message=ASSIGNED_NOTIFICATION_MESSAGE,
            severity=BusinessNotification.Severity.INFO,
            # Igual que agent_lead_handoff: el panel de leads todavía no existe.
            action_url='',
            related_object_type='lead',
            related_object_id=str(lead_id),
            metadata={'source': 'crm', 'assigned_by': getattr(actor, 'pk', None)},
            recipient_id=recipient_id,
        )

    on_commit_safely(_notify, description=f'lead_assigned lead={lead_id}')

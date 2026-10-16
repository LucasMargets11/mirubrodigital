"""Tareas Celery de apps.leads (MIRUBRO TAKEOVER 05A).

La política de reintentos de los comandos takeover/release vive en la DB
(`TakeoverCommand.attempts` / `next_attempt_at`, ver `services.takeover`), no
en Celery: sin autoretry. Un redelivery de la task (acks_late) ve el comando
`delivering`/final y no reenvía; el Beat recupera kicks perdidos.
"""
from __future__ import annotations

from celery import shared_task


@shared_task(name='leads.deliver_takeover_command', acks_late=True)
def deliver_takeover_command(command_id):
    from apps.leads.services.takeover import deliver_takeover_command as deliver

    return deliver(command_id)


@shared_task(name='leads.retry_due_takeover_commands', acks_late=True)
def retry_due_takeover_commands():
    from apps.leads.services.takeover import retry_due_takeover_commands as sweep

    return sweep()


@shared_task(name='leads.deliver_staff_message', acks_late=True)
def deliver_staff_message(message_id):
    from apps.leads.services.human_messages import deliver_staff_message as deliver

    return deliver(message_id)


@shared_task(name='leads.retry_due_staff_messages', acks_late=True)
def retry_due_staff_messages():
    from apps.leads.services.human_messages import retry_due_staff_messages as sweep

    return sweep()

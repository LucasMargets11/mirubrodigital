"""Tareas periódicas de Turnos (Slice 7C).

`appointments.expire_holds` materializa `pending_payment` vencido → `expired`
llamando al mismo servicio que el management command
`expire_appointment_holds` (`services.expiration`). Programada en
`CELERY_BEAT_SCHEDULE` (config/settings.py).

La disponibilidad NO depende de esta tarea: `AppointmentQuerySet.occupying`
ya trata como libre un hold vencido aunque su `status` siga en
`pending_payment`. Si Beat está caído, los horarios siguen siendo correctos;
solo el `status` persistido queda atrasado en listados/reportes.

Idempotente: es un UPDATE condicional por `status` + `expires_at`; re-correrla
no vuelve a tocar filas ya `expired` ni afecta `confirmed`.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
  bind=True,
  name='appointments.expire_holds',
  max_retries=2,
  default_retry_delay=30,
  acks_late=True,
)
def expire_appointment_holds(self):
  from apps.appointments.services.expiration import expire_due_appointment_holds

  count = expire_due_appointment_holds()
  if count:
    logger.info('appointments.expire_holds: %d hold(s) marcados expired', count)
  return {'expired': count}

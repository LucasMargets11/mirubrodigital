"""Expiración de holds de `pending_payment` vencidos (Slice 4B, punto 8).

Importante: la disponibilidad NUNCA depende de que este helper haya
corrido — `AppointmentQuerySet.occupying` ya considera vencido (y por lo
tanto libre) un `pending_payment` cuyo `expires_at` pasó, sin importar el
valor físico de `status`. Este helper solo materializa esa transición para
que el status deje de aparecer como "pendiente" en listados/reportes.

Slice 7C: corre automáticamente vía Celery Beat (`appointments.expire_holds`,
ver `apps.appointments.tasks`) y sigue disponible a mano con el management
command `expire_appointment_holds`.

Slice 6B: solo cambia `status`. NO toca `expires_at` (el webhook lo usa
para juzgar si un pago aprobado tarde cayó dentro de la ventana) ni los
`AppointmentPayment` del turno (pending/uncertain/Preference creada quedan
como registro histórico). Es un UPDATE por fila: si un webhook tiene el
turno lockeado, espera y re-evalúa el WHERE (un turno ya `confirmed` no se
vence).

CUSTOMER 07B: no reconcilia recordatorios a propósito. Un `pending_payment`
nunca tiene recordatorio previo automático (solo se crea en `confirmed`), así
que vencer un hold no tiene nada que cancelar; mantenerlo como UPDATE masivo.
"""
from __future__ import annotations

from django.utils import timezone as dj_timezone

from ..models import Appointment


def expire_due_appointment_holds(*, now=None) -> int:
  now = now or dj_timezone.now()
  return Appointment.objects.filter(
    status=Appointment.Status.PENDING_PAYMENT, expires_at__lte=now,
  ).update(status=Appointment.Status.EXPIRED)

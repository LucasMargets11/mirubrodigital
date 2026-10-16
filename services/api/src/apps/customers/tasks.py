import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
  bind=True,
  name='customers.dispatch_due_reminders',
  max_retries=2,
  default_retry_delay=30,
  acks_late=True,
)
def dispatch_due_customer_reminders(self):
  """Aviso interno de CustomerReminders vencidos (CUSTOMER 07C).

  Idempotente y concurrent-safe (ver `reminder_dispatch`): un Beat duplicado,
  un retry o una ejecución manual nunca generan un segundo aviso. Los fallos
  por recordatorio se aíslan y quedan para la próxima corrida.
  """
  from apps.customers.reminder_dispatch import dispatch_due_customer_reminders as dispatch

  return dispatch().as_dict()


# CUSTOMER 07D.2 — entregas externas. La política de reintentos vive en la DB
# (`attempt_count` / `next_retry_at`, ver `deliveries`), no en Celery: estas
# tasks no usan autoretry. Un redelivery de la task (acks_late) ve el Delivery
# `processing`/final y no reenvía.

@shared_task(name='customers.execute_delivery', acks_late=True)
def execute_customer_delivery(delivery_id):
  from apps.customers.deliveries import execute_delivery

  return execute_delivery(delivery_id)


@shared_task(name='customers.retry_due_deliveries', acks_late=True)
def retry_due_customer_deliveries():
  from apps.customers.deliveries import retry_due_customer_deliveries as sweep

  return sweep().as_dict()

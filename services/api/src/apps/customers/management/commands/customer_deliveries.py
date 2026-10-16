"""Operación/QA controlada de entregas externas al Customer (CUSTOMER 07D.2 / 07D.3A).

Por defecto usa el proveedor configurado (email: `CUSTOMER_DELIVERY_PROVIDER_EMAIL`,
default fake). `--provider ses` fuerza Amazon SES real para UN Delivery de email
(opt-in explícito del operador; el consent gate de execute_delivery aplica igual).

  python manage.py customer_deliveries prepare --customer <uuid> --channel email \
      --purpose appointment_reminder --key qa:1 [--appointment <uuid>] [--reminder <uuid>]
  python manage.py customer_deliveries execute --id <delivery uuid> [--fake-mode success|retryable_failure|permanent_failure]
  python manage.py customer_deliveries execute --id <delivery uuid> --provider ses
  python manage.py customer_deliveries sweep [--fake-mode ...]
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.customers.deliveries import execute_delivery, prepare_customer_delivery, retry_due_customer_deliveries
from apps.customers.delivery_providers import _FAKE_BY_CHANNEL, FakeProvider, get_provider
from apps.customers.models import Customer, CustomerMessageDelivery


class Command(BaseCommand):
  help = 'Prepara/ejecuta CustomerMessageDelivery (fake por defecto; --provider ses para SES real).'

  def add_arguments(self, parser):
    parser.add_argument('action', choices=['prepare', 'execute', 'sweep'])
    parser.add_argument('--customer')
    parser.add_argument('--channel', choices=CustomerMessageDelivery.Channel.values)
    parser.add_argument('--purpose', choices=CustomerMessageDelivery.Purpose.values)
    parser.add_argument('--key', help='idempotency_key')
    parser.add_argument('--appointment')
    parser.add_argument('--reminder')
    parser.add_argument('--id', help='delivery id (execute)')
    parser.add_argument('--fake-mode', choices=FakeProvider.MODES)
    parser.add_argument('--provider', choices=['fake', 'ses'], help='execute: fuerza el proveedor (ses solo email)')

  def handle(self, *args, **opts):
    action = opts['action']
    if action == 'prepare':
      return self._prepare(opts)
    if action == 'execute':
      return self._execute(opts)
    if opts['provider']:
      raise CommandError('--provider solo aplica a execute')
    if opts['fake_mode']:
      # El barrido mezcla canales: el modo se aplica vía settings para ambos fakes.
      from django.test.utils import override_settings

      with override_settings(CUSTOMER_DELIVERY_FAKE_MODE=opts['fake_mode']):
        result = retry_due_customer_deliveries()
    else:
      result = retry_due_customer_deliveries()
    self.stdout.write(str(result.as_dict()))
    return None

  def _execute(self, opts):
    if not opts['id']:
      raise CommandError('--id es obligatorio')
    delivery = CustomerMessageDelivery.objects.filter(pk=opts['id']).first()
    if delivery is None:
      raise CommandError('Delivery inexistente')
    if opts['fake_mode'] and opts['provider'] == 'ses':
      raise CommandError('--fake-mode no se combina con --provider ses')
    if opts['fake_mode']:
      provider = _FAKE_BY_CHANNEL[delivery.channel](opts['fake_mode'])
    elif opts['provider']:
      try:
        provider = get_provider(delivery.channel, opts['provider'])
      except ValueError as exc:
        raise CommandError(str(exc)) from exc
    else:
      provider = None
    outcome = execute_delivery(delivery.pk, provider=provider)
    delivery.refresh_from_db()
    # Sin destino ni mensaje de error crudo: solo estado/códigos/ids.
    self.stdout.write(f'outcome={outcome} status={delivery.status} provider={delivery.provider} '
                      f'message_id={delivery.provider_message_id} attempts={delivery.attempt_count} '
                      f'reason={delivery.skip_reason} failure={delivery.failure_code} next_retry_at={delivery.next_retry_at}')
    return None

  def _prepare(self, opts):
    for name in ('customer', 'channel', 'purpose', 'key'):
      if not opts[name]:
        raise CommandError(f'--{name} es obligatorio')
    customer = Customer.objects.select_related('business').filter(pk=opts['customer']).first()
    if customer is None:
      raise CommandError('Customer inexistente')
    appointment = reminder = None
    if opts['appointment']:
      from apps.appointments.models import Appointment

      appointment = Appointment.objects.filter(pk=opts['appointment'], business=customer.business).first()
      if appointment is None:
        raise CommandError('Turno inexistente en el Business del cliente')
    if opts['reminder']:
      reminder = customer.reminders.filter(pk=opts['reminder']).first()
      if reminder is None:
        raise CommandError('Recordatorio inexistente para el cliente')
    delivery, created = prepare_customer_delivery(
      business=customer.business, customer=customer, channel=opts['channel'], purpose=opts['purpose'],
      idempotency_key=opts['key'], appointment=appointment, reminder=reminder, enqueue=False,
    )
    self.stdout.write(f'id={delivery.pk} created={created} status={delivery.status} reason={delivery.skip_reason}')

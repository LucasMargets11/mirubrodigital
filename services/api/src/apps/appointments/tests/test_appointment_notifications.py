"""Slice 6D: notificación interna al negocio + WhatsApp manual en la reserva pública.

End-to-end por el webhook real (mismo harness que Slice 6B). Las
notificaciones se crean en `transaction.on_commit`, así que los webhooks se
disparan dentro de `captureOnCommitCallbacks(execute=True)`.
"""
from __future__ import annotations

import datetime as dt
import uuid
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone as dj_timezone

from apps.accounts.models import Membership
from apps.billing.models import WebhookDelivery
from apps.business.models import BusinessBranding
from apps.notifications.business_notifications import create_business_notification
from apps.notifications.models import BusinessNotification

from ..models import Appointment, AppointmentPayment, AppointmentProfessional
from ..services import contact
from .test_appointment_checkout import TOKEN_B, create_appointment, create_business, create_service
from .test_appointment_payment_webhook import TOKEN_A, WEBHOOK_SETTINGS, _Base, mp_payment

User = get_user_model()
S = WebhookDelivery.ProcessingStatus
P = AppointmentPayment.Status
Kind = BusinessNotification.Kind
NOTIF_URL = '/api/v1/notifications/business/'
WHATSAPP = '+5491112345678'
# Id de pago de MP distintivo (no puede aparecer por casualidad en fechas/uuids).
PAYMENT_ID = '8877665544'


def public_url(appt: Appointment) -> str:
  return f'/api/v1/appointments/public/{appt.business.slug}/bookings/{appt.public_token}/'


@override_settings(**WEBHOOK_SETTINGS)
class _NotifBase(_Base):
  def notify(self, payment_id=PAYMENT_ID, **kw) -> WebhookDelivery:
    with self.captureOnCommitCallbacks(execute=True):
      return self._notify(payment_id, **kw)

  def notifications(self, business=None):
    return BusinessNotification.objects.filter(business=business or self.biz)

  def expire_hold(self, minutes_ago=5):
    expires_at = dj_timezone.now() - dt.timedelta(minutes=minutes_ago)
    Appointment.objects.filter(pk=self.appt.pk).update(expires_at=expires_at)
    self.appt.refresh_from_db()
    return expires_at

  def make_review(self):
    expires_at = self.expire_hold()
    self.mp.responses[TOKEN_A] = mp_payment(self.payment, date_approved=expires_at + dt.timedelta(minutes=1))
    self.notify()
    self._reload()
    self.assertEqual(self.payment.status, P.REQUIRES_REVIEW)


class ConfirmedNotificationTests(_NotifBase):
  # 1. confirmed por webhook → notificación interna
  def test_confirmed_by_webhook_creates_notification(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self.assertEqual(self.notify().processing_status, S.PROCESSED)
    self._reload()
    self.assertEqual(self.appt.status, Appointment.Status.CONFIRMED)

    notif = self.notifications().get()
    self.assertEqual(notif.kind, Kind.APPOINTMENT_CONFIRMED)
    self.assertEqual(notif.severity, BusinessNotification.Severity.INFO)
    self.assertEqual(notif.title, 'Nueva reserva confirmada')
    self.assertEqual(notif.dedupe_key, f'appointment_confirmed:{self.appt.pk}')
    self.assertIn('Juana Pérez', notif.message)
    self.assertIn('Corte', notif.message)
    self.assertIsNone(notif.read_at)
    parts = urlsplit(notif.action_url)
    self.assertEqual(parts.path, '/app/turnos/turnos')
    self.assertEqual(parse_qs(parts.query)['appointment'], [str(self.appt.pk)])

  def test_message_includes_professional_and_local_time(self):
    pro = AppointmentProfessional.objects.create(business=self.biz, name='Lucía')
    local = dt.datetime(2030, 1, 15, 14, 30, tzinfo=dj_timezone.get_default_timezone())
    Appointment.objects.filter(pk=self.appt.pk).update(
      professional=pro, start_at=local, end_at=local + dt.timedelta(minutes=30),
    )
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self.notify()
    notif = self.notifications().get()
    self.assertIn('15/01/2030 14:30', notif.message)
    self.assertIn('con Lucía', notif.message)
    self.assertIn('date=2030-01-15', notif.action_url)

  # 2. webhook duplicado (5 veces) → una sola notificación
  def test_duplicate_webhook_creates_single_notification(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    for _ in range(5):
      self.notify()
    self.assertEqual(self.notifications().count(), 1)

  def test_non_approved_statuses_do_not_notify(self):
    for status in ('pending', 'in_process', 'rejected'):
      self.mp.responses[TOKEN_A] = mp_payment(self.payment, status=status)
      self.notify()
    self.assertFalse(self.notifications().exists())

  def test_confirmed_notification_has_no_financial_data(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self.notify()
    notif = self.notifications().get()
    blob = f'{notif.title} {notif.message} {notif.action_url}'
    for fragment in (PAYMENT_ID, self.payment.external_reference, 'PREF-1', str(self.appt.public_token), 'ARS', '$'):
      self.assertNotIn(fragment, blob)

  # 6. fallo de notificación no revierte el turno confirmado
  def test_notification_failure_does_not_revert_confirmation(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    with patch(
      'apps.appointments.services.notifications.create_business_notification', side_effect=RuntimeError('boom'),
    ), self.assertLogs('apps.notifications.business_notifications', level='ERROR') as logs:
      delivery = self.notify()
    self.assertEqual(delivery.processing_status, S.PROCESSED)
    self._reload()
    self.assertEqual((self.appt.status, self.payment.status), (Appointment.Status.CONFIRMED, P.APPROVED))
    self.assertFalse(self.notifications().exists())
    self.assertTrue(any('appointment_confirmed' in line for line in logs.output))

  def test_notification_not_created_before_commit(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    with self.captureOnCommitCallbacks(execute=False) as callbacks:
      self._notify(PAYMENT_ID)
    self.assertFalse(self.notifications().exists())
    self.assertTrue(callbacks)


class RequiresReviewNotificationTests(_NotifBase):
  # 3. requires_review → notificación distinta
  def test_requires_review_creates_priority_notification(self):
    self.make_review()
    notif = self.notifications().get()
    self.assertEqual(notif.kind, Kind.APPOINTMENT_PAYMENT_REVIEW)
    self.assertEqual(notif.severity, BusinessNotification.Severity.CRITICAL)
    self.assertEqual(notif.title, 'Pago recibido — reserva requiere revisión')
    self.assertEqual(notif.dedupe_key, f'appointment_payment_review:{self.payment.pk}')
    self.assertIn('después de que venciera', notif.message)
    self.assertIn('no quedó confirmado', notif.message)
    self.assertNotIn('approved_after_expiry', notif.message)
    self.assertIn(str(self.appt.pk), notif.action_url)
    self.assertFalse(self.notifications().filter(kind=Kind.APPOINTMENT_CONFIRMED).exists())
    for fragment in (PAYMENT_ID, self.payment.external_reference, str(self.appt.public_token)):
      self.assertNotIn(fragment, notif.message)

  # 4. requires_review duplicado → una sola
  def test_duplicate_requires_review_single_notification(self):
    self.make_review()
    for _ in range(4):
      self.notify()
    self.assertEqual(self.notifications().count(), 1)

  def test_slot_conflict_reason_message(self):
    other = create_appointment(self.biz, self.service, status_=Appointment.Status.CONFIRMED)
    Appointment.objects.filter(pk=other.pk).update(start_at=self.appt.start_at, end_at=self.appt.end_at)
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self.notify()
    notif = self.notifications().get()
    self.assertEqual(notif.kind, Kind.APPOINTMENT_PAYMENT_REVIEW)
    self.assertIn('ya estaba ocupado', notif.message)

  def test_create_business_notification_is_idempotent(self):
    kwargs = dict(
      business_id=self.biz.pk, kind=Kind.APPOINTMENT_CONFIRMED, dedupe_key='appointment_confirmed:x', title='t',
    )
    first, created = create_business_notification(**kwargs)
    second, created_again = create_business_notification(**{**kwargs, 'title': 'otro'})
    self.assertEqual((created, created_again, first.pk), (True, False, second.pk))

  def test_external_action_url_is_dropped(self):
    notif, _ = create_business_notification(
      business_id=self.biz.pk, kind=Kind.APPOINTMENT_CONFIRMED, dedupe_key='k', title='t',
      action_url='https://evil.example/app/',
    )
    self.assertEqual(notif.action_url, '')


class NotificationTenantIsolationTests(_NotifBase):
  def setUp(self):
    super().setUp()
    self.biz_b = create_business(name='Barbería B', slug='barberia-b', token=TOKEN_B)
    self.user_a = User.objects.create_user(username='owner-a', password='x')
    self.user_b = User.objects.create_user(username='owner-b', password='x')
    Membership.objects.create(user=self.user_a, business=self.biz, role='owner')
    Membership.objects.create(user=self.user_b, business=self.biz_b, role='owner')

  # 5. Business A nunca notifica usuarios de B
  def test_business_a_event_is_invisible_to_b(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self.notify()
    self.assertEqual(self.notifications().count(), 1)
    self.assertFalse(self.notifications(self.biz_b).exists())

    self.client.force_authenticate(self.user_b)
    res = self.client.get(NOTIF_URL)
    self.assertEqual(res.status_code, 200, res.content)
    self.assertEqual((res.data['results'], res.data['unread_count']), ([], 0))
    notif = self.notifications().get()
    self.assertEqual(self.client.post(f'{NOTIF_URL}{notif.pk}/read/').status_code, 404)
    notif.refresh_from_db()
    self.assertIsNone(notif.read_at)

    self.client.force_authenticate(self.user_a)
    res = self.client.get(NOTIF_URL)
    self.assertEqual(res.data['unread_count'], 1)
    self.assertEqual(res.data['results'][0]['kind'], Kind.APPOINTMENT_CONFIRMED)
    self.assertNotIn('dedupe_key', res.data['results'][0])
    res = self.client.post(f'{NOTIF_URL}{notif.pk}/read/')
    self.assertEqual(res.status_code, 200)
    self.assertIsNotNone(res.data['read_at'])
    self.assertEqual(self.client.get(NOTIF_URL).data['unread_count'], 0)

  def test_only_owner_and_admin_see_appointment_kinds(self):
    """Reservas/pagos siguen siendo owner/admin. Desde CUSTOMER 07C.1 el
    manager entra al endpoint (avisos de recordatorios) pero no ve estos kinds."""
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self.notify()
    create_business_notification(
      business_id=self.biz.pk, kind=Kind.APPOINTMENT_PAYMENT_REVIEW,
      dedupe_key='appointment_payment_review:x', title='Pago a revisar',
    )
    # Un solo usuario extra (límite de asientos del plan); se le cambia el rol.
    user = User.objects.create_user(username='u-role', password='x')
    membership = Membership.objects.create(user=user, business=self.biz, role='admin')
    for role, status_code, unread in (('admin', 200, 2), ('manager', 200, 0), ('viewer', 403, None), ('staff', 403, None)):
      with self.subTest(role=role):
        Membership.objects.filter(pk=membership.pk).update(role=role)
        self.client.force_authenticate(user)
        res = self.client.get(NOTIF_URL)
        self.assertEqual(res.status_code, status_code)
        if unread is not None:
          self.assertEqual((len(res.data['results']), res.data['unread_count']), (unread, unread))

  def test_inactive_membership_cannot_read(self):
    Membership.objects.filter(user=self.user_a).update(status=Membership.Status.INACTIVE)
    self.client.force_authenticate(self.user_a)
    self.assertIn(self.client.get(NOTIF_URL).status_code, (403,))

  def test_anonymous_rejected(self):
    self.client.force_authenticate(None)
    self.assertIn(self.client.get(NOTIF_URL).status_code, (401, 403))


class PublicWhatsappContactTests(_NotifBase):
  def set_whatsapp(self, value=WHATSAPP, business=None):
    BusinessBranding.objects.update_or_create(business=business or self.biz, defaults={'whatsapp_phone': value})

  def get_public(self, appt=None):
    res = self.client.get(public_url(appt or self.appt))
    self.assertEqual(res.status_code, 200, res.content)
    return res.data

  def text_of(self, url):
    parts = urlsplit(url)
    self.assertEqual((parts.scheme, parts.netloc), ('https', 'wa.me'))
    return parse_qs(parts.query)['text'][0]

  # 7. WhatsApp configurado → URL pública válida
  def test_confirmed_with_whatsapp_returns_wa_me_url(self):
    self.set_whatsapp()
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self.notify()
    data = self.get_public()
    self.assertEqual(data['status'], 'confirmed')
    url = data['contact_whatsapp_url']
    # 10. solo wa.me
    self.assertTrue(url.startswith('https://wa.me/5491112345678?text='))
    text = self.text_of(url)
    self.assertIn('Barbería A', text)
    self.assertIn('Corte', text)
    self.assertIn('Mi reserva está confirmada', text)

  # 8. sin WhatsApp → null
  def test_without_whatsapp_url_is_null(self):
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self.notify()
    data = self.get_public()
    self.assertIn('contact_whatsapp_url', data)
    self.assertIsNone(data['contact_whatsapp_url'])

  # 9. teléfono inválido → sin URL (defensa si el dato llegó sin pasar por el serializer)
  def test_invalid_stored_phone_gives_no_url(self):
    for bad in ('javascript:alert(1)', '11 15 1234 5678', 'https://evil.example', '123'):
      with self.subTest(bad=bad):
        self.set_whatsapp(bad)
        self.appt.status = Appointment.Status.CONFIRMED
        self.appt.save(update_fields=['status'])
        self.assertIsNone(self.get_public()['contact_whatsapp_url'])

  # 11. mensaje confirmed sin datos financieros / 14. sin public_token
  def test_confirmed_message_has_no_financial_data_or_token(self):
    self.set_whatsapp()
    self.mp.responses[TOKEN_A] = mp_payment(self.payment)
    self.notify()
    url = self.get_public()['contact_whatsapp_url']
    text = self.text_of(url)
    for fragment in (
      str(self.appt.public_token), self.appt.public_token.hex, self.payment.external_reference,
      str(self.payment.pk), str(self.appt.pk), PAYMENT_ID, 'PREF-1',
    ):
      self.assertNotIn(fragment, url)
    for fragment in ('$', 'ARS', 'http', '/t/', 'seña', str(self.appt.deposit_amount)):
      self.assertNotIn(fragment, text)

  def test_confirmed_message_mentions_professional(self):
    self.set_whatsapp()
    pro = AppointmentProfessional.objects.create(business=self.biz, name='Lucía')
    Appointment.objects.filter(pk=self.appt.pk).update(professional=pro, status=Appointment.Status.CONFIRMED)
    self.assertIn('Corte con Lucía', self.text_of(self.get_public()['contact_whatsapp_url']))

  # 12. requires_review no afirma confirmación
  def test_requires_review_message_is_neutral(self):
    self.set_whatsapp()
    self.make_review()
    data = self.get_public()
    self.assertEqual(data['payment_status'], 'requires_review')
    self.assertNotEqual(data['status'], 'confirmed')
    text = self.text_of(data['contact_whatsapp_url'])
    self.assertIn('necesita revisión', text)
    for claim in ('confirmad', 'pagué', 'pago'):
      self.assertNotIn(claim, text.lower())

  def test_no_url_for_pending_uncertain_or_expired(self):
    self.set_whatsapp()
    self.assertIsNone(self.get_public()['contact_whatsapp_url'])  # pending_payment + pending
    AppointmentPayment.objects.filter(pk=self.payment.pk).update(status=P.UNCERTAIN)
    self.assertIsNone(self.get_public()['contact_whatsapp_url'])
    self.expire_hold()
    AppointmentPayment.objects.filter(pk=self.payment.pk).update(status=P.REJECTED)
    self.assertEqual(self.get_public()['status'], 'expired')
    self.assertIsNone(self.get_public()['contact_whatsapp_url'])
    Appointment.objects.filter(pk=self.appt.pk).update(status=Appointment.Status.CANCELLED)
    self.assertIsNone(self.get_public()['contact_whatsapp_url'])

  def test_uses_own_business_whatsapp_only(self):
    biz_b = create_business(name='Otra', slug='otra-b', token=TOKEN_B)
    self.set_whatsapp('+5493514567890', business=biz_b)
    self.appt.status = Appointment.Status.CONFIRMED
    self.appt.save(update_fields=['status'])
    self.assertIsNone(self.get_public()['contact_whatsapp_url'])

  # 13. serializer público no expone ids de provider ni refs
  def test_public_payload_has_no_provider_ids(self):
    self.set_whatsapp()
    self.make_review()
    data = self.get_public()
    self.assertNotIn('id', data)
    self.assertNotIn('whatsapp_phone', data)
    blob = repr(data)
    for fragment in (
      self.payment.external_reference, PAYMENT_ID, 'PREF-1', str(self.payment.pk), str(self.appt.pk),
      'approved_after_expiry', 'review_reason',
    ):
      self.assertNotIn(fragment, blob)

  def test_message_helper_never_includes_amount(self):
    self.appt.status = Appointment.Status.CONFIRMED
    for kind in (contact.CONTACT_CONFIRMED, contact.CONTACT_REQUIRES_REVIEW):
      text = contact.build_booking_message(self.appt, kind)
      self.assertNotIn(str(self.appt.deposit_amount), text)
      self.assertNotIn(str(int(self.appt.service_price)), text)


class ManualBookingDoesNotNotifyTests(_NotifBase):
  def test_admin_created_confirmed_appointment_does_not_notify(self):
    service = create_service(self.biz, deposit_type='none')
    with self.captureOnCommitCallbacks(execute=True):
      create_appointment(self.biz, service, status_=Appointment.Status.CONFIRMED, source=Appointment.Source.MANUAL)
    self.assertFalse(self.notifications().exists())


class UnrelatedIdsTests(_NotifBase):
  def test_notification_for_missing_payment_is_logged_not_raised(self):
    from ..services.notifications import schedule_appointment_payment_review
    with self.assertLogs('apps.notifications.business_notifications', level='ERROR'):
      with self.captureOnCommitCallbacks(execute=True):
        schedule_appointment_payment_review(uuid.uuid4())

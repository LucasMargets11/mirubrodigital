"""Slice 7D: listado interno de turnos por rango (`date_from`/`date_to`).

La vista semanal del panel pide los 7 días en UNA request. Los límites son
días locales del Business (`Business.timezone`), no UTC; un turno entra si su
`start_at` cae dentro del rango local pedido (inclusive en ambos extremos).
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as dj_timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Membership

from ..models import Appointment, AppointmentCategory, AppointmentPayment, AppointmentProfessional
from .test_appointment_checkout import create_business, create_service

User = get_user_model()
LIST_URL = '/api/v1/appointments/appointments/'
AR = ZoneInfo('America/Argentina/Buenos_Aires')  # -03:00, sin DST
S = Appointment.Status


def local(y, m, d, hh=10, mm=0) -> dt.datetime:
  return dt.datetime(y, m, d, hh, mm, tzinfo=AR)


class WeekRangeTests(APITestCase):
  def setUp(self):
    self.biz = create_business(name='Biz 7D', slug='biz-7d')
    self.service = create_service(self.biz)
    self.user = User.objects.create_user(username='owner-7d', password='x')
    Membership.objects.create(user=self.user, business=self.biz, role='owner')
    self.client.force_authenticate(self.user)

  def make(self, start: dt.datetime, *, business=None, service=None, status_=S.CONFIRMED,
           expires_at=None, professional=None, name='Juana') -> Appointment:
    business = business or self.biz
    service = service or self.service
    return Appointment.objects.create(
      business=business, service=service, professional=professional,
      customer_name=name, customer_phone='1155554444',
      start_at=start, end_at=start + dt.timedelta(minutes=30),
      status=status_, expires_at=expires_at, source=Appointment.Source.MANUAL,
      service_name=service.name, service_duration_minutes=service.duration_minutes,
      service_price=service.price, deposit_type=service.deposit_type, deposit_value=service.deposit_value,
    )

  def get_range(self, date_from, date_to, **extra):
    return self.client.get(LIST_URL, {'date_from': date_from, 'date_to': date_to, **extra})

  def ids(self, res) -> set[str]:
    self.assertEqual(res.status_code, 200, res.content)
    return {row['id'] for row in res.data}

  # 1. lunes → domingo devuelve los 7 días
  def test_monday_to_sunday_returns_all_seven_days(self):
    # Semana lun 2026-09-28 → dom 2026-10-04 (cruza de mes).
    week = [self.make(local(2026, 9, 28 + i) if i < 3 else local(2026, 10, i - 2)) for i in range(7)]
    res = self.get_range('2026-09-28', '2026-10-04')
    self.assertEqual(self.ids(res), {str(a.pk) for a in week})
    starts = [row['start_at'] for row in res.data]
    self.assertEqual(starts, sorted(starts))

  # 2. fuera del rango no aparece
  def test_outside_range_is_excluded(self):
    inside = self.make(local(2026, 9, 30))
    before = self.make(local(2026, 9, 27, 18))
    after = self.make(local(2026, 10, 5, 9))
    got = self.ids(self.get_range('2026-09-28', '2026-10-04'))
    self.assertIn(str(inside.pk), got)
    self.assertNotIn(str(before.pk), got)
    self.assertNotIn(str(after.pk), got)

  # 3. límites en Business.timezone (medianoche local, no UTC)
  def test_bounds_use_business_timezone(self):
    first_minute = self.make(local(2026, 9, 28, 0, 0))            # 03:00Z lunes
    prev_sunday_late = self.make(local(2026, 9, 27, 23, 30))      # 02:30Z del 28 (UTC ya es lunes)
    sunday_late = self.make(local(2026, 10, 4, 23, 30))           # 02:30Z del 5 (UTC ya es lunes)
    next_monday = self.make(local(2026, 10, 5, 0, 0))
    self.assertEqual(prev_sunday_late.start_at.astimezone(dt.timezone.utc).date(), dt.date(2026, 9, 28))
    got = self.ids(self.get_range('2026-09-28', '2026-10-04'))
    self.assertEqual(got, {str(first_minute.pk), str(sunday_late.pk)})
    got_next = self.ids(self.get_range('2026-10-05', '2026-10-11'))
    self.assertEqual(got_next, {str(next_monday.pk)})

  def test_other_business_timezone_is_respected(self):
    self.biz.timezone = 'Europe/Madrid'  # +02:00 en octubre
    self.biz.save(update_fields=['timezone'])
    madrid = ZoneInfo('Europe/Madrid')
    early = self.make(dt.datetime(2026, 10, 5, 0, 30, tzinfo=madrid))  # 22:30Z del 4
    got = self.ids(self.get_range('2026-10-05', '2026-10-11'))
    self.assertEqual(got, {str(early.pk)})
    self.assertEqual(self.ids(self.get_range('2026-09-28', '2026-10-04')), set())

  # 4. cambio de mes
  def test_month_boundary(self):
    sep = self.make(local(2026, 9, 30, 23, 59))
    oct_ = self.make(local(2026, 10, 1, 0, 0))
    self.assertEqual(self.ids(self.get_range('2026-09-28', '2026-10-04')), {str(sep.pk), str(oct_.pk)})
    self.assertEqual(self.ids(self.get_range('2026-10-01', '2026-10-01')), {str(oct_.pk)})

  # 5. cambio de año (lun 2026-12-28 → dom 2027-01-03)
  def test_year_boundary(self):
    dec = self.make(local(2026, 12, 31, 23, 30))
    jan = self.make(local(2027, 1, 3, 20))
    outside = self.make(local(2027, 1, 4, 0, 0))
    self.assertEqual(self.ids(self.get_range('2026-12-28', '2027-01-03')), {str(dec.pk), str(jan.pk)})
    self.assertEqual(self.ids(self.get_range('2027-01-04', '2027-01-10')), {str(outside.pk)})

  # 6. aislamiento tenant
  def test_tenant_isolation(self):
    mine = self.make(local(2026, 9, 29))
    other_biz = create_business(name='Biz B', slug='biz-b-7d')
    other_service = create_service(other_biz)
    foreign = self.make(local(2026, 9, 29), business=other_biz, service=other_service)
    got = self.ids(self.get_range('2026-09-28', '2026-10-04'))
    self.assertEqual(got, {str(mine.pk)})
    self.assertNotIn(str(foreign.pk), got)

  # 7. effective expired dentro del rango
  def test_effective_expired_in_range(self):
    stale = self.make(local(2026, 10, 2), status_=S.PENDING_PAYMENT,
                      expires_at=dj_timezone.now() - dt.timedelta(minutes=1))
    live = self.make(local(2026, 10, 3), status_=S.PENDING_PAYMENT,
                     expires_at=dj_timezone.now() + dt.timedelta(minutes=10))
    res = self.get_range('2026-09-28', '2026-10-04')
    rows = {row['id']: row for row in res.data}
    self.assertEqual(rows[str(stale.pk)]['effective_status'], 'expired')
    self.assertEqual(rows[str(stale.pk)]['status'], 'pending_payment')
    self.assertEqual(rows[str(live.pk)]['effective_status'], 'pending_payment')
    self.assertEqual(self.ids(self.get_range('2026-09-28', '2026-10-04', status='expired')), {str(stale.pk)})
    self.assertEqual(self.ids(self.get_range('2026-09-28', '2026-10-04', status='pending_payment')), {str(live.pk)})

  # 8. payment_summary presente
  def test_payment_summary_present(self):
    paid = self.make(local(2026, 9, 29))
    review = self.make(local(2026, 9, 30))
    plain = self.make(local(2026, 10, 1))
    for appt, st in ((paid, AppointmentPayment.Status.APPROVED), (review, AppointmentPayment.Status.REQUIRES_REVIEW)):
      pid = uuid.uuid4()
      AppointmentPayment.objects.create(
        id=pid, business=self.biz, appointment=appt,
        external_reference=AppointmentPayment.build_external_reference(pid),
        amount=Decimal('30.00'), status=st, provider_payment_id=f'mp-{pid.hex[:8]}',
        review_reason='slot_conflict' if st == AppointmentPayment.Status.REQUIRES_REVIEW else '',
        paid_at=dj_timezone.now(),
      )
    res = self.get_range('2026-09-28', '2026-10-04')
    rows = {row['id']: row for row in res.data}
    self.assertEqual(rows[str(paid.pk)]['payment_summary']['status'], 'approved')
    self.assertTrue(rows[str(review.pk)]['payment_summary']['requires_review'])
    self.assertIsNone(rows[str(plain.pk)]['payment_summary'])

  # 9. filtro de status sigue funcionando
  def test_status_filter(self):
    confirmed = self.make(local(2026, 9, 29, 9))
    cancelled = self.make(local(2026, 9, 29, 11), status_=S.CANCELLED)
    self.assertEqual(self.ids(self.get_range('2026-09-28', '2026-10-04', status='confirmed')), {str(confirmed.pk)})
    self.assertEqual(self.ids(self.get_range('2026-09-28', '2026-10-04', status='cancelled')), {str(cancelled.pk)})

  def test_professional_filter(self):
    pro = AppointmentProfessional.objects.create(business=self.biz, name='Ana')
    with_pro = self.make(local(2026, 9, 29, 9), professional=pro)
    without = self.make(local(2026, 9, 29, 11))
    self.assertEqual(self.ids(self.get_range('2026-09-28', '2026-10-04', professional=str(pro.pk))), {str(with_pro.pk)})
    self.assertEqual(self.ids(self.get_range('2026-09-28', '2026-10-04', professional='null')), {str(without.pk)})

  # 10. rango inválido → 400
  def test_invalid_range_400(self):
    cases = [
      {'date_from': '2026-09-28'},
      {'date_to': '2026-10-04'},
      {'date_from': 'nope', 'date_to': '2026-10-04'},
      {'date_from': '2026-09-28', 'date_to': '2026-13-01'},
      {'date_from': '2026-10-04', 'date_to': '2026-09-28'},
      {'date_from': '2026-09-28', 'date_to': '2026-10-04', 'date': '2026-09-29'},
    ]
    for params in cases:
      with self.subTest(params=params):
        res = self.client.get(LIST_URL, params)
        self.assertEqual(res.status_code, 400, res.content)

  # 11. rango excesivo → 400 (31 días inclusive es el máximo)
  def test_excessive_range_400(self):
    self.assertEqual(self.get_range('2026-10-01', '2026-10-31').status_code, 200)
    res = self.get_range('2026-10-01', '2026-11-01')
    self.assertEqual(res.status_code, 400)
    self.assertIn('date_to', res.data)

  # 12. filtro de un solo día sigue compatible
  def test_single_day_filter_still_works(self):
    monday = self.make(local(2026, 9, 28, 0, 0))
    tuesday = self.make(local(2026, 9, 29, 12))
    res = self.client.get(LIST_URL, {'date': '2026-09-28'})
    self.assertEqual(self.ids(res), {str(monday.pk)})
    self.assertNotIn(str(tuesday.pk), self.ids(res))
    # Fecha inválida en `date`: comportamiento previo (lista vacía, no 400).
    res = self.client.get(LIST_URL, {'date': 'nope'})
    self.assertEqual(res.status_code, 200)
    self.assertEqual(res.data, [])

  # Performance: una semana = una request con queries constantes (sin N+1).
  def test_query_count_is_constant(self):
    category = AppointmentCategory.objects.create(business=self.biz, name='Pelo')
    self.service.category = category
    self.service.save(update_fields=['category'])
    pro = AppointmentProfessional.objects.create(business=self.biz, name='Ana')
    self.make(local(2026, 9, 28), professional=pro)

    def count():
      with CaptureQueriesContext(connection) as ctx:
        res = self.get_range('2026-09-28', '2026-10-04')
      self.assertEqual(res.status_code, 200)
      return len(ctx.captured_queries), len(res.data)

    base_queries, base_rows = count()
    for i in range(1, 7):
      self.make(local(2026, 9, 28 + i) if i < 3 else local(2026, 10, i - 2), professional=pro)
    more_queries, more_rows = count()
    self.assertEqual((base_rows, more_rows), (1, 7))
    self.assertEqual(more_queries, base_queries)

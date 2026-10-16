"""Slice 7B.1 — semántica canónica profesional/null.

Regla (server-side, `services.availability.service_requires_professional`):

- servicio SIN profesionales elegibles (activos, del Business, asignados):
  `professional=None` es el único valor válido;
- servicio CON al menos uno: el profesional es obligatorio.

Además, un turno legacy `professional=None` de un servicio que HOY tiene
profesionales ocupa todo el negocio en su intervalo (compatibilidad con datos
creados antes de esta regla, que no se migran).

Reproduce el bug de Slice 7A: mismo servicio con profesionales, mismo
horario, una reserva `professional=null` y otra `professional=X` → 2×201.
"""
from __future__ import annotations

import datetime as dt
import threading
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.apps import apps as django_apps
from django.core.cache import cache
from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.business.models import Business, BusinessPlan, Subscription

from ..models import Appointment, AppointmentProfessional, AppointmentSchedule, AppointmentService
from ..services.availability import ProfessionalRequired, compute_availability
from ..services.booking import SlotOverlap, ensure_no_overlap
from .test_appointments import _auth_client

MONDAY = dt.date(2030, 3, 4)
assert MONDAY.weekday() == 0
TZ = ZoneInfo('America/Argentina/Buenos_Aires')


def _iso(time_str: str) -> str:
    return f'{MONDAY.isoformat()}T{time_str}:00-03:00'


def _dt(time_str: str) -> dt.datetime:
    return dt.datetime.combine(MONDAY, dt.time.fromisoformat(time_str), tzinfo=TZ)


def _create_business(name='Modo Biz', slug='modo-biz'):
    biz = Business.objects.create(
        name=name, default_service='appointments', slug=slug, status='active',
        timezone='America/Argentina/Buenos_Aires',
    )
    Subscription.objects.create(
        business=biz, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active',
    )
    return biz


def _setup_business(test):
    """`service_plain`: sin profesionales. `service_pro`: Ana y Bruno."""
    test.biz = _create_business()
    test.service_plain = AppointmentService.objects.create(
        business=test.biz, name='Consulta', duration_minutes=30, price=Decimal('1000'),
    )
    test.service_pro = AppointmentService.objects.create(
        business=test.biz, name='Corte', duration_minutes=30, price=Decimal('2000'),
    )
    test.ana = AppointmentProfessional.objects.create(business=test.biz, name='Ana')
    test.bruno = AppointmentProfessional.objects.create(business=test.biz, name='Bruno')
    for prof in (test.ana, test.bruno):
        prof.services.add(test.service_pro)
        AppointmentSchedule.objects.create(
            business=test.biz, professional=prof, weekday=0, start_time='09:00', end_time='18:00',
        )
    AppointmentSchedule.objects.create(
        business=test.biz, professional=None, weekday=0, start_time='09:00', end_time='18:00',
    )


def _legacy_null(biz, service, start='10:00', end='10:30', **fields):
    """Turno `professional=None` creado directo en DB (como antes de 7B.1)."""
    defaults = dict(
        status=Appointment.Status.CONFIRMED, source=Appointment.Source.PUBLIC,
        customer_name='Legacy', customer_phone='1122334455',
        service_name=service.name, service_duration_minutes=service.duration_minutes,
        service_price=service.price, deposit_type=service.deposit_type, deposit_value=service.deposit_value,
    )
    defaults.update(fields)
    return Appointment.objects.create(
        business=biz, service=service, professional=None, start_at=_dt(start), end_at=_dt(end), **defaults,
    )


class _Base(APITestCase):
    def setUp(self):
        cache.clear()
        _setup_business(self)

    def _book(self, service, professional=None, start='10:00'):
        return self.client.post(f'/api/v1/appointments/public/{self.biz.slug}/bookings/', {
            'service': str(service.id),
            'professional': str(professional.id) if professional else None,
            'start': _iso(start),
            'customer_name': 'Cliente',
            'customer_phone': '1122334455',
        }, format='json')

    def _availability(self, service, professional=None):
        params = {'service': str(service.id), 'date': MONDAY.isoformat()}
        if professional is not None:
            params['professional'] = str(professional.id)
        return self.client.get(f'/api/v1/appointments/public/{self.biz.slug}/availability/', params)

    @staticmethod
    def _starts(resp):
        return [s['start'][11:16] for s in resp.data['slots']]


class PublicBookingModeTests(_Base):
    # 1 ---------------------------------------------------------------------------------
    def test_service_without_professionals_accepts_null(self):
        resp = self._book(self.service_plain)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIsNone(Appointment.objects.get().professional_id)

    # 2 ---------------------------------------------------------------------------------
    def test_service_without_professionals_rejects_professional(self):
        resp = self._book(self.service_plain, self.ana)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)
        self.assertFalse(Appointment.objects.exists())

    # 3 ---------------------------------------------------------------------------------
    def test_service_with_professionals_rejects_null(self):
        resp = self._book(self.service_pro)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['professional'], ['Este servicio requiere elegir un profesional.'])
        self.assertFalse(Appointment.objects.exists())

    def test_service_with_professionals_rejects_omitted_professional(self):
        resp = self.client.post(f'/api/v1/appointments/public/{self.biz.slug}/bookings/', {
            'service': str(self.service_pro.id), 'start': _iso('10:00'),
            'customer_name': 'Cliente', 'customer_phone': '1122334455',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)

    # 4 ---------------------------------------------------------------------------------
    def test_service_with_professionals_accepts_valid_professional(self):
        resp = self._book(self.service_pro, self.ana)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(Appointment.objects.get().professional_id, self.ana.id)

    # 5 ---------------------------------------------------------------------------------
    def test_professional_from_other_business_rejected(self):
        other = _create_business(name='Otro', slug='otro-modo-biz')
        foreign = AppointmentProfessional.objects.create(business=other, name='Zoe')
        foreign.services.add(self.service_pro)  # aun "asignado", es de otro tenant
        resp = self._book(self.service_pro, foreign)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)

    # 6 ---------------------------------------------------------------------------------
    def test_professional_not_assigned_to_service_rejected(self):
        carla = AppointmentProfessional.objects.create(business=self.biz, name='Carla')
        AppointmentSchedule.objects.create(
            business=self.biz, professional=carla, weekday=0, start_time='09:00', end_time='18:00',
        )
        resp = self._book(self.service_pro, carla)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)

    # 7 ---------------------------------------------------------------------------------
    def test_inactive_professional_rejected(self):
        self.ana.is_active = False
        self.ana.save(update_fields=['is_active'])
        resp = self._book(self.service_pro, self.ana)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)

    def test_service_whose_only_professionals_are_inactive_works_without_professional(self):
        for prof in (self.ana, self.bruno):
            prof.is_active = False
            prof.save(update_fields=['is_active'])
        self.assertEqual(self._book(self.service_pro).status_code, status.HTTP_201_CREATED)

    def test_professionals_endpoint_matches_rule(self):
        url = f'/api/v1/appointments/public/{self.biz.slug}/professionals/'
        self.assertEqual(self.client.get(url, {'service': str(self.service_plain.id)}).data, [])
        names = [p['name'] for p in self.client.get(url, {'service': str(self.service_pro.id)}).data]
        self.assertEqual(names, ['Ana', 'Bruno'])


class AvailabilityModeTests(_Base):
    # 8 ---------------------------------------------------------------------------------
    def test_availability_without_professional_for_service_with_professionals_rejected(self):
        resp = self._availability(self.service_pro)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)
        with self.assertRaises(ProfessionalRequired):
            compute_availability(business=self.biz, service_id=str(self.service_pro.id), target_date=MONDAY)

    # 9 ---------------------------------------------------------------------------------
    def test_availability_with_valid_professional(self):
        resp = self._availability(self.service_pro, self.ana)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['professional'], str(self.ana.id))
        self.assertIn('10:00', self._starts(resp))

    def test_availability_service_without_professionals(self):
        resp = self._availability(self.service_plain)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIsNone(resp.data['professional'])
        self.assertIn('10:00', self._starts(resp))
        # Con profesional: rechazado (no hay ninguno elegible).
        self.assertEqual(self._availability(self.service_plain, self.ana).status_code, status.HTTP_400_BAD_REQUEST)

    def test_internal_availability_applies_same_rule(self):
        _auth_client(self.client, self.biz)
        url = '/api/v1/appointments/availability/'
        resp = self.client.get(url, {'service': str(self.service_pro.id), 'date': MONDAY.isoformat()})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertIn('professional', resp.data)


class InternalPanelModeTests(_Base):
    URL = '/api/v1/appointments/appointments/'

    def setUp(self):
        super().setUp()
        _auth_client(self.client, self.biz)

    def _create(self, service, professional=None, start='10:00'):
        payload = {
            'service_id': str(service.id), 'start_at': _iso(start),
            'customer_name': 'Juana', 'customer_phone': '1122334455',
        }
        if professional is not None:
            payload['professional_id'] = str(professional.id)
        return self.client.post(self.URL, payload, format='json')

    # 10 --------------------------------------------------------------------------------
    def test_internal_create_respects_rule(self):
        resp = self._create(self.service_pro)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)
        resp = self._create(self.service_plain, self.ana)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)
        self.assertFalse(Appointment.objects.exists())

        self.assertEqual(self._create(self.service_pro, self.ana).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._create(self.service_plain, start='11:00').status_code, status.HTTP_201_CREATED)

    # 11 --------------------------------------------------------------------------------
    def test_change_service_to_one_with_professionals_requires_professional(self):
        appt_id = self._create(self.service_plain).data['id']
        resp = self.client.patch(f'{self.URL}{appt_id}/', {'service_id': str(self.service_pro.id)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)
        self.assertEqual(Appointment.objects.get(pk=appt_id).service_id, self.service_plain.id)

        resp = self.client.patch(
            f'{self.URL}{appt_id}/', {'service_id': str(self.service_pro.id), 'professional_id': str(self.ana.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        appt = Appointment.objects.get(pk=appt_id)
        self.assertEqual((appt.service_id, appt.professional_id), (self.service_pro.id, self.ana.id))

    def test_change_service_to_one_without_professionals_drops_professional(self):
        appt_id = self._create(self.service_pro, self.ana).data['id']
        resp = self.client.patch(f'{self.URL}{appt_id}/', {'service_id': str(self.service_plain.id)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)

        resp = self.client.patch(
            f'{self.URL}{appt_id}/', {'service_id': str(self.service_plain.id), 'professional_id': None},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIsNone(Appointment.objects.get(pk=appt_id).professional_id)

    def test_dropping_professional_of_service_with_professionals_rejected(self):
        appt_id = self._create(self.service_pro, self.ana).data['id']
        resp = self.client.patch(f'{self.URL}{appt_id}/', {'professional_id': None}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Appointment.objects.get(pk=appt_id).professional_id, self.ana.id)

    def test_reschedule_legacy_null_requires_professional(self):
        legacy = _legacy_null(self.biz, self.service_pro)
        resp = self.client.patch(f'{self.URL}{legacy.pk}/', {'start_at': _iso('12:00')}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)
        # Editar solo datos del cliente sigue permitido (no toca la ocupación).
        resp = self.client.patch(f'{self.URL}{legacy.pk}/', {'customer_name': 'Legacy Editado'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        # Cancelarlo también.
        self.assertEqual(self.client.delete(f'{self.URL}{legacy.pk}/').status_code, status.HTTP_204_NO_CONTENT)

    def test_reactivating_legacy_null_requires_professional(self):
        legacy = _legacy_null(self.biz, self.service_pro, status=Appointment.Status.CANCELLED)
        resp = self.client.patch(f'{self.URL}{legacy.pk}/', {'status': 'confirmed'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('professional', resp.data)
        legacy.refresh_from_db()
        self.assertEqual(legacy.status, Appointment.Status.CANCELLED)

        resp = self.client.patch(
            f'{self.URL}{legacy.pk}/', {'status': 'confirmed', 'professional_id': str(self.ana.id)}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        legacy.refresh_from_db()
        self.assertEqual((legacy.status, legacy.professional_id), (Appointment.Status.CONFIRMED, self.ana.id))


class LegacyNullOccupancyTests(_Base):
    # 12 --------------------------------------------------------------------------------
    def test_legacy_null_blocks_every_professional_in_its_interval(self):
        _legacy_null(self.biz, self.service_pro, '10:00', '10:30')
        for prof in (self.ana, self.bruno):
            starts = self._starts(self._availability(self.service_pro, prof))
            self.assertNotIn('10:00', starts)
            self.assertNotIn('09:45', starts)  # 09:45-10:15 se superpone
            self.assertIn('10:30', starts)
            self.assertEqual(self._book(self.service_pro, prof, '10:00').status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(self._book(self.service_pro, prof, '10:15').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._book(self.service_pro, self.ana, '10:30').status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.count(), 2)

    def test_legacy_null_blocks_internal_create_and_reschedule(self):
        _legacy_null(self.biz, self.service_pro, '10:00', '10:30')
        _auth_client(self.client, self.biz)
        url = '/api/v1/appointments/appointments/'
        base = {'service_id': str(self.service_pro.id), 'customer_name': 'Juana', 'customer_phone': '1122334455'}
        resp = self.client.post(url, {**base, 'professional_id': str(self.ana.id), 'start_at': _iso('10:00')}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start_at', resp.data)

        appt_id = self.client.post(
            url, {**base, 'professional_id': str(self.bruno.id), 'start_at': _iso('12:00')}, format='json',
        ).data['id']
        resp = self.client.patch(f'{url}{appt_id}/', {'start_at': _iso('10:00')}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start_at', resp.data)

    def test_non_occupying_legacy_null_does_not_block(self):
        _legacy_null(self.biz, self.service_pro, status=Appointment.Status.CANCELLED)
        _legacy_null(
            self.biz, self.service_pro, status=Appointment.Status.PENDING_PAYMENT,
            expires_at=dj_timezone.now() - dt.timedelta(minutes=1),
        )
        self.assertIn('10:00', self._starts(self._availability(self.service_pro, self.ana)))
        self.assertEqual(self._book(self.service_pro, self.ana, '10:00').status_code, status.HTTP_201_CREATED)

    def test_null_of_service_without_professionals_is_not_legacy(self):
        # Turno "del negocio" legítimo: no compite con la agenda de los profesionales.
        self.assertEqual(self._book(self.service_plain, start='10:00').status_code, status.HTTP_201_CREATED)
        self.assertIn('10:00', self._starts(self._availability(self.service_pro, self.ana)))
        self.assertEqual(self._book(self.service_pro, self.ana, '10:00').status_code, status.HTTP_201_CREATED)

    def test_null_becomes_legacy_when_service_gains_professionals(self):
        self.assertEqual(self._book(self.service_plain, start='10:00').status_code, status.HTTP_201_CREATED)
        self.ana.services.add(self.service_plain)
        # Ahora es ambiguo → ocupa a todo el negocio (Ana y Bruno).
        self.assertNotIn('10:00', self._starts(self._availability(self.service_pro, self.bruno)))
        self.assertEqual(self._book(self.service_pro, self.bruno, '10:00').status_code, status.HTTP_400_BAD_REQUEST)

    def test_legacy_null_still_blocks_business_agenda(self):
        _legacy_null(self.biz, self.service_pro, '10:00', '10:30')
        self.assertNotIn('10:00', self._starts(self._availability(self.service_plain)))
        self.assertEqual(self._book(self.service_plain, start='10:00').status_code, status.HTTP_400_BAD_REQUEST)

    def test_legacy_null_reoccupying_conflicts_with_any_professional(self):
        """Ruta del webhook (6B): confirmar tarde un legacy null revalida contra
        cualquier profesional del negocio (→ `slot_conflict` en `_review_reason`)."""
        legacy = _legacy_null(
            self.biz, self.service_pro, status=Appointment.Status.PENDING_PAYMENT,
            expires_at=dj_timezone.now() - dt.timedelta(minutes=1),
        )
        self.assertEqual(self._book(self.service_pro, self.bruno, '10:00').status_code, status.HTTP_201_CREATED)
        with self.assertRaises(SlotOverlap):
            ensure_no_overlap(
                business=self.biz, service=self.service_pro, professional=None,
                start_at=legacy.start_at, end_at=legacy.end_at, exclude_pk=legacy.pk,
            )

    # 15 --------------------------------------------------------------------------------
    def test_valid_pending_payment_occupies(self):
        self.service_pro.deposit_type = AppointmentService.DepositType.FIXED
        self.service_pro.deposit_value = Decimal('500')
        self.service_pro.save()
        resp = self._book(self.service_pro, self.ana, '10:00')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['status'], 'pending_payment')
        self.assertNotIn('10:00', self._starts(self._availability(self.service_pro, self.ana)))
        self.assertEqual(self._book(self.service_pro, self.ana, '10:00').status_code, status.HTTP_400_BAD_REQUEST)

        _legacy_null(
            self.biz, self.service_pro, '11:00', '11:30', status=Appointment.Status.PENDING_PAYMENT,
            expires_at=dj_timezone.now() + dt.timedelta(minutes=5),
        )
        self.assertNotIn('11:00', self._starts(self._availability(self.service_pro, self.bruno)))
        self.assertEqual(self._book(self.service_pro, self.bruno, '11:00').status_code, status.HTTP_400_BAD_REQUEST)


class Slice7ABugReproductionTests(_Base):
    """13 — Slice 7A: `null` + `professional=X`, mismo servicio y horario → 2×201.

    Antes de 7B.1 la reserva `null` lockeaba el `Business` y chequeaba solo
    turnos `null`; la de Ana lockeaba a Ana y chequeaba solo turnos de Ana:
    ambos carriles ignoraban al otro y confirmaban el mismo intervalo.
    """

    def _assert_single_occupant(self):
        occupying = Appointment.objects.occupying().filter(start_at=_dt('10:00'))
        self.assertEqual(occupying.count(), 1)
        self.assertEqual(occupying.get().professional_id, self.ana.id)

    def test_null_then_professional_no_longer_double_books(self):
        first = self._book(self.service_pro, None, '10:00')
        second = self._book(self.service_pro, self.ana, '10:00')
        self.assertEqual(
            (first.status_code, second.status_code), (status.HTTP_400_BAD_REQUEST, status.HTTP_201_CREATED),
        )
        self._assert_single_occupant()

    def test_professional_then_null_no_longer_double_books(self):
        first = self._book(self.service_pro, self.ana, '10:00')
        second = self._book(self.service_pro, None, '10:00')
        self.assertEqual(
            (first.status_code, second.status_code), (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST),
        )
        self._assert_single_occupant()


class ProfessionalModeConcurrencyTests(TransactionTestCase):
    """14 — PostgreSQL real, threads con conexiones propias."""

    # Ver `test_public_booking_concurrency.py` (flush con CASCADE).
    available_apps = [cfg.name for cfg in django_apps.get_app_configs()]

    def setUp(self):
        cache.clear()
        _setup_business(self)

    def _race(self, payloads):
        results: list[int] = []
        lock = threading.Lock()
        barrier = threading.Barrier(len(payloads))

        def attempt(payload):
            try:
                client = APIClient()
                barrier.wait()
                resp = client.post(f'/api/v1/appointments/public/{self.biz.slug}/bookings/', payload, format='json')
                with lock:
                    results.append(resp.status_code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=attempt, args=(p,)) for p in payloads]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results

    def _payload(self, professional):
        return {
            'service': str(self.service_pro.id),
            'professional': str(professional.id) if professional else None,
            'start': _iso('10:00'),
            'customer_name': 'Cliente concurrente',
            'customer_phone': '1122334455',
        }

    def test_five_mixed_null_and_professional_requests_single_winner(self):
        results = self._race([self._payload(p) for p in (None, self.ana, None, self.ana, self.ana)])
        self.assertEqual(sorted(results), [201, 400, 400, 400, 400], results)
        occupying = Appointment.objects.occupying().filter(business=self.biz)
        self.assertEqual(occupying.count(), 1)
        self.assertEqual(occupying.get().professional_id, self.ana.id)

    def test_five_requests_same_professional_single_winner(self):
        results = self._race([self._payload(self.ana) for _ in range(5)])
        self.assertEqual(sorted(results), [201, 400, 400, 400, 400], results)
        self.assertEqual(Appointment.objects.filter(business=self.biz).count(), 1)

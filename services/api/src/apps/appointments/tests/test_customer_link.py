"""Tests para el vínculo `Appointment` ↔ `Customer` (Turnos CUSTOMER 01).

Cubre: resolución por teléfono normalizado dentro del `Business` (booking
público y alta manual), snapshots intactos, `Customer` existente no mutado,
aislamiento multi-tenant, duplicados legacy sin merge, teléfono no
utilizable sin dedupe por nombre, y re-resolución solo cuando cambia la
identidad telefónica al editar.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.customers.models import Customer
from apps.customers.phone import normalize_phone_for_matching

from ..models import Appointment, AppointmentProfessional, AppointmentSchedule, AppointmentService
from ..services.customer_link import resolve_customer_for_appointment
from .test_appointments import MONDAY, _auth_client, _create_business, _iso

PUBLIC_PHONE = '+54 9 11 5555-5555'


class NormalizePhoneForMatchingTests(SimpleTestCase):

    def test_formatting_differences_collapse_to_digits(self):
        for raw in ('+54 9 11 5555-5555', '549115555 5555', '(54) 9-11-5555.5555', ' +5491155555555 '):
            self.assertEqual(normalize_phone_for_matching(raw), '5491155555555', raw)

    def test_no_country_or_prefix_inference(self):
        # Sin adivinar: el formato nacional AR no se fusiona con el internacional.
        self.assertEqual(normalize_phone_for_matching('011 5555-5555'), '01155555555')
        self.assertNotEqual(normalize_phone_for_matching('011 5555-5555'), normalize_phone_for_matching(PUBLIC_PHONE))

    def test_unusable_values_return_none(self):
        for raw in ('', '   ', 'abcdef', '11 5555-5555 int 2', '12345', '1' * 16, '54+911', None, 123456):
            self.assertIsNone(normalize_phone_for_matching(raw), raw)


class CustomerLinkBaseMixin:

    def _make_business_with_agenda(self, name='Turnos Biz', slug='turnos-biz'):
        biz = _create_business(name=name, slug=slug)
        service = AppointmentService.objects.create(
            business=biz, name='Corte', duration_minutes=30, price=Decimal('1000'),
            deposit_type=AppointmentService.DepositType.NONE,
        )
        professional = AppointmentProfessional.objects.create(business=biz, name='Ana')
        professional.services.add(service)
        for pro in (None, professional):
            AppointmentSchedule.objects.create(
                business=biz, professional=pro, weekday=MONDAY.weekday(), start_time='09:00', end_time='18:00',
            )
        return biz, service, professional


class PublicBookingCustomerLinkTests(CustomerLinkBaseMixin, APITestCase):

    def setUp(self):
        cache.clear()
        self.biz, self.service, self.professional = self._make_business_with_agenda()

    def _post(self, slug=None, hour=10, **overrides):
        payload = {
            'service': str(self.service.id),
            'professional': str(self.professional.id),
            'start': _iso(MONDAY, f'{hour:02d}:00'),
            'customer_name': 'Cliente de prueba',
            'customer_phone': PUBLIC_PHONE,
            'customer_email': 'cliente@example.com',
        }
        payload.update(overrides)
        return self.client.post(
            f'/api/v1/appointments/public/{slug or self.biz.slug}/bookings/', payload, format='json',
        )

    def _appointment(self, resp):
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        return Appointment.objects.get(public_token=resp.data['public_token'])

    # 1 + 4 ------------------------------------------------------------------
    def test_creates_customer_when_missing_and_keeps_snapshots(self):
        appt = self._appointment(self._post())

        customer = Customer.objects.get(business=self.biz)
        self.assertEqual(appt.customer_id, customer.id)
        self.assertEqual(customer.name, 'Cliente de prueba')
        self.assertEqual(customer.phone, PUBLIC_PHONE)
        self.assertEqual(customer.email, 'cliente@example.com')
        self.assertEqual(customer.type, Customer.CustomerType.INDIVIDUAL)
        self.assertTrue(customer.is_active)
        self.assertEqual(appt.customer_name, 'Cliente de prueba')
        self.assertEqual(appt.customer_phone, PUBLIC_PHONE)
        self.assertEqual(appt.customer_email, 'cliente@example.com')

    def test_public_response_does_not_expose_customer(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertNotIn('customer', resp.data)
        self.assertNotIn('customer_id', resp.data)

    # 2 + 5 ------------------------------------------------------------------
    def test_reuses_existing_customer_by_normalized_phone_without_mutating_it(self):
        existing = Customer.objects.create(
            business=self.biz, name='Nombre en ficha', phone='5491155555555', email='ficha@example.com', note='VIP',
        )
        before = Customer.objects.values().get(pk=existing.pk)

        appt = self._appointment(self._post(customer_name='Otro Nombre', customer_email='otro@example.com'))

        self.assertEqual(appt.customer_id, existing.id)
        self.assertEqual(Customer.objects.filter(business=self.biz).count(), 1)
        self.assertEqual(Customer.objects.values().get(pk=existing.pk), before)
        # El turno conserva lo que ingresó el cliente, no los datos de la ficha.
        self.assertEqual(appt.customer_name, 'Otro Nombre')
        self.assertEqual(appt.customer_phone, PUBLIC_PHONE)
        self.assertEqual(appt.customer_email, 'otro@example.com')

    def test_second_booking_with_other_format_reuses_same_customer(self):
        first = self._appointment(self._post(hour=10))
        second = self._appointment(self._post(hour=11, customer_phone='(54) 9 11 5555 5555'))
        self.assertEqual(first.customer_id, second.customer_id)
        self.assertEqual(Customer.objects.filter(business=self.biz).count(), 1)

    def test_snapshot_survives_customer_change(self):
        appt = self._appointment(self._post())
        Customer.objects.filter(pk=appt.customer_id).update(phone='+54 9 11 0000-0000', name='Cambiado')
        appt.refresh_from_db()
        self.assertEqual(appt.customer_phone, PUBLIC_PHONE)
        self.assertEqual(appt.customer_name, 'Cliente de prueba')

    # 3 / 11 (tenant safety) -------------------------------------------------
    def test_same_phone_email_and_name_in_other_business_is_never_reused(self):
        other_biz, _, _ = self._make_business_with_agenda(name='Otro', slug='otro-biz')
        foreign = Customer.objects.create(
            business=other_biz, name='Cliente de prueba', phone=PUBLIC_PHONE, email='cliente@example.com',
        )

        appt = self._appointment(self._post())

        self.assertNotEqual(appt.customer_id, foreign.id)
        self.assertEqual(appt.customer.business_id, self.biz.id)
        # El email del otro negocio no bloquea guardarlo acá.
        self.assertEqual(appt.customer.email, 'cliente@example.com')
        self.assertEqual(Customer.objects.filter(business=other_biz).count(), 1)

    # 10 ---------------------------------------------------------------------
    def test_multiple_legacy_matches_are_not_linked_nor_merged(self):
        a = Customer.objects.create(business=self.biz, name='Dup A', phone='+54 9 11 5555-5555')
        b = Customer.objects.create(business=self.biz, name='Dup B', phone='5491155555555')

        appt = self._appointment(self._post())

        self.assertIsNone(appt.customer_id)
        self.assertEqual(set(Customer.objects.filter(business=self.biz).values_list('id', flat=True)), {a.id, b.id})

    def test_inactive_customer_is_not_reused(self):
        archived = Customer.objects.create(business=self.biz, name='Archivado', phone=PUBLIC_PHONE, is_active=False)
        appt = self._appointment(self._post())
        self.assertNotEqual(appt.customer_id, archived.id)
        archived.refresh_from_db()
        self.assertFalse(archived.is_active)

    def test_new_customer_skips_email_already_used_by_other_customer(self):
        Customer.objects.create(business=self.biz, name='Dueño del mail', phone='', email='cliente@example.com')
        appt = self._appointment(self._post(customer_email='CLIENTE@example.com'))
        self.assertEqual(appt.customer.email, '')
        self.assertEqual(appt.customer_email, 'CLIENTE@example.com')

    # 11 ---------------------------------------------------------------------
    def test_unusable_phone_does_not_dedupe_by_name(self):
        Customer.objects.create(business=self.biz, name='Cliente de prueba', phone='')
        appt = self._appointment(self._post(customer_phone='sin telefono'))
        self.assertIsNone(appt.customer_id)
        self.assertEqual(Customer.objects.filter(business=self.biz).count(), 1)

    def test_rejected_booking_does_not_create_customer(self):
        self._appointment(self._post(hour=10))
        resp = self._post(hour=10, customer_phone='+54 9 11 7777-7777')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertEqual(Customer.objects.filter(business=self.biz).count(), 1)


class InternalAppointmentCustomerLinkTests(CustomerLinkBaseMixin, APITestCase):

    URL = '/api/v1/appointments/appointments/'

    def setUp(self):
        self.biz, self.service, self.professional = self._make_business_with_agenda()
        _auth_client(self.client, self.biz, role='owner')
        self.other_service = AppointmentService.objects.create(
            business=self.biz, name='Barba', duration_minutes=30, price=Decimal('500'),
        )
        self.professional.services.add(self.other_service)
        self.other_pro = AppointmentProfessional.objects.create(business=self.biz, name='Beto')
        self.other_pro.services.add(self.service, self.other_service)
        AppointmentSchedule.objects.create(
            business=self.biz, professional=self.other_pro, weekday=MONDAY.weekday(),
            start_time='09:00', end_time='18:00',
        )

    def _create(self, **overrides):
        payload = {
            'service_id': str(self.service.id),
            'professional_id': str(self.professional.id),
            'start_at': _iso(MONDAY, '10:00'),
            'customer_name': 'Juana Pérez',
            'customer_phone': '11 2233-4455',
            'customer_email': 'juana@example.com',
            'notes': 'Primera vez',
        }
        payload.update(overrides)
        resp = self.client.post(self.URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        return resp

    def _patch(self, appointment_id, **changes):
        resp = self.client.patch(f'{self.URL}{appointment_id}/', changes, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp

    # 6 ----------------------------------------------------------------------
    def test_manual_creation_links_customer_and_exposes_customer_id(self):
        existing = Customer.objects.create(business=self.biz, name='Juana', phone='1122334455')
        resp = self._create()
        self.assertEqual(resp.data['customer_id'], str(existing.id))
        appt = Appointment.objects.get(pk=resp.data['id'])
        self.assertEqual(appt.customer_id, existing.id)
        self.assertEqual(appt.customer_phone, '11 2233-4455')
        self.assertEqual(appt.source, Appointment.Source.MANUAL)

    def test_manual_creation_creates_customer_when_missing(self):
        resp = self._create()
        customer = Customer.objects.get(business=self.biz)
        self.assertEqual(resp.data['customer_id'], str(customer.id))
        self.assertEqual(customer.phone, '11 2233-4455')

    def test_foreign_customer_id_is_rejected(self):
        # CUSTOMER 05: `customer_id` es input, pero acotado al Business
        # (cobertura completa en test_customer_picker).
        foreign_biz, _, _ = self._make_business_with_agenda(name='Otro', slug='otro-biz')
        foreign = Customer.objects.create(business=foreign_biz, name='Ajeno', phone='999999999')
        payload = {
            'service_id': str(self.service.id), 'professional_id': str(self.professional.id),
            'start_at': _iso(MONDAY, '10:00'), 'customer_name': 'Juana', 'customer_phone': '11 2233-4455',
            'customer_id': str(foreign.id),
        }
        resp = self.client.post(self.URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('customer_id', resp.data)
        self.assertFalse(Appointment.objects.exists())

    # 7 ----------------------------------------------------------------------
    def test_reschedule_and_non_identity_edits_keep_customer(self):
        resp = self._create()
        appt_id, customer_id = resp.data['id'], resp.data['customer_id']

        self._patch(appt_id, start_at=_iso(MONDAY, '12:00'))
        self._patch(appt_id, professional_id=str(self.other_pro.id))
        self._patch(appt_id, service_id=str(self.other_service.id))
        self._patch(appt_id, notes='Cambio', customer_name='Juana P.', customer_email='j@example.com')
        resp = self._patch(appt_id, customer_phone='(11) 2233 4455')  # solo formato

        self.assertEqual(resp.data['customer_id'], customer_id)
        self.assertEqual(Customer.objects.filter(business=self.biz).count(), 1)
        appt = Appointment.objects.get(pk=appt_id)
        self.assertEqual(appt.customer_phone, '(11) 2233 4455')
        self.assertEqual(appt.customer_name, 'Juana P.')
        customer = Customer.objects.get(pk=customer_id)
        self.assertEqual(customer.name, 'Juana Pérez')
        self.assertEqual(customer.email, 'juana@example.com')

    # 8 ----------------------------------------------------------------------
    def test_phone_change_re_resolves_within_business(self):
        resp = self._create()
        appt_id, original_customer_id = resp.data['id'], resp.data['customer_id']
        other = Customer.objects.create(business=self.biz, name='Pedro', phone='+54 11 9999-8888')
        foreign_biz, _, _ = self._make_business_with_agenda(name='Otro', slug='otro-biz')
        Customer.objects.create(business=foreign_biz, name='Ajeno', phone='1177776666')

        resp = self._patch(appt_id, customer_phone='5411 9999 8888')
        self.assertEqual(resp.data['customer_id'], str(other.id))

        resp = self._patch(appt_id, customer_phone='11 7777-6666', customer_name='Nuevo')
        new_customer = Customer.objects.get(pk=resp.data['customer_id'])
        self.assertEqual(new_customer.business_id, self.biz.id)
        self.assertEqual(new_customer.name, 'Nuevo')

        # Nada se fusionó ni borró.
        self.assertTrue(Customer.objects.filter(pk=original_customer_id).exists())
        self.assertEqual(Customer.objects.filter(business=self.biz).count(), 3)

    def test_phone_change_to_unusable_value_unlinks(self):
        resp = self._create()
        resp = self._patch(resp.data['id'], customer_phone='consultar por mail')
        self.assertIsNone(resp.data['customer_id'])

    # 9 ----------------------------------------------------------------------
    def test_legacy_appointment_without_customer_serializes_and_stays_unlinked(self):
        resp = self._create()
        Appointment.objects.filter(pk=resp.data['id']).update(customer=None)

        listing = self.client.get(f'{self.URL}?date={MONDAY.isoformat()}')
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        rows = listing.data['results'] if isinstance(listing.data, dict) else listing.data
        self.assertIsNone(rows[0]['customer_id'])
        self.assertEqual(rows[0]['customer_phone'], '11 2233-4455')

        # Editar sin cambiar el teléfono no hace backfill.
        resp = self._patch(resp.data['id'], start_at=_iso(MONDAY, '13:00'), customer_name='Juana Legacy')
        self.assertIsNone(resp.data['customer_id'])

    def test_deleting_customer_keeps_appointment(self):
        resp = self._create()
        Customer.objects.filter(pk=resp.data['customer_id']).delete()
        appt = Appointment.objects.get(pk=resp.data['id'])
        self.assertIsNone(appt.customer_id)
        self.assertEqual(appt.customer_name, 'Juana Pérez')


class ResolveCustomerForAppointmentTests(CustomerLinkBaseMixin, TestCase):

    def setUp(self):
        self.biz = _create_business()

    def test_blank_phone_returns_none_even_with_matching_name_and_email(self):
        Customer.objects.create(business=self.biz, name='Ana', phone='', email='ana@example.com')
        result = resolve_customer_for_appointment(
            business=self.biz, customer_name='Ana', customer_phone='', customer_email='ana@example.com',
        )
        self.assertIsNone(result)
        self.assertEqual(Customer.objects.count(), 1)

    def test_stored_phone_with_extra_text_is_not_matched(self):
        Customer.objects.create(business=self.biz, name='Ana', phone='1122334455 int 2')
        result = resolve_customer_for_appointment(
            business=self.biz, customer_name='Ana', customer_phone='11223344552',
        )
        self.assertEqual(result.phone, '11223344552')
        self.assertEqual(Customer.objects.count(), 2)

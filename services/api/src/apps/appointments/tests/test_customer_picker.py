"""Tests del `customer_id` explícito en el alta/edición interna de turnos
(Turnos CUSTOMER 05 — CustomerPicker).

Cubre: vínculo explícito sin resolver por teléfono, snapshots del payload,
aislamiento multi-tenant (sin oráculo de existencia), Customer inactivo
bloqueado (salvo conservar el vínculo actual), cambio/conservación del FK
al editar, vínculo de turnos legacy `customer=NULL`, compatibilidad con el
resolver de CUSTOMER 01 y la búsqueda del listado canónico de Customers que
usa el picker.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.test import APITestCase

from apps.customers.models import Customer

from ..models import Appointment
from .test_appointments import MONDAY, _auth_client, _iso
from .test_customer_link import CustomerLinkBaseMixin


class CustomerPickerAppointmentTests(CustomerLinkBaseMixin, APITestCase):
    URL = '/api/v1/appointments/appointments/'

    def setUp(self):
        self.biz, self.service, self.professional = self._make_business_with_agenda()
        _auth_client(self.client, self.biz, role='owner')
        self.juan = Customer.objects.create(
            business=self.biz, name='Juan Pérez', phone='+54 9 11 4000-0001', email='juan@example.com', note='VIP',
        )
        self.maria = Customer.objects.create(business=self.biz, name='María Gómez', phone='11 4000-0002')
        self.foreign_biz, _, _ = self._make_business_with_agenda(name='Otro', slug='otro-biz')
        self.foreign = Customer.objects.create(business=self.foreign_biz, name='Ajeno', phone='11 4000-0003')

    def _payload(self, **overrides):
        payload = {
            'service_id': str(self.service.id),
            'professional_id': str(self.professional.id),
            'start_at': _iso(MONDAY, '10:00'),
            'customer_name': 'Juan - recepción',
            'customer_phone': '+54 9 11 4000-0001',
            'customer_email': 'recepcion@example.com',
        }
        payload.update(overrides)
        return payload

    def _create(self, **overrides):
        resp = self.client.post(self.URL, self._payload(**overrides), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        return resp

    def _patch(self, appointment_id, expected=status.HTTP_200_OK, **changes):
        resp = self.client.patch(f'{self.URL}{appointment_id}/', changes, format='json')
        self.assertEqual(resp.status_code, expected, resp.data)
        return resp

    # 1 + 2 ------------------------------------------------------------------
    def test_create_with_customer_id_links_it_and_keeps_payload_snapshots(self):
        resp = self._create(customer_id=str(self.juan.id))

        self.assertEqual(resp.data['customer_id'], str(self.juan.id))
        appt = Appointment.objects.get(pk=resp.data['id'])
        self.assertEqual(appt.customer_id, self.juan.id)
        self.assertEqual(appt.customer_name, 'Juan - recepción')
        self.assertEqual(appt.customer_email, 'recepcion@example.com')
        self.assertEqual(appt.customer_phone, '+54 9 11 4000-0001')

    def test_explicit_customer_wins_over_phone_match(self):
        # El teléfono del payload es el de María, pero el operador eligió a Juan.
        resp = self._create(customer_id=str(self.juan.id), customer_phone='11 4000-0002')
        self.assertEqual(resp.data['customer_id'], str(self.juan.id))
        self.assertEqual(Customer.objects.filter(business=self.biz).count(), 2)

    # 8 ----------------------------------------------------------------------
    def test_snapshots_never_modify_canonical_customer(self):
        before = Customer.objects.values().get(pk=self.juan.pk)
        resp = self._create(customer_id=str(self.juan.id), customer_phone='11 9999-0000')
        self._patch(resp.data['id'], customer_id=str(self.juan.id), customer_name='Otro nombre', customer_email='x@example.com')
        self.assertEqual(Customer.objects.values().get(pk=self.juan.pk), before)

    # 3 + 10 -----------------------------------------------------------------
    def test_foreign_customer_id_is_rejected_like_a_missing_one(self):
        foreign_resp = self.client.post(self.URL, self._payload(customer_id=str(self.foreign.id)), format='json')
        missing_resp = self.client.post(
            self.URL, self._payload(customer_id='00000000-0000-0000-0000-000000000000'), format='json',
        )

        self.assertEqual(foreign_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(missing_resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Mismo error para ajeno e inexistente: no revela que el id existe en otro tenant.
        self.assertEqual(
            str(foreign_resp.data['customer_id'][0]).replace(str(self.foreign.id), '<id>'),
            str(missing_resp.data['customer_id'][0]).replace('00000000-0000-0000-0000-000000000000', '<id>'),
        )
        self.assertNotIn('Ajeno', str(foreign_resp.data))
        self.assertFalse(Appointment.objects.exists())

    def test_foreign_customer_id_is_rejected_on_patch(self):
        resp = self._create(customer_id=str(self.juan.id))
        self._patch(resp.data['id'], expected=status.HTTP_400_BAD_REQUEST, customer_id=str(self.foreign.id))
        self.assertEqual(Appointment.objects.get(pk=resp.data['id']).customer_id, self.juan.id)

    def test_null_customer_id_is_rejected(self):
        resp = self.client.post(self.URL, self._payload(customer_id=None), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # 4 ----------------------------------------------------------------------
    def test_inactive_customer_is_blocked_and_not_reactivated(self):
        Customer.objects.filter(pk=self.maria.pk).update(is_active=False)

        resp = self.client.post(self.URL, self._payload(customer_id=str(self.maria.id)), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('customer_id', resp.data)

        appt = self._create(customer_id=str(self.juan.id))
        self._patch(appt.data['id'], expected=status.HTTP_400_BAD_REQUEST, customer_id=str(self.maria.id))
        self.assertEqual(Appointment.objects.get(pk=appt.data['id']).customer_id, self.juan.id)
        self.assertFalse(Customer.objects.get(pk=self.maria.pk).is_active)

    def test_keeping_current_link_is_allowed_after_customer_was_deactivated(self):
        resp = self._create(customer_id=str(self.juan.id))
        Customer.objects.filter(pk=self.juan.pk).update(is_active=False)

        resp = self._patch(resp.data['id'], customer_id=str(self.juan.id), notes='Sigue igual')
        self.assertEqual(resp.data['customer_id'], str(self.juan.id))
        self.assertFalse(Customer.objects.get(pk=self.juan.pk).is_active)

    # 5 ----------------------------------------------------------------------
    def test_create_without_customer_id_still_uses_phone_resolver(self):
        resp = self._create(customer_phone='5491140000001')  # Juan, otro formato
        self.assertEqual(resp.data['customer_id'], str(self.juan.id))

        resp = self._create(start_at=_iso(MONDAY, '11:00'), customer_phone='11 7000-0000', customer_name='Nueva')
        created = Customer.objects.get(pk=resp.data['customer_id'])
        self.assertEqual(created.business_id, self.biz.id)
        self.assertEqual(created.name, 'Nueva')

    # 6 ----------------------------------------------------------------------
    def test_patch_changes_customer_fk_and_snapshots(self):
        resp = self._create(customer_id=str(self.juan.id))
        resp = self._patch(
            resp.data['id'], customer_id=str(self.maria.id),
            customer_name='María Gómez', customer_phone='11 4000-0002', customer_email='',
        )
        self.assertEqual(resp.data['customer_id'], str(self.maria.id))
        appt = Appointment.objects.get(pk=resp.data['id'])
        self.assertEqual(appt.customer_id, self.maria.id)
        self.assertEqual(appt.customer_name, 'María Gómez')
        self.assertEqual(appt.customer_phone, '11 4000-0002')

    # 7 ----------------------------------------------------------------------
    def test_patch_with_same_customer_keeps_fk_even_if_phone_changes(self):
        resp = self._create(customer_id=str(self.juan.id))
        # Sin customer_id el cambio de teléfono re-resolvería a María (CUSTOMER 01);
        # con el Customer explícito el vínculo se conserva.
        resp = self._patch(resp.data['id'], customer_id=str(self.juan.id), customer_phone='11 4000-0002')
        self.assertEqual(resp.data['customer_id'], str(self.juan.id))
        self.assertEqual(Appointment.objects.get(pk=resp.data['id']).customer_phone, '11 4000-0002')

    def test_patch_without_customer_id_keeps_fk_on_non_identity_edits(self):
        resp = self._create(customer_id=str(self.juan.id))
        resp = self._patch(resp.data['id'], customer_name='Juan P.', start_at=_iso(MONDAY, '12:00'))
        self.assertEqual(resp.data['customer_id'], str(self.juan.id))

    # 9 ----------------------------------------------------------------------
    def test_legacy_null_appointment_can_be_linked_explicitly(self):
        resp = self._create()
        Appointment.objects.filter(pk=resp.data['id']).update(customer=None)

        # Editar sin customer_id no auto-vincula (abrir/guardar el modal no hace backfill).
        resp = self._patch(resp.data['id'], notes='Legacy')
        self.assertIsNone(resp.data['customer_id'])

        resp = self._patch(resp.data['id'], customer_id=str(self.maria.id))
        self.assertEqual(resp.data['customer_id'], str(self.maria.id))
        appt = Appointment.objects.get(pk=resp.data['id'])
        # Vincular no pisa los snapshots que no vinieron en el payload.
        self.assertEqual(appt.customer_name, 'Juan - recepción')

    def test_viewer_cannot_write_customer_id(self):
        resp = self._create()
        viewer_client = self.client_class()
        _auth_client_named(viewer_client, self.biz, 'viewer')
        resp = viewer_client.patch(f'{self.URL}{resp.data["id"]}/', {'customer_id': str(self.maria.id)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


def _auth_client_named(client, business, role):
    from django.contrib.auth import get_user_model

    from apps.accounts.models import Membership

    user, created = get_user_model().objects.get_or_create(username=f'{role}-{business.slug}')
    if created:
        Membership.objects.create(user=user, business=business, role=role)
    client.force_authenticate(user=user)
    return user


class CustomerPickerSearchTests(CustomerLinkBaseMixin, APITestCase):
    """El picker reutiliza `GET /api/v1/customers/?search=` (sin endpoint propio de Turnos)."""

    URL = '/api/v1/customers/'

    def setUp(self):
        self.biz, _, _ = self._make_business_with_agenda()
        self.foreign_biz, _, _ = self._make_business_with_agenda(name='Otro', slug='otro-biz')
        Customer.objects.create(business=self.biz, name='Juan Pérez', phone='11 4000-0001', email='juan@example.com')
        Customer.objects.create(business=self.biz, name='Juana Baja', phone='11 4000-0009', is_active=False)
        Customer.objects.create(business=self.foreign_biz, name='Juan Ajeno', phone='11 4000-0001')

    def _search(self, term, role='manager'):
        _auth_client_named(self.client, self.biz, role)
        resp = self.client.get(self.URL, {'search': term, 'limit': 8})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return [row['name'] for row in resp.data['results']]

    def test_search_by_name_phone_and_email_is_scoped_to_business_and_active(self):
        self.assertEqual(self._search('Juan'), ['Juan Pérez'])
        self.assertEqual(self._search('4000-0001'), ['Juan Pérez'])
        self.assertEqual(self._search('juan@example'), ['Juan Pérez'])
        self.assertEqual(self._search('4000-0009'), [])

    def test_turnos_manager_can_create_customer_inline(self):
        _auth_client_named(self.client, self.biz, 'manager')
        resp = self.client.post(self.URL, {'name': 'Nuevo Inline', 'phone': '11 5000-0000'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(Customer.objects.get(pk=resp.data['id']).business_id, self.biz.id)

    def test_turnos_viewer_can_search_but_not_create(self):
        self.assertEqual(self._search('Juan', role='viewer'), ['Juan Pérez'])
        resp = self.client.post(self.URL, {'name': 'X'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

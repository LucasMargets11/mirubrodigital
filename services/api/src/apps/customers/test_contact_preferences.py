"""Preferencias y consentimiento de contacto del Customer (CUSTOMER 07D.1).

`/api/v1/customers/{id}/contact-preferences/` (GET, PATCH). Cubre defaults
apagados sin crear fila, consentimiento obligatorio al encender
WhatsApp/email, conservación del registro al apagar, `do_not_contact` con
prioridad, disponibilidad real del canal según teléfono/email, RBAC (lectura
`view_customers`, escritura `manage_customer_contact_preferences` —
owner/admin/manager), aislamiento entre tenants y que ni Turnos ni la reserva
pública inventan consentimiento.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.rbac import permissions_for_service
from apps.appointments.models import Appointment, AppointmentSchedule, AppointmentService
from apps.appointments.tests.test_customer_core_access import LIST_URL, _gestion_business, _login, _turnos_business

from .contact_preferences import can_contact_automatically
from .models import Customer, CustomerContactPreferences

PERMISSION = 'manage_customer_contact_preferences'


def _url(customer):
    return f'{LIST_URL}{customer.pk}/contact-preferences/'


class TurnosContactPreferencesTests(APITestCase):

    def setUp(self):
        self.biz = _turnos_business(slug='prefs-turnos')
        self.customer = Customer.objects.create(
            business=self.biz, name='Ana', phone='+54 9 11 5555-0101', email='ana@example.com',
        )

    def _patch(self, payload, customer=None):
        return self.client.patch(_url(customer or self.customer), payload, format='json')

    # 1. defaults
    def test_defaults_off_without_creating_row(self):
        _login(self.client, self.biz, 'owner')
        resp = self.client.get(_url(self.customer))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(set(resp.data), {
            'customer_id', 'whatsapp_enabled', 'email_enabled', 'phone_enabled', 'preferred_channel', 'do_not_contact',
            'whatsapp_consent_at', 'whatsapp_consent_source', 'email_consent_at', 'email_consent_source',
            'channels', 'updated_at',
        })
        self.assertEqual(resp.data['customer_id'], str(self.customer.pk))
        self.assertFalse(resp.data['whatsapp_enabled'])
        self.assertFalse(resp.data['email_enabled'])
        self.assertTrue(resp.data['phone_enabled'])  # canal manual
        self.assertIsNone(resp.data['preferred_channel'])
        self.assertFalse(resp.data['do_not_contact'])
        self.assertIsNone(resp.data['whatsapp_consent_at'])
        self.assertIsNone(resp.data['email_consent_at'])
        self.assertIsNone(resp.data['updated_at'])
        self.assertEqual(resp.data['channels'], {
            'whatsapp': {'usable': False, 'reason': 'disabled'},
            'email': {'usable': False, 'reason': 'disabled'},
            'phone': {'usable': True, 'reason': None},
        })
        self.assertFalse(CustomerContactPreferences.objects.exists())
        self.assertFalse(can_contact_automatically(self.customer, 'whatsapp'))
        self.assertFalse(can_contact_automatically(self.customer, 'email'))
        self.assertFalse(can_contact_automatically(self.customer, 'phone'))

    # 9. WhatsApp exige consentimiento
    def test_enable_whatsapp_requires_consent_confirmation(self):
        _login(self.client, self.biz, 'owner')
        for payload in ({'whatsapp_enabled': True}, {'whatsapp_enabled': True, 'whatsapp_consent_confirmed': False}):
            resp = self._patch(payload)
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, payload)
            self.assertIn('whatsapp_consent_confirmed', resp.data)
        self.assertFalse(CustomerContactPreferences.objects.exists())

        resp = self._patch({'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(resp.data['whatsapp_enabled'])
        self.assertIsNotNone(resp.data['whatsapp_consent_at'])
        self.assertEqual(resp.data['whatsapp_consent_source'], 'manual')
        self.assertEqual(resp.data['channels']['whatsapp'], {'usable': True, 'reason': None})
        self.assertIsNone(resp.data['email_consent_at'])
        prefs = CustomerContactPreferences.objects.get(customer=self.customer)
        self.assertEqual(prefs.business_id, self.biz.pk)
        self.assertTrue(can_contact_automatically(self.customer, 'whatsapp'))

    # 10. Email exige consentimiento
    def test_enable_email_requires_consent_confirmation(self):
        _login(self.client, self.biz, 'owner')
        resp = self._patch({'email_enabled': True, 'whatsapp_consent_confirmed': True})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email_consent_confirmed', resp.data)
        resp = self._patch({'email_enabled': True, 'email_consent_confirmed': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(resp.data['email_enabled'])
        self.assertIsNotNone(resp.data['email_consent_at'])
        self.assertIsNone(resp.data['whatsapp_consent_at'])
        self.assertTrue(can_contact_automatically(self.customer, 'email'))

    def test_already_enabled_channel_needs_no_new_confirmation(self):
        _login(self.client, self.biz, 'owner')
        first = self._patch({'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True}).data['whatsapp_consent_at']
        resp = self._patch({'whatsapp_enabled': True, 'preferred_channel': 'whatsapp'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['whatsapp_consent_at'], first)

    def test_consent_fields_cannot_be_forged(self):
        _login(self.client, self.biz, 'owner')
        forged = (dj_timezone.now() - dt.timedelta(days=400)).isoformat()
        resp = self._patch({
            'whatsapp_consent_at': forged, 'whatsapp_consent_source': 'imported',
            'whatsapp_consent_value': '5491100000000', 'email_consent_value': 'otro@example.com',
            'email_consent_at': forged, 'customer_id': '00000000-0000-0000-0000-000000000000',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIsNone(resp.data['whatsapp_consent_at'])
        self.assertIsNone(resp.data['whatsapp_consent_source'])
        self.assertIsNone(resp.data['email_consent_at'])
        self.assertEqual(resp.data['customer_id'], str(self.customer.pk))
        self.assertNotIn('whatsapp_consent_value', resp.data)
        prefs = CustomerContactPreferences.objects.get(customer=self.customer)
        self.assertIsNone(prefs.whatsapp_consent_value)
        self.assertIsNone(prefs.email_consent_value)
        # Al autorizar, el destino sale del Customer, nunca del payload.
        resp = self._patch({
            'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True, 'whatsapp_consent_value': '5491100000000',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        prefs.refresh_from_db()
        self.assertEqual(prefs.whatsapp_consent_value, '5491155550101')
        # Desde el panel no se puede afirmar un origen de sistema.
        for source in ('public_booking', 'imported', 'whatever'):
            resp = self._patch({'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True, 'consent_source': source})
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, source)
            self.assertIn('consent_source', resp.data)

    # 14. source
    def test_consent_source_saved_per_channel(self):
        _login(self.client, self.biz, 'owner')
        resp = self._patch({'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True, 'consent_source': 'customer_request'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        resp = self._patch({'email_enabled': True, 'email_consent_confirmed': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['whatsapp_consent_source'], 'customer_request')
        self.assertEqual(resp.data['email_consent_source'], 'manual')
        prefs = CustomerContactPreferences.objects.get(customer=self.customer)
        self.assertEqual(prefs.whatsapp_consent_source, CustomerContactPreferences.ConsentSource.CUSTOMER_REQUEST)
        self.assertEqual(prefs.email_consent_source, CustomerContactPreferences.ConsentSource.MANUAL)

    # 13. apagar conserva el registro
    def test_disable_channel_keeps_consent_and_reenable_renews_it(self):
        user = _login(self.client, self.biz, 'owner')
        enabled = self._patch({'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True, 'consent_source': 'customer_request'}).data
        resp = self._patch({'whatsapp_enabled': False})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertFalse(resp.data['whatsapp_enabled'])
        self.assertEqual(resp.data['whatsapp_consent_at'], enabled['whatsapp_consent_at'])
        self.assertEqual(resp.data['whatsapp_consent_source'], 'customer_request')
        self.assertEqual(resp.data['channels']['whatsapp'], {'usable': False, 'reason': 'disabled'})
        self.assertFalse(can_contact_automatically(self.customer, 'whatsapp'))
        self.assertEqual(CustomerContactPreferences.objects.get(customer=self.customer).updated_by_id, user.pk)

        # Re-encender: un registro viejo no alcanza, hay que confirmar otra vez.
        self.assertEqual(self._patch({'whatsapp_enabled': True}).status_code, status.HTTP_400_BAD_REQUEST)
        renewed = self._patch({'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True})
        self.assertEqual(renewed.status_code, status.HTTP_200_OK, renewed.data)
        self.assertGreater(renewed.data['whatsapp_consent_at'], enabled['whatsapp_consent_at'])
        self.assertEqual(renewed.data['whatsapp_consent_source'], 'manual')

    # 8. do_not_contact gana
    def test_do_not_contact_overrides_everything_and_keeps_flags(self):
        _login(self.client, self.biz, 'owner')
        self._patch({
            'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True,
            'email_enabled': True, 'email_consent_confirmed': True, 'preferred_channel': 'whatsapp',
        })
        resp = self._patch({'do_not_contact': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(resp.data['do_not_contact'])
        self.assertTrue(resp.data['whatsapp_enabled'])
        self.assertTrue(resp.data['email_enabled'])
        self.assertEqual(resp.data['preferred_channel'], 'whatsapp')
        self.assertIsNotNone(resp.data['whatsapp_consent_at'])
        for channel in ('whatsapp', 'email', 'phone'):
            self.assertEqual(resp.data['channels'][channel], {'usable': False, 'reason': 'do_not_contact'})
            self.assertFalse(can_contact_automatically(self.customer, channel))

        resp = self._patch({'do_not_contact': False})
        self.assertEqual(resp.data['channels']['whatsapp'], {'usable': True, 'reason': None})
        self.assertTrue(can_contact_automatically(self.customer, 'whatsapp'))
        self.assertFalse(can_contact_automatically(self.customer, 'phone'))  # nunca automático

    # 11. sin teléfono (07D.1.1: ya no se puede autorizar sin un destino real)
    def test_whatsapp_cannot_be_authorized_without_valid_phone(self):
        _login(self.client, self.biz, 'owner')
        no_phone = Customer.objects.create(business=self.biz, name='Sin tel', email='x@example.com')
        bad_phone = Customer.objects.create(business=self.biz, name='Tel raro', phone='123')
        for customer in (no_phone, bad_phone):
            resp = self._patch({'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True}, customer)
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, customer.name)
            self.assertIn('whatsapp_enabled', resp.data)
        self.assertFalse(CustomerContactPreferences.objects.exists())
        no_phone.refresh_from_db()
        self.assertEqual(no_phone.phone, '')  # no se inventan datos

    def test_whatsapp_enabled_then_phone_removed_or_invalid_is_not_usable(self):
        _login(self.client, self.biz, 'owner')
        self._patch({'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True})
        Customer.objects.filter(pk=self.customer.pk).update(phone='')
        data = self.client.get(_url(self.customer)).data
        self.assertTrue(data['whatsapp_enabled'])
        self.assertEqual(data['channels']['whatsapp'], {'usable': False, 'reason': 'missing_phone'})
        self.assertEqual(data['channels']['phone'], {'usable': False, 'reason': 'missing_phone'})
        Customer.objects.filter(pk=self.customer.pk).update(phone='123')
        data = self.client.get(_url(self.customer)).data
        self.assertEqual(data['channels']['whatsapp'], {'usable': False, 'reason': 'invalid_phone'})
        self.assertEqual(data['channels']['phone'], {'usable': True, 'reason': None})
        self.customer.refresh_from_db()
        self.assertFalse(can_contact_automatically(self.customer, 'whatsapp'))

    # 12. sin email (07D.1.1 cambia la decisión de 07D.1: ya no se permite sin email)
    def test_email_cannot_be_authorized_without_email(self):
        _login(self.client, self.biz, 'owner')
        no_email = Customer.objects.create(business=self.biz, name='Sin mail', phone='1155550102')
        resp = self._patch({'email_enabled': True, 'email_consent_confirmed': True}, no_email)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email_enabled', resp.data)
        self.assertFalse(CustomerContactPreferences.objects.filter(customer=no_email).exists())
        # Con el email cargado ya se puede autorizar.
        no_email.email = 'ok@example.com'
        no_email.save()
        resp = self._patch({'email_enabled': True, 'email_consent_confirmed': True}, no_email)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(can_contact_automatically(no_email, 'email'))

    def test_preferred_channel_must_be_enabled(self):
        _login(self.client, self.biz, 'owner')
        for channel in ('whatsapp', 'email'):
            resp = self._patch({'preferred_channel': channel})
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, channel)
            self.assertIn('preferred_channel', resp.data)
        self.assertEqual(self._patch({'preferred_channel': 'phone'}).data['preferred_channel'], 'phone')
        resp = self._patch({'phone_enabled': False})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('preferred_channel', resp.data)
        resp = self._patch({'phone_enabled': False, 'preferred_channel': None})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIsNone(resp.data['preferred_channel'])
        self.assertEqual(self._patch({'preferred_channel': 'sms'}).status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_not_allowed(self):
        _login(self.client, self.biz, 'owner')
        resp = self.client.put(_url(self.customer), {'do_not_contact': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # 2-4 (Turnos), 5 viewer
    def test_owner_admin_manager_can_edit(self):
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                customer = Customer.objects.create(business=self.biz, name=f'C {role}', phone='1155550103')
                _login(self.client, self.biz, role)
                resp = self._patch({'do_not_contact': True}, customer)
                self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
                self.assertTrue(resp.data['do_not_contact'])

    def test_viewer_read_only(self):
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self.client.get(_url(self.customer)).status_code, status.HTTP_200_OK)
        resp = self._patch({'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(CustomerContactPreferences.objects.exists())

    # 7. cross-tenant
    def test_cross_tenant_blocked(self):
        other_biz = _turnos_business(slug='prefs-otro')
        foreign = Customer.objects.create(business=other_biz, name='Ajena', phone='1155550104')
        CustomerContactPreferences.objects.create(customer=foreign, do_not_contact=True)
        _login(self.client, self.biz, 'owner')
        self.assertEqual(self.client.get(_url(foreign)).status_code, status.HTTP_404_NOT_FOUND)
        resp = self._patch({'do_not_contact': False}, foreign)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(CustomerContactPreferences.objects.get(customer=foreign).do_not_contact)

    def test_model_rejects_business_mismatch(self):
        other_biz = _turnos_business(slug='prefs-mismatch')
        with self.assertRaises(ValueError):
            CustomerContactPreferences.objects.create(customer=self.customer, business=other_biz)


class ConsentDestinationTests(APITestCase):
    """CUSTOMER 07D.1.1: el consentimiento queda ligado al destino autorizado."""

    def setUp(self):
        self.biz = _turnos_business(slug='prefs-destino')
        self.customer = Customer.objects.create(
            business=self.biz, name='Ana', phone='11 5555-0101', email='Ana@Example.com',
        )
        _login(self.client, self.biz, 'owner')

    def _patch(self, payload):
        return self.client.patch(_url(self.customer), payload, format='json')

    def _authorize_both(self):
        resp = self._patch({
            'whatsapp_enabled': True, 'whatsapp_consent_confirmed': True,
            'email_enabled': True, 'email_consent_confirmed': True,
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data

    def _prefs(self):
        return CustomerContactPreferences.objects.get(customer=self.customer)

    def _channels(self):
        return self.client.get(_url(self.customer)).data['channels']

    def _set_customer(self, **fields):
        """Cambia el Customer por el endpoint de la ficha: otro camino que no toca las preferencias."""
        resp = self.client.patch(f'{LIST_URL}{self.customer.pk}/', fields, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.customer.refresh_from_db()

    # 1-2
    def test_consent_stores_normalized_destinations(self):
        self._authorize_both()
        prefs = self._prefs()
        self.assertEqual(prefs.whatsapp_consent_value, '5491155550101')
        self.assertEqual(prefs.email_consent_value, 'ana@example.com')
        channels = self._channels()
        self.assertEqual(channels['whatsapp'], {'usable': True, 'reason': None})
        self.assertEqual(channels['email'], {'usable': True, 'reason': None})

    # 3
    def test_equivalent_formats_stay_usable(self):
        self._authorize_both()
        self._set_customer(phone='+54 9 11 5555-0101', email='ANA@example.COM')
        self.assertEqual(self._channels()['whatsapp'], {'usable': True, 'reason': None})
        self.assertEqual(self._channels()['email'], {'usable': True, 'reason': None})
        self.assertTrue(can_contact_automatically(self.customer, 'whatsapp'))
        self.assertTrue(can_contact_automatically(self.customer, 'email'))

    # 4, 5, 6, 12
    def test_changed_destination_via_customer_endpoint_is_not_usable(self):
        self._authorize_both()
        self._set_customer(phone='11 4444-0202')
        channels = self._channels()
        self.assertEqual(channels['whatsapp'], {'usable': False, 'reason': 'consent_destination_changed'})
        self.assertEqual(channels['email'], {'usable': True, 'reason': None})
        self.assertFalse(can_contact_automatically(self.customer, 'whatsapp'))
        self._set_customer(email='nueva@example.com')
        self.assertEqual(self._channels()['email'], {'usable': False, 'reason': 'consent_destination_changed'})
        self.assertFalse(can_contact_automatically(self.customer, 'email'))
        # La preferencia histórica queda intacta: encendidos y con su registro.
        prefs = self._prefs()
        self.assertTrue(prefs.whatsapp_enabled and prefs.email_enabled)
        self.assertEqual(prefs.whatsapp_consent_value, '5491155550101')
        self.assertEqual(prefs.email_consent_value, 'ana@example.com')

    def test_direct_model_update_is_also_protected(self):
        self._authorize_both()
        Customer.objects.filter(pk=self.customer.pk).update(phone='3515550000', email='otro@example.com')
        self.customer.refresh_from_db()
        self.assertFalse(can_contact_automatically(self.customer, 'whatsapp'))
        self.assertFalse(can_contact_automatically(self.customer, 'email'))

    def test_back_to_authorized_destination_is_usable_again(self):
        """Regla elegida: comparación estricta contra el destino autorizado.
        A → B → A vuelve a ser usable: A es exactamente lo que el cliente
        autorizó y ese consentimiento nunca se revocó."""
        self._authorize_both()
        self._set_customer(phone='11 4444-0202')
        self.assertFalse(can_contact_automatically(self.customer, 'whatsapp'))
        self._set_customer(phone='011 5555-0101')
        self.assertTrue(can_contact_automatically(self.customer, 'whatsapp'))

    # 7
    def test_reconfirm_whatsapp_updates_destination(self):
        first = self._authorize_both()
        self._set_customer(phone='11 4444-0202')
        resp = self._patch({'whatsapp_consent_confirmed': True, 'consent_source': 'customer_request'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['channels']['whatsapp'], {'usable': True, 'reason': None})
        self.assertGreater(resp.data['whatsapp_consent_at'], first['whatsapp_consent_at'])
        self.assertEqual(resp.data['whatsapp_consent_source'], 'customer_request')
        self.assertEqual(resp.data['email_consent_at'], first['email_consent_at'])  # email intacto
        self.assertEqual(self._prefs().whatsapp_consent_value, '5491144440202')
        # El destino anterior deja de ser el autorizado.
        self._set_customer(phone='11 5555-0101')
        self.assertEqual(self._channels()['whatsapp']['reason'], 'consent_destination_changed')

    # 8
    def test_reconfirm_email_updates_destination(self):
        first = self._authorize_both()
        self._set_customer(email='Nueva@Example.com')
        resp = self._patch({'email_enabled': True, 'email_consent_confirmed': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['channels']['email'], {'usable': True, 'reason': None})
        self.assertGreater(resp.data['email_consent_at'], first['email_consent_at'])
        self.assertEqual(self._prefs().email_consent_value, 'nueva@example.com')

    def test_reconfirm_without_destination_is_rejected(self):
        self._authorize_both()
        self._set_customer(email='')
        resp = self._patch({'email_consent_confirmed': True})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email_enabled', resp.data)
        self.assertEqual(self._prefs().email_consent_value, 'ana@example.com')
        self.assertEqual(self._channels()['email'], {'usable': False, 'reason': 'missing_email'})

    def test_confirmation_on_disabled_channel_is_ignored(self):
        self._authorize_both()
        self._patch({'whatsapp_enabled': False})
        self._set_customer(phone='11 4444-0202')
        resp = self._patch({'whatsapp_consent_confirmed': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(self._prefs().whatsapp_consent_value, '5491155550101')

    # 9, 10
    def test_do_not_contact_and_disabled_keep_priority_over_destination_change(self):
        self._authorize_both()
        self._set_customer(phone='11 4444-0202')
        self._patch({'do_not_contact': True})
        self.assertEqual(self._channels()['whatsapp'], {'usable': False, 'reason': 'do_not_contact'})
        self._patch({'do_not_contact': False, 'whatsapp_enabled': False})
        self.assertEqual(self._channels()['whatsapp'], {'usable': False, 'reason': 'disabled'})
        # Apagar conserva el destino autorizado (historial).
        prefs = self._prefs()
        self.assertEqual(prefs.whatsapp_consent_value, '5491155550101')
        self.assertIsNotNone(prefs.whatsapp_consent_at)

    # 11: filas previas a 07D.1.1 quedan con consent_value NULL tras la migración.
    def test_consent_without_value_is_not_enough(self):
        CustomerContactPreferences.objects.create(
            customer=self.customer, whatsapp_enabled=True, whatsapp_consent_at=dj_timezone.now(),
            whatsapp_consent_source='manual', email_enabled=True, email_consent_at=dj_timezone.now(),
            email_consent_source='manual',
        )
        channels = self._channels()
        self.assertEqual(channels['whatsapp'], {'usable': False, 'reason': 'consent_missing'})
        self.assertEqual(channels['email'], {'usable': False, 'reason': 'consent_missing'})
        self.assertFalse(can_contact_automatically(self.customer, 'whatsapp'))
        resp = self._patch({'whatsapp_consent_confirmed': True, 'email_consent_confirmed': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['channels']['whatsapp'], {'usable': True, 'reason': None})
        self.assertEqual(resp.data['channels']['email'], {'usable': True, 'reason': None})

    def test_phone_channel_has_no_consent_rule(self):
        self._set_customer(phone='11 4444-0202')
        self.assertEqual(self._channels()['phone'], {'usable': True, 'reason': None})
        self.assertFalse(can_contact_automatically(self.customer, 'phone'))


class GestionContactPreferencesTests(APITestCase):
    """RBAC de Gestión: cashier/staff tienen `manage_customers` (POS) pero NO
    `manage_customer_contact_preferences`."""

    def setUp(self):
        self.biz = _gestion_business('pro', 'prefs-gestion')
        self.customer = Customer.objects.create(business=self.biz, name='Carla', phone='1155550105', email='carla@example.com')

    def _assert_read_only(self, role):
        _login(self.client, self.biz, role)
        self.assertEqual(self.client.get(_url(self.customer)).status_code, status.HTTP_200_OK)
        resp = self.client.patch(_url(self.customer), {'do_not_contact': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(CustomerContactPreferences.objects.exists())

    def test_owner_admin_manager_manage(self):
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                _login(self.client, self.biz, role)
                resp = self.client.patch(_url(self.customer), {
                    'email_enabled': role == 'owner', 'email_consent_confirmed': True, 'do_not_contact': role == 'manager',
                }, format='json')
                self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    # Un test por rol: el plan tiene límite de asientos.
    def test_cashier_read_only(self):
        self._assert_read_only('cashier')

    def test_staff_read_only(self):
        self._assert_read_only('staff')

    def test_viewer_read_only(self):
        self._assert_read_only('viewer')


class ContactPreferencesPermissionMatrixTests(APITestCase):

    def test_matrix(self):
        expected = {
            'gestion': {'owner': True, 'admin': True, 'manager': True, 'cashier': False, 'staff': False,
                        'viewer': False, 'analyst': False, 'contador': False},
            'appointments': {'owner': True, 'admin': True, 'manager': True, 'viewer': False},
        }
        for service, roles in expected.items():
            for role, allowed in roles.items():
                with self.subTest(service=service, role=role):
                    perms = permissions_for_service(service, role)
                    self.assertEqual(perms[PERMISSION], allowed)
                    self.assertTrue(perms['view_customers'])

    def test_registered_capability(self):
        from apps.accounts.rbac_registry import get_registry
        cap = get_registry().get(PERMISSION)
        self.assertIsNotNone(cap)
        self.assertEqual(cap.module, 'Clientes')


class TurnosCreatedCustomerNoConsentTests(APITestCase):
    """16/17: ni la reserva pública ni el alta desde Turnos inventan consentimiento."""

    def setUp(self):
        cache.clear()
        self.biz = _turnos_business(slug='prefs-publico')
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=Decimal('1000'),
            deposit_type=AppointmentService.DepositType.NONE,
        )
        for weekday in range(7):
            AppointmentSchedule.objects.create(
                business=self.biz, professional=None, weekday=weekday, start_time='09:00', end_time='18:00',
            )

    def test_public_booking_customer_has_default_off_preferences(self):
        day = (dj_timezone.now() + dt.timedelta(days=3)).date()
        resp = self.client.post(f'/api/v1/appointments/public/{self.biz.slug}/bookings/', {
            'service': str(self.service.id),
            'start': f'{day.isoformat()}T10:00:00-03:00',
            'customer_name': 'Reserva Web',
            'customer_phone': '+54 9 11 4444-3333',
            'customer_email': 'web@example.com',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        customer = Appointment.objects.get(public_token=resp.data['public_token']).customer
        self.assertIsNotNone(customer)
        self.assertFalse(CustomerContactPreferences.objects.filter(customer=customer).exists())
        self.assertFalse(can_contact_automatically(customer, 'whatsapp'))
        self.assertFalse(can_contact_automatically(customer, 'email'))

        _login(self.client, self.biz, 'owner')
        data = self.client.get(_url(customer)).data
        self.assertFalse(data['whatsapp_enabled'])
        self.assertFalse(data['email_enabled'])
        self.assertIsNone(data['whatsapp_consent_at'])
        self.assertIsNone(data['email_consent_at'])

"""Clientes como entidad compartida desde Turnos (Turnos CUSTOMER 02).

Cubre: acceso de un Business solo-Turnos al padrón y la ficha de
`customers.Customer` (entitlement `appointments.customers` + RBAC del
servicio appointments), bloqueo para planes sin Clientes, aislamiento entre
tenants, `appointments_summary` en el detail (conteos, próximo y último
turno), Customer creado por la reserva pública visible en el listado y el
seed QA generando turnos vinculados.
"""
from __future__ import annotations

import datetime as dt
import io
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.billing.models import SubscriptionV2
from apps.business.models import Business, Subscription
from apps.customers.models import Customer

from ..models import Appointment, AppointmentProfessional, AppointmentSchedule, AppointmentService

User = get_user_model()

LIST_URL = '/api/v1/customers/'
S = Appointment.Status


def _detail_url(customer):
    return f'{LIST_URL}{customer.pk}/'


def _turnos_business(slug='turnos-core', status_=SubscriptionV2.Status.ACTIVE):
    """Business solo-Turnos con la configuración real del piloto (V2 manual)."""
    biz = Business.objects.create(
        name=f'Biz {slug}', slug=slug, default_service='appointments', status='active',
        timezone='America/Argentina/Buenos_Aires',
    )
    SubscriptionV2.objects.create(
        business=biz, service_type='appointments', plan_code='appointments_base',
        provider=SubscriptionV2.Provider.MANUAL, external_reference=f'SUB-{uuid.uuid4()}', status=status_,
    )
    return biz


def _gestion_business(plan, slug):
    biz = Business.objects.create(name=f'Gestion {slug}', slug=slug, default_service='gestion')
    Subscription.objects.create(business=biz, plan=plan, status='active')
    return biz


def _login(client, business, role='owner'):
    user = User.objects.create_user(username=f'{role}-{business.slug}-{uuid.uuid4().hex[:6]}', password='x')
    Membership.objects.create(user=user, business=business, role=role)
    client.force_authenticate(user=user)
    client.cookies['bid'] = str(business.id)
    return user


class TurnosAgendaMixin:

    def _agenda(self, biz):
        service = AppointmentService.objects.create(
            business=biz, name='Corte', duration_minutes=30, price=Decimal('1000'),
            deposit_type=AppointmentService.DepositType.NONE,
        )
        pro = AppointmentProfessional.objects.create(business=biz, name='Lu')
        pro.services.add(service)
        return service, pro

    def _appt(self, biz, service, customer, start, *, status_=S.CONFIRMED, pro=None, expires_at=None):
        return Appointment.objects.create(
            business=biz, service=service, professional=pro, customer=customer,
            customer_name=customer.name if customer else 'X', customer_phone='1155550000',
            start_at=start, end_at=start + dt.timedelta(minutes=30), status=status_, expires_at=expires_at,
            service_name=service.name, service_duration_minutes=30, service_price=service.price,
            deposit_type=service.deposit_type, deposit_value=service.deposit_value,
        )


# ── 1-4: acceso, bloqueo y aislamiento ──────────────────────────────────────

class TurnosCustomerAccessTests(TurnosAgendaMixin, APITestCase):

    def setUp(self):
        self.biz = _turnos_business()
        self.customer = Customer.objects.create(business=self.biz, name='Ana', phone='1155550001', tags=['vip'])

    def test_turnos_owner_can_list_customers(self):
        _login(self.client, self.biz, 'owner')
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        row = resp.data['results'][0]
        self.assertEqual(row['id'], str(self.customer.pk))
        for field in ('name', 'phone', 'email', 'tags', 'created_at', 'is_active'):
            self.assertIn(field, row)
        # Sin N+1 ni resumen de turnos en el listado.
        self.assertNotIn('appointments_summary', row)

    def test_turnos_roles_can_open_detail_with_summary(self):
        for role in ('owner', 'admin', 'manager', 'viewer'):
            with self.subTest(role=role):
                Membership.objects.filter(business=self.biz).delete()  # límite real de asientos
                _login(self.client, self.biz, role)
                resp = self.client.get(_detail_url(self.customer))
                self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
                self.assertIn('appointments_summary', resp.data)

    def test_turnos_manager_can_create_and_edit(self):
        _login(self.client, self.biz, 'manager')
        resp = self.client.post(LIST_URL, {'name': 'Nuevo', 'phone': '1155550002'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        resp = self.client.patch(_detail_url(self.customer), {'note': 'ok'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_turnos_viewer_is_read_only(self):
        _login(self.client, self.biz, 'viewer')
        self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.post(LIST_URL, {'name': 'X'}, format='json').status_code, status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.patch(_detail_url(self.customer), {'name': 'Y'}, format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.delete(_detail_url(self.customer)).status_code, status.HTTP_403_FORBIDDEN)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, 'Ana')
        self.assertTrue(self.customer.is_active)

    def test_session_exposes_customer_permissions_for_turnos(self):
        _login(self.client, self.biz, 'viewer')
        resp = self.client.get('/api/v1/auth/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        perms = resp.data['permissions']
        self.assertTrue(perms['view_customers'])
        self.assertFalse(perms['manage_customers'])
        # Nada comercial de Gestión llega con Turnos.
        for key in ('view_sales', 'create_sales', 'view_quotes', 'view_cash', 'view_products'):
            self.assertFalse(perms.get(key, False), key)

    def test_turnos_does_not_get_commercial_customer_sections(self):
        _login(self.client, self.biz, 'owner')
        for suffix in ('sales/', 'quotes/'):
            resp = self.client.get(f'{_detail_url(self.customer)}{suffix}')
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, suffix)

    def test_business_without_valid_entitlement_stays_blocked(self):
        starter = _gestion_business('starter', 'gestion-starter')
        _login(self.client, starter, 'owner')
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data['code'], 'plan_entitlement_required')
        self.assertEqual(resp.data['entitlement'], 'gestion.customers')

        reviews = _gestion_business('qr_reviews_base', 'reviews-only')
        _login(self.client, reviews, 'owner')
        self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_suspended_turnos_subscription_is_blocked(self):
        suspended = _turnos_business(slug='turnos-susp', status_=SubscriptionV2.Status.SUSPENDED)
        _login(self.client, suspended, 'owner')
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data['code'], 'subscription_access_denied')

    def test_gestion_pro_keeps_access_without_appointments_summary(self):
        pro = _gestion_business('pro', 'gestion-pro')
        customer = Customer.objects.create(business=pro, name='Cliente Gestión')
        _login(self.client, pro, 'owner')
        self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_200_OK)
        resp = self.client.get(_detail_url(customer))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn('appointments_summary', resp.data)

    def test_tenant_isolation(self):
        other = _turnos_business(slug='turnos-otro')
        foreign = Customer.objects.create(business=other, name='Ajeno', phone='1155550009')
        _login(self.client, self.biz, 'owner')

        ids = [row['id'] for row in self.client.get(LIST_URL).data['results']]
        self.assertNotIn(str(foreign.pk), ids)
        self.assertEqual(self.client.get(_detail_url(foreign)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.patch(_detail_url(foreign), {'name': 'X'}, format='json').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_summary_ignores_appointments_of_other_business_pointing_to_customer(self):
        """Aunque una FK cruzada existiera (dato corrupto), el resumen filtra por Business."""
        other = _turnos_business(slug='turnos-cruzado')
        other_service, _ = self._agenda(other)
        future = dj_timezone.now() + dt.timedelta(days=2)
        self._appt(other, other_service, self.customer, future)  # FK cruzada
        _login(self.client, self.biz, 'owner')
        summary = self.client.get(_detail_url(self.customer)).data['appointments_summary']
        self.assertEqual(summary['total'], 0)
        self.assertIsNone(summary['next_appointment'])
        self.assertEqual(Appointment.objects.filter(customer=self.customer).count(), 1)


# ── 5-8: appointments_summary ───────────────────────────────────────────────

class AppointmentsSummaryTests(TurnosAgendaMixin, APITestCase):

    def setUp(self):
        self.biz = _turnos_business()
        self.service, self.pro = self._agenda(self.biz)
        self.customer = Customer.objects.create(business=self.biz, name='Ana', phone='1155550001')
        self.other_customer = Customer.objects.create(business=self.biz, name='Beto', phone='1155550002')
        _login(self.client, self.biz, 'owner')
        self.now = dj_timezone.now()

    def _days(self, n, hour=0):
        return self.now + dt.timedelta(days=n, hours=hour)

    def _summary(self):
        resp = self.client.get(_detail_url(self.customer))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp.data['appointments_summary']

    def test_empty_summary(self):
        self.assertEqual(self._summary(), {
            'total': 0, 'completed': 0, 'cancelled': 0, 'no_show': 0, 'upcoming': 0,
            'next_appointment': None, 'last_appointment': None,
        })

    def test_counts_by_canonical_status(self):
        self._appt(self.biz, self.service, self.customer, self._days(-10), status_=S.COMPLETED)
        self._appt(self.biz, self.service, self.customer, self._days(-9), status_=S.COMPLETED)
        self._appt(self.biz, self.service, self.customer, self._days(-8), status_=S.CANCELLED)
        self._appt(self.biz, self.service, self.customer, self._days(-7), status_=S.NO_SHOW)
        self._appt(self.biz, self.service, self.customer, self._days(3), status_=S.CONFIRMED)
        # Vencidos (materializado y efectivo) no son turnos del cliente.
        self._appt(self.biz, self.service, self.customer, self._days(4), status_=S.EXPIRED,
                   expires_at=self._days(-1))
        self._appt(self.biz, self.service, self.customer, self._days(5), status_=S.PENDING_PAYMENT,
                   expires_at=self.now - dt.timedelta(minutes=1))
        # Otro cliente del mismo negocio no suma.
        self._appt(self.biz, self.service, self.other_customer, self._days(-5), status_=S.COMPLETED)

        summary = self._summary()
        self.assertEqual(summary['total'], 5)
        self.assertEqual(summary['completed'], 2)
        self.assertEqual(summary['cancelled'], 1)
        self.assertEqual(summary['no_show'], 1)
        self.assertEqual(summary['upcoming'], 1)

    def test_next_appointment_ignores_cancelled_and_expired(self):
        self._appt(self.biz, self.service, self.customer, self._days(1), status_=S.CANCELLED)
        self._appt(self.biz, self.service, self.customer, self._days(1, 2), status_=S.EXPIRED)
        self._appt(self.biz, self.service, self.customer, self._days(1, 4), status_=S.PENDING_PAYMENT,
                   expires_at=self.now - dt.timedelta(minutes=1))
        later = self._appt(self.biz, self.service, self.customer, self._days(6), status_=S.CONFIRMED, pro=self.pro)
        self._appt(self.biz, self.service, self.customer, self._days(-1), status_=S.CONFIRMED)  # pasado

        summary = self._summary()
        nxt = summary['next_appointment']
        self.assertEqual(nxt['id'], str(later.pk))
        self.assertEqual(nxt['status'], S.CONFIRMED)
        self.assertEqual(nxt['service_name'], 'Corte')
        self.assertEqual(nxt['professional_name'], 'Lu')
        self.assertEqual(summary['upcoming'], 1)

    def test_next_appointment_includes_pending_payment_with_live_hold(self):
        held = self._appt(self.biz, self.service, self.customer, self._days(2), status_=S.PENDING_PAYMENT,
                          expires_at=self.now + dt.timedelta(minutes=10))
        self._appt(self.biz, self.service, self.customer, self._days(5), status_=S.CONFIRMED)
        nxt = self._summary()['next_appointment']
        self.assertEqual(nxt['id'], str(held.pk))
        self.assertEqual(nxt['status'], S.PENDING_PAYMENT)

    def test_last_appointment_is_most_recent_past_relevant(self):
        self._appt(self.biz, self.service, self.customer, self._days(-20), status_=S.COMPLETED)
        last = self._appt(self.biz, self.service, self.customer, self._days(-5), status_=S.NO_SHOW)
        # Más recientes pero no relevantes: cancelado, vencido, hold sin pagar.
        self._appt(self.biz, self.service, self.customer, self._days(-3), status_=S.CANCELLED)
        self._appt(self.biz, self.service, self.customer, self._days(-2), status_=S.EXPIRED)
        self._appt(self.biz, self.service, self.customer, self._days(-1), status_=S.PENDING_PAYMENT,
                   expires_at=self._days(-1))
        # Futuro: nunca es "último".
        self._appt(self.biz, self.service, self.customer, self._days(2), status_=S.CONFIRMED)

        summary = self._summary()
        self.assertEqual(summary['last_appointment']['id'], str(last.pk))
        self.assertEqual(summary['last_appointment']['status'], S.NO_SHOW)
        self.assertIsNone(summary['last_appointment']['professional_name'])

    def test_last_appointment_counts_past_confirmed_not_yet_closed(self):
        self._appt(self.biz, self.service, self.customer, self._days(-6), status_=S.COMPLETED)
        last = self._appt(self.biz, self.service, self.customer, self._days(-1), status_=S.CONFIRMED)
        self.assertEqual(self._summary()['last_appointment']['id'], str(last.pk))

    def test_summary_query_count_is_constant(self):
        for n in range(1, 6):
            self._appt(self.biz, self.service, self.customer, self._days(-n), status_=S.COMPLETED, pro=self.pro)
            self._appt(self.biz, self.service, self.customer, self._days(n), status_=S.CONFIRMED, pro=self.pro)
        self._summary()  # calienta caches de sesión/permisos
        with CaptureQueriesContext(connection) as small:
            self._summary()
        for n in range(6, 16):
            self._appt(self.biz, self.service, self.customer, self._days(-n), status_=S.COMPLETED, pro=self.pro)
        with CaptureQueriesContext(connection) as big:
            self._summary()
        self.assertEqual(len(small), len(big))


# ── 9: reserva pública → Customer en el listado y en la ficha ────────────────

class PublicBookingCustomerVisibleTests(APITestCase):

    def setUp(self):
        cache.clear()
        self.biz = _turnos_business(slug='turnos-publico')
        self.service = AppointmentService.objects.create(
            business=self.biz, name='Corte', duration_minutes=30, price=Decimal('1000'),
            deposit_type=AppointmentService.DepositType.NONE,
        )
        for weekday in range(7):
            AppointmentSchedule.objects.create(
                business=self.biz, professional=None, weekday=weekday, start_time='09:00', end_time='18:00',
            )

    def test_public_booking_customer_appears_in_list_and_detail(self):
        day = (dj_timezone.now() + dt.timedelta(days=3)).date()
        resp = self.client.post(f'/api/v1/appointments/public/{self.biz.slug}/bookings/', {
            'service': str(self.service.id),
            'start': f'{day.isoformat()}T10:00:00-03:00',
            'customer_name': 'Reserva Web',
            'customer_phone': '+54 9 11 4444-3333',
            'customer_email': 'web@example.com',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        appt = Appointment.objects.get(public_token=resp.data['public_token'])
        self.assertIsNotNone(appt.customer_id)

        _login(self.client, self.biz, 'owner')
        rows = self.client.get(LIST_URL).data['results']
        self.assertEqual([r['id'] for r in rows], [str(appt.customer_id)])
        self.assertEqual(rows[0]['name'], 'Reserva Web')

        detail = self.client.get(f'{LIST_URL}{appt.customer_id}/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        summary = detail.data['appointments_summary']
        self.assertEqual(summary['total'], 1)
        self.assertEqual(summary['next_appointment']['id'], str(appt.pk))


# ── 10: seed QA ─────────────────────────────────────────────────────────────

@override_settings(DEBUG=True)
class SeedTurnosQaCustomerLinkTests(TestCase):

    def test_seed_links_appointments_to_customers_with_history(self):
        call_command('seed_turnos_qa', password='qa-test-pass-123', stdout=io.StringIO())
        biz = Business.objects.get(slug='qa-turnos')
        appts = Appointment.objects.filter(business=biz)
        self.assertTrue(appts.exists())
        self.assertFalse(appts.filter(customer__isnull=True).exists())
        self.assertFalse(appts.exclude(customer__business=biz).exists())
        # Una persona = un Customer (no todos colapsados en uno).
        self.assertEqual(
            Customer.objects.filter(business=biz).count(),
            appts.values('customer_name').distinct().count(),
        )

        from ..services.customer_summary import build_customer_appointments_summary
        ana = Customer.objects.get(business=biz, name='Ana Confirmada')
        summary = build_customer_appointments_summary(ana)
        self.assertGreaterEqual(summary['completed'], 1)
        self.assertGreaterEqual(summary['cancelled'], 1)
        self.assertGreaterEqual(summary['no_show'], 1)
        self.assertIsNotNone(summary['next_appointment'])
        self.assertIsNotNone(summary['last_appointment'])

        viewer_biz = Business.objects.get(slug='qa-turnos-viewer')
        self.assertFalse(Appointment.objects.filter(business=viewer_biz, customer__isnull=True).exists())

        call_command('seed_turnos_qa', reset=True, stdout=io.StringIO())
        self.assertFalse(Customer.objects.filter(business__slug__in=['qa-turnos', 'qa-turnos-viewer']).exists())


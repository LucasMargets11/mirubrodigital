"""Visibilidad por kind de BusinessNotification (CUSTOMER 07C.1).

`customer_reminder_due` → owner/admin/manager (`view_customer_reminder_notifications`).
El resto de los kinds (reservas, pagos a revisar) sigue siendo solo owner/admin:
el manager no los recibe, no cuentan en su `unread_count` y su `read/` da 404.
El filtro vive en el backend; `read_at` sigue compartido por el Business.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Membership
from apps.accounts.rbac import permissions_for_service
from apps.accounts.rbac_registry import get_registry
from apps.appointments.tests.test_customer_core_access import _gestion_business, _login, _turnos_business
from apps.notifications.business_notifications import KIND_VIEW_PERMISSIONS, create_business_notification
from apps.notifications.models import BusinessNotification

from .models import Customer

Kind = BusinessNotification.Kind
URL = '/api/v1/notifications/business/'
PERMISSION = 'view_customer_reminder_notifications'


def _read_url(notification):
    return f'{URL}{notification.pk}/read/'


class _VisibilityBase(APITestCase):
    biz = None

    def _notification(self, kind, key, *, business=None, title=None, severity=BusinessNotification.Severity.INFO, url=''):
        notification, _ = create_business_notification(
            business_id=(business or self.biz).pk, kind=kind, dedupe_key=f'{kind}:{key}',
            title=title or f'{kind} {key}', severity=severity, action_url=url,
        )
        return notification

    def _as(self, role):
        """Un solo miembro por vez (límite de asientos del plan)."""
        Membership.objects.filter(business=self.biz).delete()
        client = APIClient()
        _login(client, self.biz, role)
        return client


class TurnosReminderNotificationVisibilityTests(_VisibilityBase):

    def setUp(self):
        self.biz = _turnos_business(slug='vis-turnos')
        self.customer = Customer.objects.create(business=self.biz, name='Ana', phone='1155550101')
        self.reminder = self._notification(
            Kind.CUSTOMER_REMINDER_DUE, 'r1', title='Recordatorio: Llamar a Ana',
            url=f'/app/clientes/{self.customer.pk}',
        )
        self.payment_review = self._notification(
            Kind.APPOINTMENT_PAYMENT_REVIEW, 'p1', title='Pago sensible a revisar',
            severity=BusinessNotification.Severity.CRITICAL,
        )
        self.confirmed = self._notification(Kind.APPOINTMENT_CONFIRMED, 'a1', title='Reserva confirmada')
        self.other_biz = _turnos_business(slug='vis-turnos-otro')
        self.other_reminder = self._notification(Kind.CUSTOMER_REMINDER_DUE, 'r9', business=self.other_biz)

    def _kinds(self, response):
        return [row['kind'] for row in response.data['results']]

    # ── 1, 2, 8: owner/admin sin cambios ─────────────────────────────────────

    def test_owner_and_admin_keep_seeing_every_kind(self):
        for role in ('owner', 'admin'):
            with self.subTest(role=role):
                resp = self._as(role).get(URL)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                self.assertCountEqual(
                    self._kinds(resp),
                    [Kind.CUSTOMER_REMINDER_DUE, Kind.APPOINTMENT_PAYMENT_REVIEW, Kind.APPOINTMENT_CONFIRMED],
                )
                self.assertEqual(resp.data['unread_count'], 3)

    # ── 3, 7, 14: manager solo ve recordatorios, filtrado en el backend ──────

    def test_manager_sees_only_reminder_kind(self):
        resp = self._as('manager').get(f'{URL}?limit=50')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        [row] = resp.data['results']
        self.assertEqual(row['id'], str(self.reminder.pk))
        self.assertEqual(row['kind'], 'customer_reminder_due')
        self.assertEqual(row['action_url'], f'/app/clientes/{self.customer.pk}')
        self.assertEqual(resp.data['unread_count'], 1)
        self.assertNotIn('Pago sensible', str(resp.data))
        self.assertNotIn('Reserva confirmada', str(resp.data))

    # ── 4–6: roles sin el permiso ────────────────────────────────────────────

    def test_viewer_cannot_list_nor_mark_read(self):
        client = self._as('viewer')
        self.assertEqual(client.get(URL).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(client.post(_read_url(self.reminder)).status_code, status.HTTP_403_FORBIDDEN)
        self.reminder.refresh_from_db()
        self.assertIsNone(self.reminder.read_at)

    def test_roles_outside_appointments_matrix_are_forbidden(self):
        # cashier/staff no existen en Turnos → sin permisos → 403.
        for role in ('cashier', 'staff'):
            with self.subTest(role=role):
                self.assertEqual(self._as(role).get(URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_inactive_manager_is_forbidden(self):
        client = self._as('manager')
        Membership.objects.filter(business=self.biz).update(status=Membership.Status.INACTIVE)
        self.assertEqual(client.get(URL).status_code, status.HTTP_403_FORBIDDEN)

    # ── 9, 10: mark-as-read por kind ─────────────────────────────────────────

    def test_manager_marks_reminder_read_shared_for_the_business(self):
        client = self._as('manager')
        resp = client.post(_read_url(self.reminder))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['read_at'])
        self.assertEqual(client.get(URL).data['unread_count'], 0)
        # read_at es del Business (limitación conocida): owner lo ve leído.
        owner_view = self._as('owner').get(URL).data
        row = next(r for r in owner_view['results'] if r['id'] == str(self.reminder.pk))
        self.assertIsNotNone(row['read_at'])
        self.assertEqual(owner_view['unread_count'], 2)

    def test_manager_cannot_mark_hidden_kind_read(self):
        client = self._as('manager')
        for hidden in (self.payment_review, self.confirmed):
            with self.subTest(kind=hidden.kind):
                resp = client.post(_read_url(hidden))
                self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
                self.assertNotIn(hidden.title, str(resp.data))
                hidden.refresh_from_db()
                self.assertIsNone(hidden.read_at)

    def test_manager_mark_read_is_idempotent(self):
        client = self._as('manager')
        self.assertEqual(client.post(_read_url(self.reminder)).status_code, status.HTTP_200_OK)
        self.assertEqual(client.post(_read_url(self.reminder)).status_code, status.HTTP_200_OK)

    # ── 11: otro Business ────────────────────────────────────────────────────

    def test_other_business_reminder_is_invisible_and_404(self):
        client = self._as('manager')
        ids = [row['id'] for row in client.get(URL).data['results']]
        self.assertNotIn(str(self.other_reminder.pk), ids)
        self.assertEqual(client.post(_read_url(self.other_reminder)).status_code, status.HTTP_404_NOT_FOUND)
        self.other_reminder.refresh_from_db()
        self.assertIsNone(self.other_reminder.read_at)

    # ── 12, 13: unread filter + unread_count ─────────────────────────────────

    def test_unread_filter_and_count_only_cover_visible_kinds(self):
        BusinessNotification.objects.filter(pk=self.reminder.pk).update(read_at=self.reminder.created_at)
        self._notification(Kind.CUSTOMER_REMINDER_DUE, 'r2', title='Recordatorio 2')
        data = self._as('manager').get(f'{URL}?unread=true').data
        self.assertEqual([row['title'] for row in data['results']], ['Recordatorio 2'])
        self.assertEqual(data['unread_count'], 1)  # 2 kinds ocultos sin leer no cuentan

    def test_manager_with_only_hidden_kinds_gets_empty_list(self):
        BusinessNotification.objects.filter(kind=Kind.CUSTOMER_REMINDER_DUE).delete()
        data = self._as('manager').get(URL).data
        self.assertEqual((data['results'], data['unread_count']), ([], 0))


class GestionReminderNotificationVisibilityTests(_VisibilityBase):
    """Mismo endpoint con el RBAC de Gestión (cashier/staff/viewer/analyst/contador)."""

    def setUp(self):
        self.biz = _gestion_business('pro', 'vis-gestion')
        self.reminder = self._notification(Kind.CUSTOMER_REMINDER_DUE, 'g1')
        self.other = self._notification(Kind.APPOINTMENT_PAYMENT_REVIEW, 'g2')

    def test_manager_sees_reminder_only(self):
        data = self._as('manager').get(URL).data
        self.assertEqual([row['id'] for row in data['results']], [str(self.reminder.pk)])
        self.assertEqual(data['unread_count'], 1)

    def test_operational_roles_are_forbidden(self):
        for role in ('cashier', 'staff', 'viewer', 'analyst', 'contador'):
            with self.subTest(role=role):
                client = self._as(role)
                self.assertEqual(client.get(URL).status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(client.post(_read_url(self.reminder)).status_code, status.HTTP_403_FORBIDDEN)


class ReminderNotificationPermissionMatrixTests(APITestCase):

    def test_matrix(self):
        expected = {
            'gestion': {'owner': True, 'admin': True, 'manager': True, 'cashier': False, 'staff': False,
                        'viewer': False, 'analyst': False, 'contador': False},
            'appointments': {'owner': True, 'admin': True, 'manager': True, 'viewer': False},
            'restaurante': {'manager': False, 'cashier': False, 'salon': False, 'viewer': False},
        }
        for service, roles in expected.items():
            for role, allowed in roles.items():
                with self.subTest(service=service, role=role):
                    self.assertEqual(permissions_for_service(service, role)[PERMISSION], allowed)

    def test_only_reminder_kind_is_delegated(self):
        # AGENT 02B agregó agent_lead_handoff → view_leads y LEADS 04B.3 lead_assigned (personal);
        # los kinds de reservas/pagos siguen sin delegar.
        self.assertEqual(KIND_VIEW_PERMISSIONS, {
            Kind.CUSTOMER_REMINDER_DUE: PERMISSION,
            Kind.AGENT_LEAD_HANDOFF: 'view_leads',
            Kind.LEAD_ASSIGNED: 'view_leads',
        })

    def test_registered_capability(self):
        cap = get_registry().get(PERMISSION)
        self.assertIsNotNone(cap)
        self.assertEqual(cap.module, 'Clientes')

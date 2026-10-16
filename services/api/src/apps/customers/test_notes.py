"""Notas internas del Customer (CUSTOMER 04C).

`/api/v1/customers/{id}/notes/` (GET, POST) y `/notes/{note_id}/` (PATCH,
DELETE). Cubre contrato, orden, RBAC (lectura `view_customers`, escritura
`manage_customer_notes` — owner/admin/manager, CUSTOMER 04C.1), aislamiento
entre tenants, validación de `body` y autor tomado del request.
"""
from __future__ import annotations

import datetime as dt
import uuid

from django.contrib.auth import get_user_model
from django.utils import timezone as dj_timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.rbac import permissions_for_service
from apps.appointments.tests.test_customer_core_access import LIST_URL, _detail_url, _gestion_business, _login, _turnos_business

from .models import Customer, CustomerNote

User = get_user_model()


def _notes_url(customer):
    return f'{LIST_URL}{customer.pk}/notes/'


def _note_url(customer, note):
    note_id = note if isinstance(note, (str, uuid.UUID)) else note.pk
    return f'{LIST_URL}{customer.pk}/notes/{note_id}/'


class CustomerNotesMixin:

    def _author(self, biz, first_name='Lucía'):
        user = User.objects.create_user(username=f'author-{uuid.uuid4().hex[:8]}@example.com', password='x', first_name=first_name)
        return user

    def _note(self, customer, body='Prefiere turnos después de las 17.', *, author=None, created_at=None):
        note = CustomerNote.objects.create(business=customer.business, customer=customer, author=author, body=body)
        if created_at is not None:
            CustomerNote.objects.filter(pk=note.pk).update(created_at=created_at)
            note.refresh_from_db()
        return note


class TurnosCustomerNotesTests(CustomerNotesMixin, APITestCase):

    def setUp(self):
        self.biz = _turnos_business(slug='notes-turnos')
        self.customer = Customer.objects.create(business=self.biz, name='Ana', phone='1155550101')

    # ── Alta / listado / contrato ────────────────────────────────────────────

    def test_owner_creates_note_and_author_comes_from_request(self):
        user = _login(self.client, self.biz, 'owner')
        user.first_name, user.last_name = 'Lucía', 'Pérez'
        user.save()
        other = self._author(self.biz)
        resp = self.client.post(
            _notes_url(self.customer),
            {'body': '  Llamar antes de confirmar.  ', 'author': str(other.pk), 'author_id': other.pk},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(set(resp.data), {'id', 'body', 'author', 'created_at', 'updated_at'})
        self.assertEqual(resp.data['body'], 'Llamar antes de confirmar.')
        self.assertEqual(resp.data['author'], {'id': str(user.pk), 'name': 'Lucía Pérez'})
        note = CustomerNote.objects.get(pk=resp.data['id'])
        self.assertEqual(note.author_id, user.pk)
        self.assertEqual(note.business_id, self.biz.pk)
        self.assertEqual(note.customer_id, self.customer.pk)

    def test_author_name_never_exposes_email(self):
        _login(self.client, self.biz, 'owner')
        nameless = User.objects.create_user(username='sin.nombre@example.com', password='x', email='sin.nombre@example.com')
        self._note(self.customer, author=nameless)
        resp = self.client.get(_notes_url(self.customer))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['results'][0]['author'], {'id': str(nameless.pk), 'name': 'sin.nombre'})
        self.assertNotIn('example.com', str(resp.data))

    def test_list_most_recent_first(self):
        _login(self.client, self.biz, 'owner')
        now = dj_timezone.now()
        old = self._note(self.customer, 'Vieja', created_at=now - dt.timedelta(days=3))
        new = self._note(self.customer, 'Nueva', created_at=now - dt.timedelta(hours=1))
        mid = self._note(self.customer, 'Media', created_at=now - dt.timedelta(days=1))
        resp = self.client.get(_notes_url(self.customer))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['count'], 3)
        self.assertEqual([row['id'] for row in resp.data['results']], [str(new.pk), str(mid.pk), str(old.pk)])

    def test_list_only_this_customer(self):
        _login(self.client, self.biz, 'owner')
        other = Customer.objects.create(business=self.biz, name='Beto', phone='1155550102')
        mine = self._note(self.customer, 'Mía')
        self._note(other, 'De Beto')
        resp = self.client.get(_notes_url(self.customer))
        self.assertEqual([row['id'] for row in resp.data['results']], [str(mine.pk)])

    def test_deleted_author_keeps_note(self):
        _login(self.client, self.biz, 'owner')
        author = self._author(self.biz)
        note = self._note(self.customer, author=author)
        author.delete()
        resp = self.client.get(_notes_url(self.customer))
        self.assertEqual(resp.data['results'][0]['id'], str(note.pk))
        self.assertIsNone(resp.data['results'][0]['author'])

    # ── Validación ───────────────────────────────────────────────────────────

    def test_blank_body_rejected(self):
        _login(self.client, self.biz, 'owner')
        for payload in ({'body': ''}, {'body': '   \n  '}, {}):
            resp = self.client.post(_notes_url(self.customer), payload, format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, payload)
            self.assertIn('body', resp.data)
        self.assertFalse(CustomerNote.objects.exists())

    def test_body_max_length(self):
        _login(self.client, self.biz, 'owner')
        resp = self.client.post(_notes_url(self.customer), {'body': 'x' * (CustomerNote.BODY_MAX_LENGTH + 1)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.post(_notes_url(self.customer), {'body': 'x' * CustomerNote.BODY_MAX_LENGTH}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_patch_blank_body_rejected(self):
        _login(self.client, self.biz, 'owner')
        note = self._note(self.customer, 'Original')
        resp = self.client.patch(_note_url(self.customer, note), {'body': '  '}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        note.refresh_from_db()
        self.assertEqual(note.body, 'Original')

    # ── Edición / borrado ────────────────────────────────────────────────────

    def test_owner_edits_any_note_and_author_is_kept(self):
        _login(self.client, self.biz, 'owner')
        author = self._author(self.biz)
        note = self._note(self.customer, 'Original', author=author)
        intruder = self._author(self.biz)
        resp = self.client.patch(
            _note_url(self.customer, note), {'body': ' Editada ', 'author': str(intruder.pk)}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['body'], 'Editada')
        note.refresh_from_db()
        self.assertEqual(note.body, 'Editada')
        self.assertEqual(note.author_id, author.pk)
        self.assertGreaterEqual(note.updated_at, note.created_at)

    def test_put_not_allowed(self):
        _login(self.client, self.biz, 'owner')
        note = self._note(self.customer)
        resp = self.client.put(_note_url(self.customer, note), {'body': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_owner_deletes_note(self):
        _login(self.client, self.biz, 'owner')
        note = self._note(self.customer)
        keep = self._note(self.customer, 'Otra')
        resp = self.client.delete(_note_url(self.customer, note))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CustomerNote.objects.filter(pk=note.pk).exists())
        self.assertTrue(CustomerNote.objects.filter(pk=keep.pk).exists())
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    # ── RBAC ─────────────────────────────────────────────────────────────────

    def test_viewer_can_read(self):
        note = self._note(self.customer)
        _login(self.client, self.biz, 'viewer')
        resp = self.client.get(_notes_url(self.customer))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['results'][0]['id'], str(note.pk))

    def test_viewer_cannot_create(self):
        _login(self.client, self.biz, 'viewer')
        resp = self.client.post(_notes_url(self.customer), {'body': 'Hola'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(CustomerNote.objects.exists())

    def test_viewer_cannot_edit(self):
        note = self._note(self.customer, 'Original')
        _login(self.client, self.biz, 'viewer')
        resp = self.client.patch(_note_url(self.customer, note), {'body': 'Cambio'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        note.refresh_from_db()
        self.assertEqual(note.body, 'Original')

    def test_viewer_cannot_delete(self):
        note = self._note(self.customer)
        _login(self.client, self.biz, 'viewer')
        resp = self.client.delete(_note_url(self.customer, note))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(CustomerNote.objects.filter(pk=note.pk).exists())

    def test_manager_and_admin_can_manage(self):
        for role in ('manager', 'admin'):
            with self.subTest(role=role):
                user = _login(self.client, self.biz, role)
                created = self.client.post(_notes_url(self.customer), {'body': f'Nota {role}'}, format='json')
                self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
                self.assertEqual(created.data['author']['id'], str(user.pk))
                url = _note_url(self.customer, created.data['id'])
                edited = self.client.patch(url, {'body': f'Nota {role} editada'}, format='json')
                self.assertEqual(edited.status_code, status.HTTP_200_OK, edited.data)
                self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)

    def test_manager_can_edit_note_from_other_author(self):
        note = self._note(self.customer, 'De otro', author=self._author(self.biz))
        _login(self.client, self.biz, 'manager')
        resp = self.client.patch(_note_url(self.customer, note), {'body': 'Ajustada'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

    def test_anonymous_rejected(self):
        resp = self.client.get(_notes_url(self.customer))
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    # ── Tenant safety ────────────────────────────────────────────────────────

    def test_customer_from_other_business_404(self):
        other_biz = _turnos_business(slug='notes-turnos-b')
        foreign = Customer.objects.create(business=other_biz, name='Ajeno', phone='1155550199')
        self._note(foreign, 'Secreta')
        _login(self.client, self.biz, 'owner')
        self.assertEqual(self.client.get(_notes_url(foreign)).status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.post(_notes_url(foreign), {'body': 'Intrusa'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(CustomerNote.objects.filter(customer=foreign).count(), 1)

    def test_note_from_other_business_404(self):
        other_biz = _turnos_business(slug='notes-turnos-c')
        foreign_customer = Customer.objects.create(business=other_biz, name='Ajeno', phone='1155550198')
        foreign_note = self._note(foreign_customer, 'Secreta')
        _login(self.client, self.biz, 'owner')
        # Nota ajena colgada de MI customer y de su customer real: 404 en ambos.
        for url in (_note_url(self.customer, foreign_note), _note_url(foreign_customer, foreign_note)):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(self.client.patch(url, {'body': 'x'}, format='json').status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        foreign_note.refresh_from_db()
        self.assertEqual(foreign_note.body, 'Secreta')

    def test_note_of_other_customer_same_business_404(self):
        _login(self.client, self.biz, 'owner')
        other = Customer.objects.create(business=self.biz, name='Beto', phone='1155550102')
        note = self._note(other, 'De Beto')
        resp = self.client.delete(_note_url(self.customer, note))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(CustomerNote.objects.filter(pk=note.pk).exists())

    def test_model_rejects_business_mismatch(self):
        other_biz = _turnos_business(slug='notes-turnos-d')
        with self.assertRaises(ValueError):
            CustomerNote.objects.create(business=other_biz, customer=self.customer, body='Cruzada')
        self.assertFalse(CustomerNote.objects.exists())

    def test_model_defaults_business_from_customer(self):
        note = CustomerNote.objects.create(customer=self.customer, body='Sin business explícito')
        self.assertEqual(note.business_id, self.biz.pk)


class GestionCustomerNotesTests(CustomerNotesMixin, APITestCase):
    """Mismo endpoint con el RBAC de Gestión (servicio activo distinto).

    CUSTOMER 04C.1: cashier/staff tienen `manage_customers` (POS/ventas) pero
    NO `manage_customer_notes`: leen notas, no las mutan.
    """

    def setUp(self):
        self.biz = _gestion_business('pro', 'notes-gestion')
        self.customer = Customer.objects.create(business=self.biz, name='Carla')

    def _assert_full_access(self, role):
        user = _login(self.client, self.biz, role)
        created = self.client.post(_notes_url(self.customer), {'body': f'Nota {role}'}, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data['author']['id'], str(user.pk))
        url = _note_url(self.customer, created.data['id'])
        self.assertEqual(self.client.get(_notes_url(self.customer)).status_code, status.HTTP_200_OK)
        edited = self.client.patch(url, {'body': f'Nota {role} editada'}, format='json')
        self.assertEqual(edited.status_code, status.HTTP_200_OK, edited.data)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)

    def _assert_read_only(self, role):
        note = self._note(self.customer, 'Cliente frecuente', author=self._author(self.biz))
        _login(self.client, self.biz, role)
        listed = self.client.get(_notes_url(self.customer))
        self.assertEqual(listed.status_code, status.HTTP_200_OK, listed.data)
        self.assertEqual([row['id'] for row in listed.data['results']], [str(note.pk)])
        url = _note_url(self.customer, note)
        self.assertEqual(self.client.post(_notes_url(self.customer), {'body': 'x'}, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.patch(url, {'body': 'x'}, format='json').status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_403_FORBIDDEN)
        note.refresh_from_db()
        self.assertEqual(note.body, 'Cliente frecuente')
        self.assertEqual(CustomerNote.objects.filter(customer=self.customer).count(), 1)

    def test_owner_admin_manager_manage_notes(self):
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                self._assert_full_access(role)

    def test_viewer_read_only(self):
        self._assert_read_only('viewer')

    def test_cashier_read_only(self):
        self._assert_read_only('cashier')

    def test_staff_read_only(self):
        self._assert_read_only('staff')

    def test_other_read_roles_read_only(self):
        for role in ('analyst', 'contador'):
            with self.subTest(role=role):
                CustomerNote.objects.all().delete()
                self._assert_read_only(role)

    def test_cashier_and_staff_keep_customer_crud(self):
        """Este slice no toca `manage_customers`: cashier/staff siguen creando/editando Customers."""
        for role in ('cashier', 'staff'):
            with self.subTest(role=role):
                perms = permissions_for_service('gestion', role)
                self.assertTrue(perms['view_customers'])
                self.assertTrue(perms['manage_customers'])
                self.assertFalse(perms['manage_customer_notes'])
                _login(self.client, self.biz, role)
                created = self.client.post(LIST_URL, {'name': f'Nuevo {role}'}, format='json')
                self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
                patched = self.client.patch(_detail_url(self.customer), {'phone': '1155550000'}, format='json')
                self.assertEqual(patched.status_code, status.HTTP_200_OK, patched.data)

    def test_cross_tenant_still_404_for_manager(self):
        other_biz = _gestion_business('pro', 'notes-gestion-b')
        foreign = Customer.objects.create(business=other_biz, name='Ajeno')
        foreign_note = self._note(foreign, 'Secreta')
        _login(self.client, self.biz, 'manager')
        self.assertEqual(self.client.get(_notes_url(foreign)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post(_notes_url(foreign), {'body': 'x'}, format='json').status_code, status.HTTP_404_NOT_FOUND)
        for url in (_note_url(foreign, foreign_note), _note_url(self.customer, foreign_note)):
            self.assertEqual(self.client.patch(url, {'body': 'x'}, format='json').status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)


class CustomerNotesPermissionMatrixTests(APITestCase):
    """`manage_customer_notes` solo para owner/admin/manager donde hay Clientes."""

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
                    self.assertEqual(perms['manage_customer_notes'], allowed)
                    # Lectura de notas = view_customers, sin cambios.
                    self.assertTrue(perms['view_customers'])

    def test_registered_capability(self):
        from apps.accounts.rbac_registry import get_registry
        cap = get_registry().get('manage_customer_notes')
        self.assertIsNotNone(cap)
        self.assertEqual(cap.module, 'Clientes')

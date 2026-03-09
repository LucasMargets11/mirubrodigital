"""
cash/tests/test_pos_cash.py — Backend tests for POS cash operative endpoints.

Test blocks:
  A. Open cash session (POST /api/v1/pos/cash/open/)
     A1. Valid cashier can open a session.
     A2. Valid manager_op can open a session.
     A3. Suspended employee cannot open.
     A4. must_change_pin=True blocks access.
     A5. Role without can_open_cash (server, kitchen) is rejected.
     A6. Employee cannot open a second session if one is already open.
     A7. Invalid token is rejected.

  B. Get current session (GET /api/v1/pos/cash/current/)
     B1. Returns open session when one exists for this employee.
     B2. Returns null when no open session exists.
     B3. Expired token is rejected.
     B4. Returns only this employee's session (not others).

  C. Close current session (POST /api/v1/pos/cash/current/close/)
     C1. Close succeeds with no body.
     C2. Close succeeds with closing_cash_counted and closing_note.
     C3. Error if no open session exists.
     C4. Role without can_close_cash is rejected.
     C5. Audit log is created on close.

  D. Cash movement (POST /api/v1/pos/cash/current/movements/)
     D1. Valid in-movement succeeds.
     D2. Valid out-movement succeeds.
     D3. Amount <= 0 is rejected.
     D4. Role without can_register_cash_movement is rejected.
     D5. No open session returns 400.
     D6. Audit log is created.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.backends import TokenBackend
from django.conf import settings

from apps.accounts.models import AccessAuditLog, EmployeeProfile
from apps.business.models import Business
from apps.cash.models import CashSession

User = get_user_model()

# ── URL shortcuts ─────────────────────────────────────────────────────────────

URL_OPEN      = '/api/v1/pos/cash/open/'
URL_CURRENT   = '/api/v1/pos/cash/current/'
URL_CLOSE     = '/api/v1/pos/cash/current/close/'
URL_MOVEMENTS = '/api/v1/pos/cash/current/movements/'


# ── Test fixtures ─────────────────────────────────────────────────────────────


def _make_business(name: str = 'CashPOSBiz') -> Business:
    return Business.objects.create(name=name, default_service='gestion', status='active')


def _make_employee(
    business: Business,
    code: str = 'EMP-0001',
    role_type: str = EmployeeProfile.RoleType.CASHIER,
    pin: str = '123456',
    emp_status: str = EmployeeProfile.Status.ACTIVE,
    must_change_pin: bool = False,
) -> EmployeeProfile:
    return EmployeeProfile.objects.create(
        business=business,
        first_name='Test',
        last_name='Emp',
        alias='Tester',
        employee_code=code,
        role_type=role_type,
        credential_type=EmployeeProfile.CredentialType.PIN,
        login_code_hash=make_password(pin),
        must_change_pin=must_change_pin,
        status=emp_status,
    )


def _make_employee_token(employee: EmployeeProfile, business: Business) -> str:
    now = timezone.now()
    payload = {
        'actor_type':  'employee',
        'employee_id': str(employee.pk),
        'business_id': business.pk,
        'role_type':   employee.role_type,
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(hours=12)).timestamp()),
    }
    backend = TokenBackend(
        algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
        signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
    )
    return backend.encode(payload)


def _make_expired_token(employee: EmployeeProfile, business: Business) -> str:
    now = timezone.now()
    payload = {
        'actor_type':  'employee',
        'employee_id': str(employee.pk),
        'business_id': business.pk,
        'role_type':   employee.role_type,
        'iat': int((now - timedelta(hours=14)).timestamp()),
        'exp': int((now - timedelta(hours=2)).timestamp()),
    }
    backend = TokenBackend(
        algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
        signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
    )
    return backend.encode(payload)


def _employee_client(employee: EmployeeProfile, business: Business) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_X_EMPLOYEE_TOKEN=_make_employee_token(employee, business))
    return client


# ── Block A: Open cash session ────────────────────────────────────────────────


class PosCashOpenTest(TestCase):

    def setUp(self):
        self.biz = _make_business('OpenBiz')
        self.cashier = _make_employee(self.biz, 'EMP-C01', EmployeeProfile.RoleType.CASHIER)
        self.manager = _make_employee(self.biz, 'EMP-M01', EmployeeProfile.RoleType.MANAGER_OP)
        self.server  = _make_employee(self.biz, 'EMP-S01', EmployeeProfile.RoleType.SERVER)

    # A1 ─────────────────────────────────────────────────────────────────────

    def test_cashier_can_open_session(self):
        client = _employee_client(self.cashier, self.biz)
        resp = client.post(URL_OPEN, {'opening_cash_amount': '200.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIn('session', resp.data)
        session_data = resp.data['session']
        self.assertEqual(session_data['status'], 'open')
        self.assertEqual(Decimal(session_data['opening_cash_amount']), Decimal('200.00'))

    # A2 ─────────────────────────────────────────────────────────────────────

    def test_manager_op_can_open_session(self):
        client = _employee_client(self.manager, self.biz)
        resp = client.post(URL_OPEN, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        # Verify DB row
        self.assertTrue(
            CashSession.objects.filter(
                business=self.biz,
                opened_by_employee=self.manager,
                status=CashSession.Status.OPEN,
            ).exists()
        )

    # A3 ─────────────────────────────────────────────────────────────────────

    def test_suspended_employee_cannot_open(self):
        suspended = _make_employee(
            self.biz, 'EMP-SUS', EmployeeProfile.RoleType.CASHIER,
            emp_status=EmployeeProfile.Status.SUSPENDED,
        )
        # Bypassing login: force the token but the authenticator checks status=ACTIVE
        client = _employee_client(suspended, self.biz)
        resp = client.post(URL_OPEN, {}, format='json')
        # EmployeeTokenAuthentication rejects SUSPENDED employees
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # A4 ─────────────────────────────────────────────────────────────────────

    def test_must_change_pin_blocks_open(self):
        employee = _make_employee(
            self.biz, 'EMP-PIN', EmployeeProfile.RoleType.CASHIER,
            must_change_pin=True,
        )
        client = _employee_client(employee, self.biz)
        resp = client.post(URL_OPEN, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data.get('code'), 'pin_change_required')

    # A5 ─────────────────────────────────────────────────────────────────────

    def test_server_role_cannot_open_cash(self):
        """Server role does not have can_open_cash capability."""
        client = _employee_client(self.server, self.biz)
        resp = client.post(URL_OPEN, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data.get('code'), 'capability_required')

    # A6 ─────────────────────────────────────────────────────────────────────

    def test_cannot_open_second_session_while_one_is_open(self):
        client = _employee_client(self.cashier, self.biz)
        resp1 = client.post(URL_OPEN, {}, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        # Try to open another one
        resp2 = client.post(URL_OPEN, {}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

    # A7 ─────────────────────────────────────────────────────────────────────

    def test_invalid_token_rejected_on_open(self):
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN='not.a.valid.token')
        resp = client.post(URL_OPEN, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ── Block B: Current session ──────────────────────────────────────────────────


class PosCashCurrentTest(TestCase):

    def setUp(self):
        self.biz = _make_business('CurrentBiz')
        self.cashier = _make_employee(self.biz, 'EMP-C02', EmployeeProfile.RoleType.CASHIER)
        self.other   = _make_employee(self.biz, 'EMP-C03', EmployeeProfile.RoleType.CASHIER)
        self.client  = _employee_client(self.cashier, self.biz)

    # B1 ─────────────────────────────────────────────────────────────────────

    def test_returns_open_session_when_exists(self):
        # Open first
        self.client.post(URL_OPEN, {'opening_cash_amount': '300.00'}, format='json')
        resp = self.client.get(URL_CURRENT)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['session'])
        self.assertEqual(resp.data['session']['status'], 'open')
        self.assertEqual(Decimal(resp.data['session']['opening_cash_amount']), Decimal('300.00'))

    # B2 ─────────────────────────────────────────────────────────────────────

    def test_returns_null_when_no_session(self):
        resp = self.client.get(URL_CURRENT)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data['session'])

    # B3 ─────────────────────────────────────────────────────────────────────

    def test_expired_token_is_rejected(self):
        client = APIClient()
        client.credentials(
            HTTP_X_EMPLOYEE_TOKEN=_make_expired_token(self.cashier, self.biz)
        )
        resp = client.get(URL_CURRENT)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # B4 ─────────────────────────────────────────────────────────────────────

    def test_returns_only_own_session(self):
        """current/ should not return another employee's session."""
        # Open session for 'other' employee
        other_client = _employee_client(self.other, self.biz)
        other_client.post(URL_OPEN, {}, format='json')

        # cashier has no session — should get null
        resp = self.client.get(URL_CURRENT)
        self.assertIsNone(resp.data['session'])


# ── Block C: Close session ────────────────────────────────────────────────────


class PosCashCloseTest(TestCase):

    def setUp(self):
        self.biz     = _make_business('CloseBiz')
        self.cashier = _make_employee(self.biz, 'EMP-CL1', EmployeeProfile.RoleType.CASHIER)
        self.server  = _make_employee(self.biz, 'EMP-SV2', EmployeeProfile.RoleType.SERVER)
        self.client  = _employee_client(self.cashier, self.biz)
        # Open a session
        self.client.post(URL_OPEN, {'opening_cash_amount': '100.00'}, format='json')

    # C1 ─────────────────────────────────────────────────────────────────────

    def test_close_with_no_body_succeeds(self):
        resp = self.client.post(URL_CLOSE, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['session']['status'], 'closed')

    # C2 ─────────────────────────────────────────────────────────────────────

    def test_close_with_counted_cash_and_note(self):
        resp = self.client.post(
            URL_CLOSE,
            {'closing_cash_counted': '95.00', 'closing_note': 'Fin de turno'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        session_data = resp.data['session']
        self.assertEqual(session_data['status'], 'closed')
        self.assertEqual(Decimal(session_data['closing_cash_counted']), Decimal('95.00'))
        # Difference: 95 - expected (100 opening + 0 payments) = -5
        self.assertEqual(Decimal(session_data['difference_amount']), Decimal('-5.00'))

    # C3 ─────────────────────────────────────────────────────────────────────

    def test_close_with_no_open_session_returns_400(self):
        # Close existing session first
        self.client.post(URL_CLOSE, {}, format='json')
        # Try to close again
        resp = self.client.post(URL_CLOSE, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data.get('code'), 'no_open_session')

    # C4 ─────────────────────────────────────────────────────────────────────

    def test_server_role_cannot_close_cash(self):
        """Server role does not have can_close_cash capability."""
        # Open a session for the server first — actually server can't open either.
        # Create the session directly via ORM to test close capability in isolation.
        session = CashSession.objects.create(
            business=self.biz,
            opened_by=None,
            opened_by_employee=self.server,
            opened_by_name='Tester',
            opening_cash_amount=Decimal('0'),
        )
        server_client = _employee_client(self.server, self.biz)
        resp = server_client.post(URL_CLOSE, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data.get('code'), 'capability_required')

    # C5 ─────────────────────────────────────────────────────────────────────

    def test_audit_log_created_on_close(self):
        before_count = AccessAuditLog.objects.filter(
            action='CASH_SESSION_CLOSED',
            business=self.biz,
        ).count()
        self.client.post(URL_CLOSE, {}, format='json')
        after_count = AccessAuditLog.objects.filter(
            action='CASH_SESSION_CLOSED',
            business=self.biz,
        ).count()
        self.assertEqual(after_count, before_count + 1)
        log = AccessAuditLog.objects.filter(
            action='CASH_SESSION_CLOSED', business=self.biz
        ).latest('created_at')
        self.assertEqual(log.actor_type, AccessAuditLog.ActorType.EMPLOYEE)
        self.assertEqual(log.actor_employee, self.cashier)
        self.assertIsNone(log.actor)
        self.assertEqual(log.entity_type, 'cash_session')


# ── Block D: Cash movement ────────────────────────────────────────────────────


class PosCashMovementTest(TestCase):

    def setUp(self):
        self.biz     = _make_business('MovBiz')
        self.cashier = _make_employee(self.biz, 'EMP-MV1', EmployeeProfile.RoleType.CASHIER)
        self.server  = _make_employee(self.biz, 'EMP-MV2', EmployeeProfile.RoleType.SERVER)
        self.client  = _employee_client(self.cashier, self.biz)
        # Open a session
        self.client.post(URL_OPEN, {'opening_cash_amount': '500.00'}, format='json')

    # D1 ─────────────────────────────────────────────────────────────────────

    def test_in_movement_succeeds(self):
        resp = self.client.post(
            URL_MOVEMENTS,
            {
                'movement_type': 'in',
                'category': 'deposit',
                'method': 'cash',
                'amount': '50.00',
                'note': 'Depósito inicial extra',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIn('movement', resp.data)
        self.assertEqual(resp.data['movement']['movement_type'], 'in')
        self.assertEqual(Decimal(resp.data['movement']['amount']), Decimal('50.00'))

    # D2 ─────────────────────────────────────────────────────────────────────

    def test_out_movement_succeeds(self):
        resp = self.client.post(
            URL_MOVEMENTS,
            {'movement_type': 'out', 'category': 'expense', 'amount': '25.00'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['movement']['movement_type'], 'out')

    # D3 ─────────────────────────────────────────────────────────────────────

    def test_zero_amount_rejected(self):
        resp = self.client.post(
            URL_MOVEMENTS,
            {'movement_type': 'in', 'amount': '0.00'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # D4 ─────────────────────────────────────────────────────────────────────

    def test_server_role_cannot_register_movement(self):
        server_client = _employee_client(self.server, self.biz)
        resp = server_client.post(
            URL_MOVEMENTS,
            {'movement_type': 'in', 'amount': '10.00'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data.get('code'), 'capability_required')

    # D5 ─────────────────────────────────────────────────────────────────────

    def test_no_open_session_returns_400(self):
        new_cashier = _make_employee(self.biz, 'EMP-MV3', EmployeeProfile.RoleType.CASHIER)
        client = _employee_client(new_cashier, self.biz)
        resp = client.post(
            URL_MOVEMENTS,
            {'movement_type': 'in', 'amount': '10.00'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data.get('code'), 'no_open_session')

    # D6 ─────────────────────────────────────────────────────────────────────

    def test_audit_log_created_for_movement(self):
        before_count = AccessAuditLog.objects.filter(
            action='CASH_MOVEMENT_CREATED',
            business=self.biz,
        ).count()
        self.client.post(
            URL_MOVEMENTS,
            {'movement_type': 'in', 'amount': '10.00'},
            format='json',
        )
        after_count = AccessAuditLog.objects.filter(
            action='CASH_MOVEMENT_CREATED',
            business=self.biz,
        ).count()
        self.assertEqual(after_count, before_count + 1)
        log = AccessAuditLog.objects.filter(
            action='CASH_MOVEMENT_CREATED', business=self.biz
        ).latest('created_at')
        self.assertEqual(log.actor_type, AccessAuditLog.ActorType.EMPLOYEE)
        self.assertEqual(log.actor_employee, self.cashier)
        self.assertEqual(log.entity_type, 'cash_movement')


# ── Block E: Open audit log created ──────────────────────────────────────────


class PosCashOpenAuditTest(TestCase):

    def setUp(self):
        self.biz     = _make_business('AuditOpenBiz')
        self.cashier = _make_employee(self.biz, 'EMP-AO1', EmployeeProfile.RoleType.CASHIER)
        self.client  = _employee_client(self.cashier, self.biz)

    def test_audit_log_created_on_open(self):
        before_count = AccessAuditLog.objects.filter(
            action='CASH_SESSION_OPENED', business=self.biz
        ).count()
        self.client.post(URL_OPEN, {}, format='json')
        after_count = AccessAuditLog.objects.filter(
            action='CASH_SESSION_OPENED', business=self.biz
        ).count()
        self.assertEqual(after_count, before_count + 1)
        log = AccessAuditLog.objects.filter(
            action='CASH_SESSION_OPENED', business=self.biz
        ).latest('created_at')
        self.assertEqual(log.actor_type, AccessAuditLog.ActorType.EMPLOYEE)
        self.assertEqual(log.actor_employee, self.cashier)
        self.assertIsNone(log.actor)
        self.assertIsNone(log.target_user)
        self.assertEqual(log.entity_type, 'cash_session')

"""
accounts/tests/test_pos_routes.py — Backend tests for POS endpoints and PIN change.

Test blocks:
  A. POS /me/ — authenticated access, pin-change exempt
  B. POS /capabilities/ — enforces must_change_pin, returns perms + capabilities
  C. POS /health/ — lightweight probe, pin-change exempt
  D. POST /auth/employee-change-pin/ — full PIN change flow
  E. must_change_pin enforcement — whitelist vs blocked routes
  F. Token edge cases on POS routes (invalid, suspended, wrong business)
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.backends import TokenBackend
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import AccessAuditLog, EmployeeProfile, Membership
from apps.business.models import Business

User = get_user_model()


# ── Shared fixtures ───────────────────────────────────────────────────────────


def _make_business(name: str = 'POSTestBiz', service: str = 'gestion') -> Business:
    return Business.objects.create(name=name, default_service=service, status='active')


def _make_employee(
    business: Business,
    code: str = 'EMP-0001',
    role_type: str = EmployeeProfile.RoleType.CASHIER,
    pin: str = '123456',
    status: str = EmployeeProfile.Status.ACTIVE,
    must_change_pin: bool = False,
) -> EmployeeProfile:
    return EmployeeProfile.objects.create(
        business=business,
        first_name='Test',
        last_name='Employee',
        alias='Tester',
        employee_code=code,
        role_type=role_type,
        credential_type=EmployeeProfile.CredentialType.PIN,
        login_code_hash=make_password(pin),
        must_change_pin=must_change_pin,
        status=status,
    )


def _make_employee_token(employee: EmployeeProfile, business: Business) -> str:
    """Generate a valid employee JWT (same logic as EmployeeLoginView)."""
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
    """Generate an already-expired employee JWT."""
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
    """APIClient pre-configured with a valid X-Employee-Token."""
    client = APIClient()
    client.credentials(HTTP_X_EMPLOYEE_TOKEN=_make_employee_token(employee, business))
    return client


# ═══════════════════════════════════════════════════════════════════════════════
# A. GET /api/v1/pos/me/
# ═══════════════════════════════════════════════════════════════════════════════


class PosMeViewTest(TestCase):
    """Tests for GET /api/v1/pos/me/."""

    def setUp(self):
        self.biz = _make_business('PosMeBiz')
        self.employee = _make_employee(self.biz, code='EMP-ME01', must_change_pin=False)
        self.client = _employee_client(self.employee, self.biz)

    def test_me_returns_identity_fields(self):
        """Valid token → 200 with identity payload."""
        resp = self.client.get('/api/v1/pos/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        data = resp.data
        self.assertEqual(data['id'], str(self.employee.pk))
        self.assertEqual(data['employee_code'], 'EMP-ME01')
        self.assertEqual(data['role_type'], 'cashier')
        self.assertIn('display_name', data)
        self.assertIn('full_name', data)
        self.assertIn('must_change_pin', data)
        self.assertIn('business_id', data)
        self.assertIn('business_name', data)
        # Sensitive fields must NOT be present
        self.assertNotIn('login_code_hash', data)

    def test_me_allowed_when_must_change_pin_true(self):
        """/pos/me/ is accessible even when must_change_pin=True."""
        emp = _make_employee(self.biz, code='EMP-ME02', must_change_pin=True)
        client = _employee_client(emp, self.biz)
        resp = client.get('/api/v1/pos/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['must_change_pin'])

    def test_me_rejected_without_token(self):
        """Missing X-Employee-Token → 401 or 403."""
        resp = APIClient().get('/api/v1/pos/me/')
        self.assertIn(resp.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ])

    def test_me_rejected_with_invalid_token(self):
        """Garbage token → 401."""
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN='not.a.real.token')
        resp = client.get('/api/v1/pos/me/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_rejected_with_expired_token(self):
        """Expired token → 401."""
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN=_make_expired_token(self.employee, self.biz))
        resp = client.get('/api/v1/pos/me/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_rejected_for_suspended_employee(self):
        """Token issued before suspension is rejected after employee is suspended."""
        token = _make_employee_token(self.employee, self.biz)
        self.employee.status = EmployeeProfile.Status.SUSPENDED
        self.employee.save(update_fields=['status'])
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN=token)
        resp = client.get('/api/v1/pos/me/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_rejected_with_admin_bearer_token(self):
        """Admin JWT in Authorization header is rejected by /pos/me/ (no employee identity)."""
        user = User.objects.create_user(
            username='admin_me@test.com', email='admin_me@test.com', password='pass1234!'
        )
        from rest_framework_simplejwt.tokens import AccessToken
        admin_jwt = str(AccessToken.for_user(user))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {admin_jwt}')
        resp = client.get('/api/v1/pos/me/')
        self.assertIn(resp.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ])


# ═══════════════════════════════════════════════════════════════════════════════
# B. GET /api/v1/pos/capabilities/
# ═══════════════════════════════════════════════════════════════════════════════


class PosCapabilitiesViewTest(TestCase):
    """Tests for GET /api/v1/pos/capabilities/."""

    def setUp(self):
        self.biz = _make_business('PosCapsBiz')
        self.employee = _make_employee(
            self.biz, code='EMP-CAP01',
            role_type=EmployeeProfile.RoleType.CASHIER,
            must_change_pin=False,
        )
        self.client = _employee_client(self.employee, self.biz)

    def test_capabilities_returns_expected_shape(self):
        """Valid token → 200 with role_type, service, permissions, capabilities."""
        resp = self.client.get('/api/v1/pos/capabilities/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        data = resp.data
        self.assertIn('role_type', data)
        self.assertIn('service', data)
        self.assertIn('permissions', data)
        self.assertIn('capabilities', data)
        self.assertEqual(data['role_type'], 'cashier')

    def test_cashier_has_expected_capabilities(self):
        """Cashier role has can_open_pos, can_create_sale, can_manage_cash."""
        resp = self.client.get('/api/v1/pos/capabilities/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        caps = resp.data['capabilities']
        self.assertTrue(caps.get('can_open_pos'))
        self.assertTrue(caps.get('can_create_sale'))
        self.assertTrue(caps.get('can_manage_cash'))
        # Cashier does NOT have refund or reports
        self.assertFalse(caps.get('can_refund_sale'))
        self.assertFalse(caps.get('can_view_reports'))

    def test_manager_op_has_all_core_capabilities(self):
        """manager_op has the full POS capability set."""
        mgr = _make_employee(
            self.biz, code='EMP-CAP02',
            role_type=EmployeeProfile.RoleType.MANAGER_OP,
            must_change_pin=False,
        )
        client = _employee_client(mgr, self.biz)
        resp = client.get('/api/v1/pos/capabilities/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        caps = resp.data['capabilities']
        for cap in ('can_open_pos', 'can_create_sale', 'can_refund_sale',
                    'can_manage_cash', 'can_view_reports', 'can_manage_employees_pos'):
            self.assertTrue(caps.get(cap), f'Expected {cap}=True for manager_op')

    def test_capabilities_blocked_when_must_change_pin(self):
        """/pos/capabilities/ requires must_change_pin=False."""
        emp = _make_employee(self.biz, code='EMP-CAP03', must_change_pin=True)
        client = _employee_client(emp, self.biz)
        resp = client.get('/api/v1/pos/capabilities/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        # Semantic error code must be present
        self.assertEqual(resp.data.get('code'), 'pin_change_required')

    def test_capabilities_rejected_without_token(self):
        resp = APIClient().get('/api/v1/pos/capabilities/')
        self.assertIn(resp.status_code, [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
        ])

    def test_capability_overrides_applied(self):
        """per-employee permission_overrides on capability keys are respected."""
        self.employee.permission_overrides = {'can_refund_sale': True}
        self.employee.save(update_fields=['permission_overrides'])
        # Re-authenticate to pick up override
        client = _employee_client(self.employee, self.biz)
        resp = client.get('/api/v1/pos/capabilities/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Override should grant refund even though cashier normally can't
        self.assertTrue(resp.data['capabilities'].get('can_refund_sale'))


# ═══════════════════════════════════════════════════════════════════════════════
# C. GET /api/v1/pos/health/
# ═══════════════════════════════════════════════════════════════════════════════


class PosHealthViewTest(TestCase):
    """Tests for GET /api/v1/pos/health/."""

    def setUp(self):
        self.biz = _make_business('PosHealthBiz')
        self.employee = _make_employee(self.biz, code='EMP-HLT01')
        self.client = _employee_client(self.employee, self.biz)

    def test_health_returns_ok(self):
        """Valid token → 200 with status=ok."""
        resp = self.client.get('/api/v1/pos/health/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'ok')
        self.assertIn('employee_code', resp.data)
        self.assertIn('business_id', resp.data)
        self.assertIn('must_change_pin', resp.data)

    def test_health_allowed_when_must_change_pin_true(self):
        """/pos/health/ is accessible even when must_change_pin=True."""
        emp = _make_employee(self.biz, code='EMP-HLT02', must_change_pin=True)
        resp = _employee_client(emp, self.biz).get('/api/v1/pos/health/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['must_change_pin'])

    def test_health_rejected_without_token(self):
        resp = APIClient().get('/api/v1/pos/health/')
        self.assertIn(resp.status_code, [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
        ])

    def test_health_rejected_with_malformed_token(self):
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN='bad.token.value')
        resp = client.get('/api/v1/pos/health/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ═══════════════════════════════════════════════════════════════════════════════
# D. POST /api/v1/auth/employee-change-pin/
# ═══════════════════════════════════════════════════════════════════════════════


class EmployeeChangePinTest(TestCase):
    """Tests for POST /api/v1/auth/employee-change-pin/."""

    URL = '/api/v1/auth/employee-change-pin/'

    def setUp(self):
        self.biz = _make_business('PinChangeBiz')
        self.pin = '123456'
        self.employee = _make_employee(
            self.biz, code='EMP-PIN01', pin=self.pin, must_change_pin=True,
        )
        self.client = _employee_client(self.employee, self.biz)

    # ── Success ────────────────────────────────────────────────────────────────

    def test_change_pin_success(self):
        """Correct current PIN + valid new PIN → 200, must_change_pin cleared."""
        resp = self.client.post(self.URL, {
            'current_pin':     self.pin,
            'new_pin':         '654321',
            'confirm_new_pin': '654321',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(resp.data['success'])
        self.assertFalse(resp.data['must_change_pin'])

    def test_must_change_pin_cleared_in_db(self):
        """After successful change, must_change_pin=False in DB."""
        self.client.post(self.URL, {
            'current_pin': self.pin, 'new_pin': '654321', 'confirm_new_pin': '654321',
        }, format='json')
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.must_change_pin)

    def test_new_hash_stored(self):
        """After successful change, new PIN hash is stored (old PIN fails)."""
        self.client.post(self.URL, {
            'current_pin': self.pin, 'new_pin': '654321', 'confirm_new_pin': '654321',
        }, format='json')
        self.employee.refresh_from_db()
        self.assertFalse(check_password(self.pin, self.employee.login_code_hash))
        self.assertTrue(check_password('654321', self.employee.login_code_hash))

    def test_old_pin_no_longer_authenticates(self):
        """After change, old PIN cannot be used to login at /employee-login/."""
        self.client.post(self.URL, {
            'current_pin': self.pin, 'new_pin': '654321', 'confirm_new_pin': '654321',
        }, format='json')
        resp = APIClient().post('/api/v1/auth/employee-login/', {
            'business_id': self.biz.pk,
            'employee_code': 'EMP-PIN01',
            'pin': self.pin,  # old PIN
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_new_pin_authenticates(self):
        """After change, new PIN authenticates successfully at /employee-login/."""
        self.client.post(self.URL, {
            'current_pin': self.pin, 'new_pin': '654321', 'confirm_new_pin': '654321',
        }, format='json')
        resp = APIClient().post('/api/v1/auth/employee-login/', {
            'business_id': self.biz.pk,
            'employee_code': 'EMP-PIN01',
            'pin': '654321',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_audit_created_on_success(self):
        """Successful PIN change creates a PIN_CHANGED audit entry."""
        self.client.post(self.URL, {
            'current_pin': self.pin, 'new_pin': '654321', 'confirm_new_pin': '654321',
        }, format='json')
        self.assertTrue(
            AccessAuditLog.objects.filter(
                action='PIN_CHANGED',
                actor_type=AccessAuditLog.ActorType.EMPLOYEE,
                entity_id=str(self.employee.pk),
            ).exists()
        )

    # ── Validation failures ────────────────────────────────────────────────────

    def test_wrong_current_pin_returns_401(self):
        """Incorrect current PIN → 401 with code=bad_current_pin."""
        resp = self.client.post(self.URL, {
            'current_pin': '000000', 'new_pin': '654321', 'confirm_new_pin': '654321',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.data.get('code'), 'bad_current_pin')

    def test_wrong_current_pin_creates_access_denied_audit(self):
        """A failed PIN change attempt creates an ACCESS_DENIED audit entry."""
        self.client.post(self.URL, {
            'current_pin': '000000', 'new_pin': '654321', 'confirm_new_pin': '654321',
        }, format='json')
        self.assertTrue(
            AccessAuditLog.objects.filter(
                action='ACCESS_DENIED',
                actor_type=AccessAuditLog.ActorType.EMPLOYEE,
                entity_id=str(self.employee.pk),
            ).exists()
        )

    def test_confirmation_mismatch_returns_400(self):
        """new_pin != confirm_new_pin → 400."""
        resp = self.client.post(self.URL, {
            'current_pin': self.pin, 'new_pin': '654321', 'confirm_new_pin': '999999',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_same_pin_rejected(self):
        """new_pin == current_pin → 400."""
        resp = self.client.post(self.URL, {
            'current_pin': self.pin, 'new_pin': self.pin, 'confirm_new_pin': self.pin,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_pin_format_rejected(self):
        """Non-numeric or too-short new_pin → 400."""
        resp = self.client.post(self.URL, {
            'current_pin': self.pin, 'new_pin': 'abc', 'confirm_new_pin': 'abc',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_rejected(self):
        """No token → not authenticated → 401 or 403."""
        resp = APIClient().post(self.URL, {
            'current_pin': self.pin, 'new_pin': '654321', 'confirm_new_pin': '654321',
        }, format='json')
        self.assertIn(resp.status_code, [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
        ])

    def test_pin_not_leaked_in_any_response(self):
        """change-pin responses never contain login_code_hash."""
        resp = self.client.post(self.URL, {
            'current_pin': self.pin, 'new_pin': '654321', 'confirm_new_pin': '654321',
        }, format='json')
        self.assertNotIn('login_code_hash', resp.data)
        self.assertNotIn('current_pin', resp.data)
        self.assertNotIn('new_pin', resp.data)


# ═══════════════════════════════════════════════════════════════════════════════
# E. must_change_pin enforcement
# ═══════════════════════════════════════════════════════════════════════════════


class PinChangeEnforcementTest(TestCase):
    """
    When must_change_pin=True, the employee can access ONLY whitelisted routes.
    All other operative routes must return 403 with code=pin_change_required.
    """

    def setUp(self):
        self.biz = _make_business('PinEnfBiz')
        self.employee = _make_employee(
            self.biz, code='EMP-ENF01', pin='111222', must_change_pin=True,
        )
        self.client = _employee_client(self.employee, self.biz)

    def test_capabilities_blocked(self):
        """/pos/capabilities/ → 403 pin_change_required when must_change_pin=True."""
        resp = self.client.get('/api/v1/pos/capabilities/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data.get('code'), 'pin_change_required')

    def test_me_allowed_on_whitelist(self):
        """/pos/me/ → 200 allowed even when must_change_pin=True."""
        resp = self.client.get('/api/v1/pos/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_health_allowed_on_whitelist(self):
        """/pos/health/ → 200 allowed even when must_change_pin=True."""
        resp = self.client.get('/api/v1/pos/health/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_change_pin_allowed_on_whitelist(self):
        """/auth/employee-change-pin/ → accessible when must_change_pin=True."""
        resp = self.client.post('/api/v1/auth/employee-change-pin/', {
            'current_pin': '111222', 'new_pin': '333444', 'confirm_new_pin': '333444',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_after_pin_change_capabilities_unlocked(self):
        """
        After successful PIN change, must_change_pin=False and
        /pos/capabilities/ becomes accessible.
        """
        # Change PIN to clear the flag
        self.client.post('/api/v1/auth/employee-change-pin/', {
            'current_pin': '111222', 'new_pin': '999888', 'confirm_new_pin': '999888',
        }, format='json')
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.must_change_pin)

        # Re-authenticate with updated employee state
        new_client = _employee_client(self.employee, self.biz)
        resp = new_client.get('/api/v1/pos/capabilities/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_must_change_pin_false_allows_capabilities(self):
        """Baseline: employee with must_change_pin=False can access /capabilities/."""
        emp = _make_employee(self.biz, code='EMP-ENF02', must_change_pin=False)
        client = _employee_client(emp, self.biz)
        resp = client.get('/api/v1/pos/capabilities/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ═══════════════════════════════════════════════════════════════════════════════
# F. Token edge cases across POS routes
# ═══════════════════════════════════════════════════════════════════════════════


class PosTokenEdgeCasesTest(TestCase):
    """
    Cross-business isolation and token edge cases for POS routes.
    """

    def setUp(self):
        self.biz_a = _make_business('PosEdgeBizA')
        self.biz_b = _make_business('PosEdgeBizB')
        self.emp_a = _make_employee(self.biz_a, code='EMP-EA01')
        self.emp_b = _make_employee(self.biz_b, code='EMP-EB01')

    def test_cross_business_token_rejected(self):
        """
        Token with employee_id from biz_a but business_id=biz_b
        is rejected by EmployeeTokenAuthentication.
        """
        now = timezone.now()
        payload = {
            'actor_type':  'employee',
            'employee_id': str(self.emp_a.pk),
            'business_id': self.biz_b.pk,   # wrong business
            'role_type':   'cashier',
            'iat': int(now.timestamp()),
            'exp': int((now + timedelta(hours=12)).timestamp()),
        }
        backend = TokenBackend(
            algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
            signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
        )
        bad_token = backend.encode(payload)
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN=bad_token)
        resp = client.get('/api/v1/pos/me/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_nonexistent_employee_id_in_token_rejected(self):
        """Token with a random non-existent employee UUID is rejected."""
        import uuid
        now = timezone.now()
        payload = {
            'actor_type':  'employee',
            'employee_id': str(uuid.uuid4()),  # non-existent
            'business_id': self.biz_a.pk,
            'role_type':   'cashier',
            'iat': int(now.timestamp()),
            'exp': int((now + timedelta(hours=12)).timestamp()),
        }
        backend = TokenBackend(
            algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
            signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
        )
        token = backend.encode(payload)
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN=token)
        resp = client.get('/api/v1/pos/me/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_suspended_after_token_issued_blocked_on_health(self):
        """Token issued before suspension → rejected after employee suspended."""
        token = _make_employee_token(self.emp_a, self.biz_a)
        self.emp_a.status = EmployeeProfile.Status.SUSPENDED
        self.emp_a.save(update_fields=['status'])
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN=token)
        resp = client.get('/api/v1/pos/health/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_token_rejected_on_capabilities(self):
        """Expired token → /pos/capabilities/ returns 401."""
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN=_make_expired_token(self.emp_a, self.biz_a))
        resp = client.get('/api/v1/pos/capabilities/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_employee_token_rejected_on_owner_routes(self):
        """
        X-Employee-Token cannot authenticate owner/admin routes.
        EmployeeTokenAuthentication is not in DEFAULT_AUTHENTICATION_CLASSES.
        """
        user = User.objects.create_user(
            username='owneredge@test.com', email='owneredge@test.com', password='pass!'
        )
        Membership.objects.create(user=user, business=self.biz_a, role='owner')
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN=_make_employee_token(self.emp_a, self.biz_a))
        resp = client.get('/api/v1/owner/access/employees/')
        self.assertIn(resp.status_code, [
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN,
        ])

    def test_wrong_actor_type_in_token_rejected(self):
        """Token with actor_type != 'employee' is rejected."""
        now = timezone.now()
        payload = {
            'actor_type':  'user',    # wrong type
            'employee_id': str(self.emp_a.pk),
            'business_id': self.biz_a.pk,
            'role_type':   'cashier',
            'iat': int(now.timestamp()),
            'exp': int((now + timedelta(hours=12)).timestamp()),
        }
        backend = TokenBackend(
            algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
            signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
        )
        token = backend.encode(payload)
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN=token)
        resp = client.get('/api/v1/pos/me/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ═══════════════════════════════════════════════════════════════════════════════
# G. Login hardening (timing + rate-limit awareness)
# ═══════════════════════════════════════════════════════════════════════════════


class LoginHardeningTest(TestCase):
    """Tests for login hardening: generic errors, no info leakage."""

    def setUp(self):
        self.biz = _make_business('LoginHardenBiz')
        self.employee = _make_employee(self.biz, code='EMP-LH01', pin='777888')

    def test_nonexistent_employee_returns_generic_error(self):
        """Missing employee_code returns 401 (no 404, no detail about existence)."""
        resp = APIClient().post('/api/v1/auth/employee-login/', {
            'business_id': self.biz.pk, 'employee_code': 'EMP-INVALID', 'pin': '000000',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        # Must not reveal that the employee doesn't exist
        self.assertNotIn('not found', str(resp.data).lower())

    def test_wrong_business_id_returns_generic_error(self):
        """Invalid business_id returns 401 (not 404)."""
        resp = APIClient().post('/api/v1/auth/employee-login/', {
            'business_id': 999999, 'employee_code': 'EMP-LH01', 'pin': '777888',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wrong_pin_returns_generic_error(self):
        """Incorrect PIN returns 401 with generic message."""
        resp = APIClient().post('/api/v1/auth/employee-login/', {
            'business_id': self.biz.pk, 'employee_code': 'EMP-LH01', 'pin': '000000',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        # Must NOT reveal that only the PIN was wrong (vs employee not found)
        error_text = str(resp.data).lower()
        self.assertNotIn('not found', error_text)


# ═══════════════════════════════════════════════════════════════════════════════
# H. Operative permissions matrix
# ═══════════════════════════════════════════════════════════════════════════════


class OperativePermissionsMatrixTest(TestCase):
    """Tests for resolve_pos_capabilities() role matrix consistency."""

    def setUp(self):
        self.biz = _make_business('PermMatrixBiz')

    def _caps(self, role_type: str):
        from apps.accounts.operative_permissions import resolve_pos_capabilities
        emp = _make_employee(self.biz, code=f'EMP-PM-{role_type}', role_type=role_type)
        return resolve_pos_capabilities(emp)

    def test_kitchen_has_no_sale_capability(self):
        """Kitchen role cannot create sales."""
        caps = self._caps('kitchen')
        self.assertFalse(caps.get('can_create_sale'))
        self.assertTrue(caps.get('can_open_pos'))

    def test_server_has_no_cash_capability(self):
        """Server role cannot manage cash."""
        caps = self._caps('server')
        self.assertFalse(caps.get('can_manage_cash'))
        self.assertTrue(caps.get('can_create_sale'))

    def test_all_capabilities_present_in_result(self):
        """resolve_pos_capabilities always returns ALL capability keys."""
        from apps.accounts.operative_permissions import _ALL_CAPABILITIES
        for role_type in ('cashier', 'server', 'kitchen', 'delivery', 'manager_op'):
            caps = self._caps(role_type)
            for key in _ALL_CAPABILITIES:
                self.assertIn(key, caps, f'Missing capability {key} for {role_type}')

    def test_stable_shape_for_unknown_role(self):
        """An employee with an unrecognised role_type gets all-False capabilities."""
        from apps.accounts.operative_permissions import resolve_pos_capabilities, _ALL_CAPABILITIES
        emp = _make_employee(self.biz, code='EMP-PM-UNK', role_type='cashier')
        emp.role_type = 'unknown_future_role'
        # Don't save — just call the function directly
        caps = resolve_pos_capabilities(emp)
        self.assertEqual(set(caps.keys()), set(_ALL_CAPABILITIES))
        self.assertFalse(any(caps.values()))

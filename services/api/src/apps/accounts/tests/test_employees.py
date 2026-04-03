"""
accounts/tests/test_employees.py — Operative employee module tests.

Covers (9 backend cases):
  1.  Create a valid operative employee.
  2.  Duplicate employee_code in the same business is rejected.
  3.  Reset-pin marks must_change_pin and creates an audit entry.
  4.  Suspended employee cannot log in.
  5.  Operative login returns actor_type='employee' and correct permissions.
  6.  Employee belonging to another business is not accessible.
  7.  permission_overrides modify effective permissions.
  8.  OWNER / ADMIN can manage employees; regular STAFF cannot.
  9.  Verify employee token contains expected JWT claims.
"""
from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.backends import TokenBackend
from django.conf import settings

from apps.accounts.models import AccessAuditLog, EmployeeProfile, Membership
from apps.business.models import Business

User = get_user_model()

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_user(email: str, password: str = 'pass1234!') -> User:
    return User.objects.create_user(username=email, email=email, password=password)


def _make_business(name: str = 'TestBiz', service: str = 'gestion') -> Business:
    slug = name.lower().replace(' ', '-')
    return Business.objects.create(name=name, slug=slug, default_service=service, status='active')


def _make_membership(user, business, role: str = 'owner') -> Membership:
    return Membership.objects.create(user=user, business=business, role=role)


def _make_employee(
    business: Business,
    code: str = 'EMP-0001',
    role_type: str = EmployeeProfile.RoleType.CASHIER,
    pin: str = '123456',
    status: str = EmployeeProfile.Status.ACTIVE,
) -> EmployeeProfile:
    return EmployeeProfile.objects.create(
        business=business,
        first_name='Ana',
        last_name='García',
        alias='Ana',
        employee_code=code,
        role_type=role_type,
        credential_type=EmployeeProfile.CredentialType.PIN,
        login_code_hash=make_password(pin),
        must_change_pin=False,
        status=status,
    )


def _auth_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ── Test cases ────────────────────────────────────────────────────────────────


class CreateEmployeeTest(TestCase):
    """Case 1 + 2: Create employee; reject duplicate code."""

    def setUp(self):
        self.biz = _make_business('BizA')
        self.owner = _make_user('owner@test.com')
        self.membership = _make_membership(self.owner, self.biz, 'owner')
        self.client = _auth_client(self.owner)

    def test_create_employee_valid(self):
        """Case 1: Valid employee creation returns 201 and includes initial_pin."""
        resp = self.client.post(
            '/api/v1/owner/access/employees/',
            {
                'first_name':      'Pedro',
                'last_name':       'López',
                'role_type':       'cashier',
                'initial_pin':     '654321',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        data = resp.data
        self.assertIn('id', data)
        self.assertIn('initial_pin', data)
        self.assertEqual(data['initial_pin'], '654321')
        self.assertTrue(data['must_change_pin'])
        # Employee code should have been auto-generated
        self.assertTrue(data['employee_code'].startswith('EMP-'))
        # Audit entry created
        self.assertTrue(
            AccessAuditLog.objects.filter(
                action='EMPLOYEE_CREATED',
                business=self.biz,
                entity_type='employee_profile',
            ).exists()
        )

    def test_create_employee_duplicate_code(self):
        """Case 2: Duplicate employee_code in same business returns 400."""
        _make_employee(self.biz, code='EMP-0001')
        resp = self.client.post(
            '/api/v1/owner/access/employees/',
            {
                'first_name':    'Juan',
                'last_name':     'Pérez',
                'role_type':     'server',
                'employee_code': 'EMP-0001',  # duplicate
                'initial_pin':   '111222',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ResetPinTest(TestCase):
    """Case 3: Reset-pin sets must_change_pin and creates audit entry."""

    def setUp(self):
        self.biz = _make_business('BizB')
        self.owner = _make_user('owner2@test.com')
        self.membership = _make_membership(self.owner, self.biz, 'owner')
        self.employee = _make_employee(self.biz, code='EMP-0002', pin='999888')
        self.client = _auth_client(self.owner)

    def test_reset_pin_marks_must_change(self):
        """Case 3: Reset-pin returns temporary_pin and sets must_change_pin."""
        resp = self.client.post(
            f'/api/v1/owner/access/employees/{self.employee.pk}/reset-pin/',
            {'new_pin': '555666'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(resp.data['must_change_pin'])
        self.assertEqual(resp.data['temporary_pin'], '555666')
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.must_change_pin)
        # Audit
        self.assertTrue(
            AccessAuditLog.objects.filter(
                action='PIN_RESET',
                entity_id=str(self.employee.pk),
            ).exists()
        )

    def test_reset_pin_generates_pin_if_none_supplied(self):
        """Case 3b: If new_pin not provided, a random 6-digit PIN is returned."""
        resp = self.client.post(
            f'/api/v1/owner/access/employees/{self.employee.pk}/reset-pin/',
            {},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pin = resp.data['temporary_pin']
        self.assertTrue(pin.isdigit())
        self.assertEqual(len(pin), 6)
        self.assertTrue(resp.data['pin_was_generated'])


class SuspendedEmployeeLoginTest(TestCase):
    """Case 4: Suspended employee cannot log in."""

    def setUp(self):
        self.client = APIClient()
        self.biz = _make_business('BizCsuspend')
        self.employee = _make_employee(
            self.biz, code='EMP-0010', pin='112233',
            status=EmployeeProfile.Status.SUSPENDED,
        )

    def test_suspended_employee_blocked(self):
        resp = self.client.post(
            '/api/v1/auth/employee-login/',
            {
                'business_code': self.biz.slug,
                'employee_code': 'EMP-0010',
                'pin':           '112233',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class EmployeeLoginSuccessTest(TestCase):
    """Case 5: Successful operative login returns correct claims."""

    def setUp(self):
        self.biz = _make_business('BizD')
        self.employee = _make_employee(
            self.biz, code='EMP-0004',
            role_type=EmployeeProfile.RoleType.CASHIER,
            pin='777888',
        )
        self.client = APIClient()

    def test_login_success_returns_employee_token(self):
        resp = self.client.post(
            '/api/v1/auth/employee-login/',
            {
                'business_code': self.biz.slug,
                'employee_code': 'EMP-0004',
                'pin':           '777888',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        data = resp.data
        self.assertEqual(data['actor_type'], 'employee')
        self.assertEqual(data['role_type'], 'cashier')
        self.assertIn('token', data)
        self.assertIn('permissions', data)
        self.assertEqual(data['employee_id'], str(self.employee.pk))
        self.assertEqual(data['business_id'], self.biz.pk)

    def test_login_wrong_pin_returns_401(self):
        resp = self.client.post(
            '/api/v1/auth/employee-login/',
            {
                'business_code': self.biz.slug,
                'employee_code': 'EMP-0004',
                'pin':           '000000',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class CrossBusinessIsolationTest(TestCase):
    """Case 6: Owner of BizA cannot access employees of BizB."""

    def setUp(self):
        self.biz_a = _make_business('BizIsoA')
        self.biz_b = _make_business('BizIsoB')
        self.owner_a = _make_user('iso_owner@test.com')
        _make_membership(self.owner_a, self.biz_a, 'owner')
        self.emp_b = _make_employee(self.biz_b, code='EMP-0099')
        self.client = _auth_client(self.owner_a)

    def test_cannot_access_other_business_employee(self):
        resp = self.client.get(
            f'/api/v1/owner/access/employees/{self.emp_b.pk}/',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_reset_pin_of_other_business_employee(self):
        resp = self.client.post(
            f'/api/v1/owner/access/employees/{self.emp_b.pk}/reset-pin/',
            {'new_pin': '123456'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class PermissionOverridesTest(TestCase):
    """Case 7: permission_overrides are applied on top of role defaults."""

    def setUp(self):
        self.biz = _make_business('BizOvr', service='gestion')
        self.emp = _make_employee(
            self.biz, code='EMP-0005',
            role_type=EmployeeProfile.RoleType.CASHIER,
            pin='321654',
        )
        # Override: strip a permission the cashier role normally has
        # (we don't know the exact key; we just verify the override logic runs)
        self.emp.permission_overrides = {'view_reports': False}
        self.emp.save(update_fields=['permission_overrides'])
        self.client = APIClient()

    def test_login_permissions_reflect_overrides(self):
        resp = self.client.post(
            '/api/v1/auth/employee-login/',
            {
                'business_code': self.biz.slug,
                'employee_code': 'EMP-0005',
                'pin':           '321654',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # The override must be applied: view_reports should be absent (False perms are excluded)
        perms = resp.data['permissions']
        self.assertNotIn('view_reports', perms)


class RoleBasedManagementAccessTest(TestCase):
    """Case 8: Owner + Admin can manage; Staff/viewer cannot."""

    def setUp(self):
        self.biz = _make_business('BizRoles')
        self.emp_obj = _make_employee(self.biz, code='EMP-0006')

        self.owner    = _make_user('owner_mgmt@test.com')
        self.admin    = _make_user('admin_mgmt@test.com')
        self.staff    = _make_user('staff_mgmt@test.com')

        _make_membership(self.owner, self.biz, 'owner')
        _make_membership(self.admin, self.biz, 'admin')
        _make_membership(self.staff, self.biz, 'viewer')

    def test_owner_can_list_employees(self):
        resp = _auth_client(self.owner).get('/api/v1/owner/access/employees/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_admin_can_list_employees(self):
        resp = _auth_client(self.admin).get('/api/v1/owner/access/employees/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_staff_cannot_list_employees(self):
        resp = _auth_client(self.staff).get('/api/v1/owner/access/employees/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_list_employees(self):
        resp = APIClient().get('/api/v1/owner/access/employees/')
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


class EmployeeTokenClaimsTest(TestCase):
    """Case 9: Generated employee JWT contains expected claims."""

    def setUp(self):
        self.biz = _make_business('BizToken')
        self.employee = _make_employee(
            self.biz, code='EMP-0007',
            role_type=EmployeeProfile.RoleType.SERVER,
            pin='246810',
        )
        self.client = APIClient()

    def test_token_contains_expected_claims(self):
        resp = self.client.post(
            '/api/v1/auth/employee-login/',
            {
                'business_code': self.biz.slug,
                'employee_code': 'EMP-0007',
                'pin':           '246810',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        raw_token = resp.data['token']

        backend = TokenBackend(
            algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
            signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
        )
        payload = backend.decode(raw_token, verify=True)

        self.assertEqual(payload['actor_type'], 'employee')
        self.assertEqual(payload['employee_id'], str(self.employee.pk))
        self.assertEqual(payload['business_id'], self.biz.pk)
        self.assertEqual(payload['role_type'], 'server')
        self.assertIn('exp', payload)
        self.assertIn('iat', payload)


# ══════════════════════════════════════════════════════════════════════════════
# NEW EXTENDED COVERAGE — added in security review
# ══════════════════════════════════════════════════════════════════════════════

import uuid as _uuid
from datetime import timedelta
from rest_framework import exceptions as drf_exceptions
from rest_framework.test import APIRequestFactory
from rest_framework.request import Request as DrfRequest
from apps.accounts.authentication import EmployeeIdentity, EmployeeTokenAuthentication


# ── Helper to generate an employee JWT without going through the full view ───

def _make_employee_token(employee, business) -> str:
    """Generate a valid employee JWT the same way EmployeeLoginView does."""
    from django.utils import timezone
    now = timezone.now()
    payload = {
        'actor_type':   'employee',
        'employee_id':  str(employee.pk),
        'business_id':  business.pk,
        'role_type':    employee.role_type,
        'iat':          int(now.timestamp()),
        'exp':          int((now + timedelta(hours=12)).timestamp()),
    }
    from rest_framework_simplejwt.backends import TokenBackend
    backend = TokenBackend(
        algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
        signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
    )
    return backend.encode(payload)


# ── 10. EmployeeTokenAuthentication unit tests ────────────────────────────────

class EmployeeTokenAuthUnitTest(TestCase):
    """
    Tests for EmployeeTokenAuthentication authenticate() directly.
    Covers: missing header, valid token, malformed token, expired token,
    post-suspension rejection, regular-user JWT rejected.
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.biz = _make_business('BizUnitAuth')
        self.employee = _make_employee(self.biz, code='EMP-UA01', pin='111000')

    def _drf_request(self, **kwargs) -> DrfRequest:
        raw = self.factory.get('/fake/', **kwargs)
        return DrfRequest(raw)

    def test_missing_header_returns_none(self):
        """No X-Employee-Token header → returns None (chain continues)."""
        result = EmployeeTokenAuthentication().authenticate(self._drf_request())
        self.assertIsNone(result)

    def test_valid_token_returns_identity(self):
        """Valid employee token returns (EmployeeIdentity, payload)."""
        token = _make_employee_token(self.employee, self.biz)
        req = self._drf_request(HTTP_X_EMPLOYEE_TOKEN=token)
        identity, payload = EmployeeTokenAuthentication().authenticate(req)
        self.assertIsInstance(identity, EmployeeIdentity)
        self.assertEqual(str(identity.employee.pk), str(self.employee.pk))
        self.assertEqual(payload['actor_type'], 'employee')

    def test_malformed_token_raises(self):
        """Garbage string raises AuthenticationFailed."""
        req = self._drf_request(HTTP_X_EMPLOYEE_TOKEN='not.a.jwt.at.all')
        with self.assertRaises(drf_exceptions.AuthenticationFailed):
            EmployeeTokenAuthentication().authenticate(req)

    def test_expired_token_raises(self):
        """Token whose exp is in the past raises AuthenticationFailed."""
        from django.utils import timezone
        from rest_framework_simplejwt.backends import TokenBackend
        now = timezone.now()
        payload = {
            'actor_type':  'employee',
            'employee_id': str(self.employee.pk),
            'business_id': self.biz.pk,
            'role_type':   'cashier',
            'iat': int((now - timedelta(hours=14)).timestamp()),
            'exp': int((now - timedelta(hours=2)).timestamp()),   # already expired
        }
        backend = TokenBackend(
            algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
            signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
        )
        expired_token = backend.encode(payload)
        req = self._drf_request(HTTP_X_EMPLOYEE_TOKEN=expired_token)
        with self.assertRaises(drf_exceptions.AuthenticationFailed):
            EmployeeTokenAuthentication().authenticate(req)

    def test_token_after_suspension_rejected(self):
        """Token issued before suspension is rejected once employee is suspended."""
        token = _make_employee_token(self.employee, self.biz)
        # Suspend AFTER token was issued
        self.employee.status = EmployeeProfile.Status.SUSPENDED
        self.employee.save(update_fields=['status'])

        req = self._drf_request(HTTP_X_EMPLOYEE_TOKEN=token)
        with self.assertRaises(drf_exceptions.AuthenticationFailed):
            EmployeeTokenAuthentication().authenticate(req)

    def test_non_employee_jwt_rejected(self):
        """A standard simplejwt Access token sent as X-Employee-Token is rejected."""
        from rest_framework_simplejwt.tokens import AccessToken
        user = _make_user('admintoken_test@test.com')
        admin_jwt = str(AccessToken.for_user(user))
        req = self._drf_request(HTTP_X_EMPLOYEE_TOKEN=admin_jwt)
        with self.assertRaises(drf_exceptions.AuthenticationFailed):
            EmployeeTokenAuthentication().authenticate(req)

    def test_token_wrong_business_rejected(self):
        """Token for employee_id that belongs to a different business is invalid."""
        other_biz = _make_business('OtherBizUA')
        from django.utils import timezone
        from rest_framework_simplejwt.backends import TokenBackend
        now = timezone.now()
        payload = {
            'actor_type':  'employee',
            # employee is on self.biz, but token claims other_biz
            'employee_id': str(self.employee.pk),
            'business_id': other_biz.pk,
            'role_type':   'cashier',
            'iat': int(now.timestamp()),
            'exp': int((now + timedelta(hours=12)).timestamp()),
        }
        backend = TokenBackend(
            algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
            signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
        )
        token = backend.encode(payload)
        req = self._drf_request(HTTP_X_EMPLOYEE_TOKEN=token)
        with self.assertRaises(drf_exceptions.AuthenticationFailed):
            EmployeeTokenAuthentication().authenticate(req)


# ── 11. Employee token rejected on owner routes ───────────────────────────────

class EmployeeTokenOnOwnerRouteTest(TestCase):
    """
    Employee tokens (X-Employee-Token) are rejected by admin/owner endpoints.
    EmployeeTokenAuthentication is NOT in DEFAULT_AUTHENTICATION_CLASSES, so
    any request carrying only X-Employee-Token is treated as unauthenticated.
    """

    def setUp(self):
        self.biz = _make_business('BizOwnerIso2')
        self.employee = _make_employee(self.biz, code='EMP-OWN1', pin='555444')

    def _login(self):
        resp = APIClient().post(
            '/api/v1/auth/employee-login/',
            {'business_code': self.biz.slug, 'employee_code': 'EMP-OWN1', 'pin': '555444'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp.data['token']

    def test_employee_x_header_rejected_on_owner_list(self):
        """X-Employee-Token header alone cannot authenticate owner routes."""
        token = self._login()
        client = APIClient()
        client.credentials(HTTP_X_EMPLOYEE_TOKEN=token)
        resp = client.get('/api/v1/owner/access/employees/')
        self.assertIn(resp.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ])

    def test_employee_jwt_as_bearer_rejected_on_owner_route(self):
        """
        Employee JWT placed in Authorization: Bearer is rejected by
        CookieJWTAuthentication (no user_id claim → InvalidToken → 401).
        """
        token = self._login()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        resp = client.get('/api/v1/owner/access/employees/')
        self.assertIn(resp.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ])


# ── 12. PIN never leaked in list / detail responses ───────────────────────────

class PinNotLeakedTest(TestCase):
    """login_code_hash is never returned by any list or detail endpoint."""

    def setUp(self):
        self.biz = _make_business('BizPinLeak')
        self.owner = _make_user('pinleak@test.com')
        self.mem = _make_membership(self.owner, self.biz, 'owner')
        self.employee = _make_employee(self.biz, code='EMP-PL01', pin='999000')
        self.client = _auth_client(self.owner)

    def test_hash_absent_in_list(self):
        resp = self.client.get('/api/v1/owner/access/employees/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for emp in resp.data:
            self.assertNotIn('login_code_hash', emp)
            # initial_pin must NOT appear in list — only on create response
            self.assertNotIn('initial_pin', emp)

    def test_hash_absent_in_detail(self):
        resp = self.client.get(f'/api/v1/owner/access/employees/{self.employee.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn('login_code_hash', resp.data)
        self.assertNotIn('initial_pin', resp.data)

    def test_initial_pin_present_only_on_create(self):
        """initial_pin IS returned on POST /employees/ — exactly once."""
        resp = self.client.post(
            '/api/v1/owner/access/employees/',
            {'first_name': 'Once', 'last_name': 'Pin', 'role_type': 'cashier'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('initial_pin', resp.data)
        # Subsequent GET detail must NOT return it
        emp_id = resp.data['id']
        detail = self.client.get(f'/api/v1/owner/access/employees/{emp_id}/')
        self.assertNotIn('initial_pin', detail.data)


# ── 13. Login with wrong employee_code ────────────────────────────────────────

class LoginWrongCodeTest(TestCase):
    """Login with a nonexistent employee_code returns 401 (not 404/500)."""

    def setUp(self):
        self.biz = _make_business('BizWrongCode')
        self.client = APIClient()

    def test_nonexistent_code_returns_401(self):
        resp = self.client.post(
            '/api/v1/auth/employee-login/',
            {'business_code': self.biz.slug, 'employee_code': 'DOESNT-EXIST', 'pin': '000000'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_nonexistent_business_code_returns_401(self):
        resp = self.client.post(
            '/api/v1/auth/employee-login/',
            {'business_code': 'nonexistent-biz', 'employee_code': 'EMP-0001', 'pin': '000000'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ── 14. Audit log completeness ────────────────────────────────────────────────

class AuditLogCompletenessTest(TestCase):
    """Critical actions must produce AccessAuditLog entries."""

    def setUp(self):
        self.biz = _make_business('BizAudit2')
        self.owner = _make_user('auditcomplete@test.com')
        _make_membership(self.owner, self.biz, 'owner')
        self.employee = _make_employee(self.biz, code='EMP-AUD2', pin='123777')
        self.client = _auth_client(self.owner)

    def test_audit_on_suspend(self):
        """EMPLOYEE_SUSPENDED audit log is created on suspension."""
        resp = self.client.post(
            f'/api/v1/owner/access/employees/{self.employee.pk}/suspend/'
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            AccessAuditLog.objects.filter(
                action='EMPLOYEE_SUSPENDED',
                entity_id=str(self.employee.pk),
            ).exists()
        )

    def test_audit_on_reactivate(self):
        """EMPLOYEE_REACTIVATED audit log is created on reactivation."""
        self.employee.status = EmployeeProfile.Status.SUSPENDED
        self.employee.save(update_fields=['status'])

        resp = self.client.post(
            f'/api/v1/owner/access/employees/{self.employee.pk}/reactivate/'
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            AccessAuditLog.objects.filter(
                action='EMPLOYEE_REACTIVATED',
                entity_id=str(self.employee.pk),
            ).exists()
        )

    def test_audit_successful_login(self):
        """OPERATOR_SESSION_STARTED is logged after a valid login."""
        APIClient().post(
            '/api/v1/auth/employee-login/',
            {'business_code': self.biz.slug, 'employee_code': 'EMP-AUD2', 'pin': '123777'},
            format='json',
        )
        self.assertTrue(
            AccessAuditLog.objects.filter(
                action='OPERATOR_SESSION_STARTED',
                entity_id=str(self.employee.pk),
            ).exists()
        )

    def test_audit_failed_login_bad_pin(self):
        """LOGIN_FAILED is logged when PIN is incorrect for a known employee."""
        APIClient().post(
            '/api/v1/auth/employee-login/',
            {'business_code': self.biz.slug, 'employee_code': 'EMP-AUD2', 'pin': '000000'},
            format='json',
        )
        self.assertTrue(
            AccessAuditLog.objects.filter(
                action='LOGIN_FAILED',
                entity_id=str(self.employee.pk),
            ).exists()
        )

    def test_audit_update_employee(self):
        """EMPLOYEE_UPDATED or ROLE_CHANGED is logged on PATCH."""
        resp = self.client.patch(
            f'/api/v1/owner/access/employees/{self.employee.pk}/',
            {'first_name': 'NuevoNombre'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            AccessAuditLog.objects.filter(
                action__in=['EMPLOYEE_UPDATED', 'ROLE_CHANGED'],
                entity_id=str(self.employee.pk),
            ).exists()
        )


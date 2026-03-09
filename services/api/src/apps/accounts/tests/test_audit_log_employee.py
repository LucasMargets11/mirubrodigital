"""
accounts/tests/test_audit_log_employee.py — Tests for AuditLogSerializer null-safety.

Covers:
  1. Serializer does not crash when actor is NULL (SYSTEM action).
  2. Serializer does not crash when target_user is NULL.
  3. Serializer exposes actor_employee_code when actor is an employee.
  4. Serializer exposes actor_type correctly for all three actor types.
  5. Serializer works normally for USER actor with non-null target.
  6. Serializer exposes entity_type and entity_id.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase

from apps.accounts.models import AccessAuditLog, EmployeeProfile, Membership
from apps.accounts.owner_serializers import AuditLogSerializer
from apps.business.models import Business

User = get_user_model()


def _make_business(name: str = 'AuditBiz') -> Business:
    return Business.objects.create(name=name, default_service='gestion', status='active')


def _make_user(email: str) -> User:
    return User.objects.create_user(username=email, email=email, password='pass1234!')


def _make_employee(business: Business, code: str = 'EMP-0001') -> EmployeeProfile:
    return EmployeeProfile.objects.create(
        business=business,
        first_name='Ana',
        last_name='González',
        alias='Ana',
        employee_code=code,
        role_type=EmployeeProfile.RoleType.CASHIER,
        credential_type=EmployeeProfile.CredentialType.PIN,
        login_code_hash=make_password('123456'),
        must_change_pin=False,
        status=EmployeeProfile.Status.ACTIVE,
    )


class AuditLogSerializerNullActorTest(TestCase):
    """Case 1: actor=None, target_user=None — should not crash."""

    def setUp(self):
        self.biz = _make_business('NullBiz')
        self.log = AccessAuditLog.objects.create(
            action='CASH_SESSION_OPENED',
            actor=None,
            actor_type=AccessAuditLog.ActorType.SYSTEM,
            actor_employee=None,
            target_user=None,
            business=self.biz,
            details={},
        )

    def test_serializer_does_not_crash_with_null_actor(self):
        data = AuditLogSerializer(self.log).data
        self.assertIsNone(data['actor_email'])
        self.assertEqual(data['actor_name'], 'Sistema')
        self.assertIsNone(data['actor_employee_code'])

    def test_serializer_does_not_crash_with_null_target_user(self):
        data = AuditLogSerializer(self.log).data
        self.assertIsNone(data['target_email'])
        self.assertIsNone(data['target_name'])

    def test_actor_type_system(self):
        data = AuditLogSerializer(self.log).data
        self.assertEqual(data['actor_type'], AccessAuditLog.ActorType.SYSTEM)


class AuditLogSerializerEmployeeActorTest(TestCase):
    """Case 3 + 4: actor_employee set, actor_type=EMPLOYEE."""

    def setUp(self):
        self.biz = _make_business('EmpBiz')
        self.employee = _make_employee(self.biz, 'EMP-0099')
        self.log = AccessAuditLog.objects.create(
            action='CASH_SESSION_OPENED',
            actor=None,
            actor_type=AccessAuditLog.ActorType.EMPLOYEE,
            actor_employee=self.employee,
            target_user=None,
            business=self.biz,
            entity_type='cash_session',
            entity_id='some-uuid-here',
            details={'opening_cash_amount': '500.00'},
        )

    def test_actor_employee_code_is_exposed(self):
        data = AuditLogSerializer(self.log).data
        self.assertEqual(data['actor_employee_code'], 'EMP-0099')

    def test_actor_email_is_none_for_employee(self):
        data = AuditLogSerializer(self.log).data
        self.assertIsNone(data['actor_email'])

    def test_actor_name_from_employee(self):
        data = AuditLogSerializer(self.log).data
        # alias is set on the employee
        self.assertEqual(data['actor_name'], 'Ana')

    def test_actor_type_employee(self):
        data = AuditLogSerializer(self.log).data
        self.assertEqual(data['actor_type'], AccessAuditLog.ActorType.EMPLOYEE)

    def test_entity_type_and_entity_id_exposed(self):
        data = AuditLogSerializer(self.log).data
        self.assertEqual(data['entity_type'], 'cash_session')
        self.assertEqual(data['entity_id'], 'some-uuid-here')

    def test_target_null_does_not_crash(self):
        data = AuditLogSerializer(self.log).data
        self.assertIsNone(data['target_email'])
        self.assertIsNone(data['target_name'])


class AuditLogSerializerUserActorTest(TestCase):
    """Case 5: USER actor with real user and real target_user."""

    def setUp(self):
        self.biz = _make_business('UserBiz')
        self.actor_user = _make_user('actor@biz.com')
        self.target_user = _make_user('target@biz.com')
        self.target_user.first_name = 'Target'
        self.target_user.last_name = 'User'
        self.target_user.save()
        self.log = AccessAuditLog.objects.create(
            action='ROLE_CHANGED',
            actor=self.actor_user,
            actor_type=AccessAuditLog.ActorType.USER,
            actor_employee=None,
            target_user=self.target_user,
            business=self.biz,
            details={'old_role': 'staff', 'new_role': 'manager'},
        )

    def test_actor_email_from_user(self):
        data = AuditLogSerializer(self.log).data
        self.assertEqual(data['actor_email'], 'actor@biz.com')

    def test_target_email_from_user(self):
        data = AuditLogSerializer(self.log).data
        self.assertEqual(data['target_email'], 'target@biz.com')

    def test_target_name_from_user(self):
        data = AuditLogSerializer(self.log).data
        self.assertEqual(data['target_name'], 'Target User')

    def test_actor_employee_code_is_none_for_user_actor(self):
        data = AuditLogSerializer(self.log).data
        self.assertIsNone(data['actor_employee_code'])

    def test_actor_type_user(self):
        data = AuditLogSerializer(self.log).data
        self.assertEqual(data['actor_type'], AccessAuditLog.ActorType.USER)


class AuditLogSerializerNoAliasEmployeeTest(TestCase):
    """Edge case: employee has no alias — actor_name falls back to first+last."""

    def setUp(self):
        self.biz = _make_business('NoAliasBiz')
        self.employee = EmployeeProfile.objects.create(
            business=self.biz,
            first_name='Pedro',
            last_name='Ramírez',
            alias='',                   # no alias
            employee_code='EMP-0002',
            role_type=EmployeeProfile.RoleType.CASHIER,
            credential_type=EmployeeProfile.CredentialType.PIN,
            login_code_hash=make_password('111111'),
            must_change_pin=False,
            status=EmployeeProfile.Status.ACTIVE,
        )
        self.log = AccessAuditLog.objects.create(
            action='CASH_SESSION_CLOSED',
            actor=None,
            actor_type=AccessAuditLog.ActorType.EMPLOYEE,
            actor_employee=self.employee,
            target_user=None,
            business=self.biz,
        )

    def test_actor_name_fallback_to_full_name(self):
        data = AuditLogSerializer(self.log).data
        self.assertEqual(data['actor_name'], 'Pedro Ramírez')

"""PROD-02F4 — Protección de propietarios y auditoría transaccional del provisioning.

Una cuenta existente sólo se asocia como owner de un cliente nuevo con
confirmación explícita (`attach_existing_owner` + el token emitido para ESA
identidad y ESE admin), en todos los productos. Cuentas inactivas, ambiguas,
superusuarios, personal de plataforma y cuentas cuyas credenciales controla
otro negocio se rechazan. La auditoría del alta es obligatoria y forma parte
de la misma transacción.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from datetime import datetime, timedelta
from rest_framework.test import APIClient

from apps.accounts.admin_client_provisioning_service import (
    ExistingOwnerConfirmationInvalidError,
    ExistingOwnerRequiresConfirmationError,
    provision_admin_client,
)
from apps.accounts.models import AccessAuditLog, AccountProfile, EmployeeProfile, Membership
from apps.accounts.platform_audit import record_platform_action as real_record
from apps.accounts.tests.owner_confirmation_helpers import call_confirming_owner
from apps.accounts.tests.test_admin_clientes_04c_google_preauthorized import (
    PREAUTH_URL,
    _DRF_OVERRIDE,
    _ensure_plan,
    _google_success,
)
from apps.accounts.tests.test_admin_clientes_reception_provisioning_02f2 import CLIENTS_URL, _Base, _staff
from apps.billing.models import ReceptionAIUsagePolicy, SubscriptionV2
from apps.business.models import Business

User = get_user_model()
CONFIRM = 'existing_owner_requires_confirmation'
INVALID = 'existing_owner_confirmation_invalid'
NOT_ELIGIBLE = 'owner_account_not_eligible'


def _existing_owner(email=None, **user_fields):
    """A self-service owner of its own business (the regular reusable case)."""
    email = email or f'dueno-{uuid.uuid4().hex[:8]}@example.test'
    user = User.objects.create_user(
        username=email, email=email, password='OriginalPass123!',
        first_name='Original', last_name='Owner', **user_fields,
    )
    biz = Business.objects.create(name='Negocio Previo Secreto', slug=f'previo-{uuid.uuid4().hex[:8]}', status='active')
    Membership.objects.create(user=user, business=biz, role='owner')
    return user, biz


def _employee_membership(user, business, role, **fields):
    # bulk_create skips Membership.save()'s seat check: the fixture only needs
    # the row to exist (the seat rule is unrelated to owner eligibility).
    Membership.objects.bulk_create([Membership(user=user, business=business, role=role, **fields)])


def _snapshot(user):
    user.refresh_from_db()
    profile = AccountProfile.objects.get(user=user)
    return {
        'password': user.password, 'first_name': user.first_name, 'last_name': user.last_name,
        'email': user.email, 'is_active': user.is_active, 'is_staff': user.is_staff,
        'is_superuser': user.is_superuser, 'account_status': profile.account_status,
        'email_verified': profile.email_verified, 'google_sub': profile.google_sub,
        'is_platform_staff': profile.is_platform_staff, 'internal_role': profile.internal_role,
        'account_mode': profile.account_mode,
        'memberships': sorted(Membership.objects.filter(user=user).values_list('business_id', 'role', 'status')),
    }


class _OwnerBase(_Base):

    def confirm(self, response, **overrides):
        """The admin confirms the account the 409 prompt identified."""
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data['code'], CONFIRM)
        return self.provision(
            attach_existing_owner=True, owner_confirmation_token=response.data['confirmation']['token'], **overrides,
        )


class NewOwnerTests(_OwnerBase):

    def test_new_email_keeps_the_preauthorized_flow(self):
        response = self.provision(owner_email='Nuevo.Owner@Example.test')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['owner']['created'])
        owner = User.objects.get(pk=response.data['owner']['id'])
        self.assertEqual(owner.email, 'nuevo.owner@example.test')
        self.assertFalse(owner.has_usable_password())
        log = AccessAuditLog.objects.get(action='ADMIN_CLIENT_CREATED', business_id=response.data['business_id'])
        self.assertEqual((log.details['owner_account'], log.details['owner_reuse_confirmed']), ('created', False))


class ExistingOwnerConfirmationTests(_OwnerBase):

    def test_existing_owner_without_confirmation_is_409_and_creates_nothing(self):
        user, previous = _existing_owner()
        before = _snapshot(user)
        response = self.provision(owner_email=user.email.upper())
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual((response.data['code'], response.data['field']), (CONFIRM, 'owner_email'))
        self.assertEqual(set(response.data['confirmation']), {'token', 'owner_email', 'expires_in_seconds'})
        self.assertEqual(response.data['confirmation']['owner_email'], user.email)
        # Nothing about the account beyond the email the admin typed
        rendered = json.dumps(response.data).lower()
        for leak in (previous.name.lower(), previous.slug, 'original', 'role', 'businesses'):
            self.assertNotIn(leak, rendered.replace(response.data['confirmation']['token'].lower(), ''))
        self.assertFalse(Business.objects.filter(default_service='reception').exists())
        self.assertFalse(AccessAuditLog.objects.filter(action='ADMIN_CLIENT_CREATED').exists())
        self.assertEqual(_snapshot(user), before)

    def test_confirmed_existing_owner_is_reused_without_touching_the_account(self):
        user, previous = _existing_owner()
        AccountProfile.objects.filter(user=user).update(google_sub='sub-previo', email_verified=True)
        before = _snapshot(user)
        response = self.confirm(self.provision(owner_email=user.email), owner_email=user.email)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data['owner']['created'])
        self.assertEqual(response.data['owner']['id'], user.pk)
        after = _snapshot(user)
        new_membership = (response.data['business_id'], 'owner', 'active')
        self.assertEqual(after.pop('memberships'), sorted(before.pop('memberships') + [new_membership]))
        self.assertEqual(after, before)  # password, profile, roles, flags untouched
        self.assertEqual(User.objects.filter(email__iexact=user.email).count(), 1)
        details = AccessAuditLog.objects.get(action='ADMIN_CLIENT_CREATED', business_id=response.data['business_id']).details
        self.assertEqual((details['owner_account'], details['owner_reuse_confirmed'], details['owner_user_id']),
                         ('reused', True, user.pk))

    def test_owner_of_several_businesses_keeps_every_previous_membership(self):
        user, _ = _existing_owner()
        other = Business.objects.create(name='Segundo', slug=f'seg-{uuid.uuid4().hex[:8]}', status='active')
        branch = Business.objects.create(name='Sucursal', slug=f'suc-{uuid.uuid4().hex[:8]}', parent=other, status='active')
        Membership.objects.create(user=user, business=other, role='owner')
        Membership.objects.create(user=user, business=branch, role='owner', status=Membership.Status.SUSPENDED)
        before = _snapshot(user)['memberships']
        response = self.confirm(self.provision(owner_email=user.email), owner_email=user.email)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(_snapshot(user)['memberships'],
                         sorted(before + [(response.data['business_id'], 'owner', 'active')]))

    def test_every_product_requires_the_confirmation(self):
        cases = {
            'reception fixed': {},
            'reception custom': {'usage_tier': 'reception_custom', 'custom_included_sessions': 70},
            'turnos ia': {'service_type': 'appointments', 'plan_code': 'appointments_ai', 'usage_tier': 'ai_300'},
            'gestion': {'service_type': 'gestion', 'plan_code': _ensure_plan().code, 'usage_tier': ...},
        }
        user, _ = _existing_owner()
        for label, overrides in cases.items():
            with self.subTest(product=label):
                prompt = self.provision(owner_email=user.email, **overrides)
                self.assertEqual((prompt.status_code, prompt.data['code']), (409, CONFIRM))
                response = self.confirm(prompt, owner_email=user.email, **overrides)
                self.assertEqual(response.status_code, 201, response.data)
                self.assertFalse(response.data['owner']['created'])
        self.assertEqual(Membership.objects.filter(user=user, role='owner').count(), 1 + len(cases))

    def test_custom_reception_reuse_is_atomic_with_its_policy_and_audit(self):
        user, _ = _existing_owner()
        response = self.confirm(
            self.provision(owner_email=user.email, usage_tier='reception_custom', custom_included_sessions=55),
            owner_email=user.email, usage_tier='reception_custom', custom_included_sessions=55,
        )
        self.assertEqual(response.status_code, 201, response.data)
        sub = SubscriptionV2.objects.get(business_id=response.data['business_id'])
        policy = ReceptionAIUsagePolicy.objects.get(subscription=sub)
        log = AccessAuditLog.objects.get(action='ADMIN_CLIENT_CREATED', business_id=sub.business_id)
        self.assertEqual((log.actor_id, log.target_user_id), (self.admin.pk, user.pk))
        expected = {
            'business_id': sub.business_id, 'owner_user_id': user.pk, 'owner_account': 'reused',
            'owner_reuse_confirmed': True, 'subscription_id': str(sub.pk), 'service_type': 'reception',
            'plan_code': 'reception', 'usage_tier': 'reception_custom', 'custom_included_sessions': 55,
            'custom_policy_id': str(policy.pk), 'grant_reason': 'Piloto Recepcionista IA',
        }
        self.assertEqual({k: log.details[k] for k in expected}, expected)
        self.assertEqual(datetime.fromisoformat(log.details['complimentary_start']), sub.current_period_start)
        self.assertEqual(datetime.fromisoformat(log.details['complimentary_end']), sub.current_period_end)
        self.assertTrue(AccessAuditLog.objects.filter(action='ADMIN_OWNER_PREAUTHORIZED', business_id=sub.business_id,
                                                      details__owner_reuse_confirmed=True).exists())

    def test_audit_never_stores_the_confirmation_token(self):
        user, _ = _existing_owner()
        prompt = self.provision(owner_email=user.email)
        token = prompt.data['confirmation']['token']
        self.assertEqual(self.confirm(prompt, owner_email=user.email).status_code, 201)
        for log in AccessAuditLog.objects.all():
            self.assertNotIn(token, json.dumps(log.details))
            self.assertNotIn(token.split(':')[0], json.dumps(log.details))


class ConfirmationBindingTests(_OwnerBase):

    def _token_for(self, email, client=None):
        response = (client or self.client).post(CLIENTS_URL, self.payload(owner_email=email), format='json')
        self.assertEqual(response.data['code'], CONFIRM)
        return response.data['confirmation']['token']

    def _assert_invalid(self, response):
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual((response.data['code'], response.data['field']), (INVALID, 'owner_email'))
        self.assertEqual(set(response.data['confirmation']), {'token', 'owner_email', 'expires_in_seconds'})
        self.assertFalse(Business.objects.filter(default_service='reception').exists())

    def test_token_for_one_email_never_confirms_another_account(self):
        first, _ = _existing_owner()
        second, _ = _existing_owner()
        token = self._token_for(first.email)
        response = self.provision(owner_email=second.email, attach_existing_owner=True, owner_confirmation_token=token)
        self._assert_invalid(response)
        # The fresh token is bound to the account identified now and works for it
        retry = self.provision(owner_email=second.email, attach_existing_owner=True,
                               owner_confirmation_token=response.data['confirmation']['token'])
        self.assertEqual(retry.status_code, 201, retry.data)
        self.assertEqual(retry.data['owner']['id'], second.pk)
        self.assertEqual(Membership.objects.filter(user=first).count(), 1)

    def test_token_is_invalid_after_the_account_behind_the_email_changes(self):
        user, _ = _existing_owner()
        email = user.email
        token = self._token_for(email)
        User.objects.filter(pk=user.pk).delete()
        replacement, _ = _existing_owner(email=email)
        self._assert_invalid(self.provision(owner_email=email, attach_existing_owner=True, owner_confirmation_token=token))
        self.assertEqual(Membership.objects.filter(user=replacement).count(), 1)

    def test_token_issued_to_another_admin_is_invalid(self):
        user, _ = _existing_owner()
        other_admin = APIClient()
        other_admin.force_authenticate(user=_staff())
        token = self._token_for(user.email, client=other_admin)
        self._assert_invalid(self.provision(owner_email=user.email, attach_existing_owner=True, owner_confirmation_token=token))

    def test_expired_and_tampered_tokens_are_invalid(self):
        user, _ = _existing_owner()
        token = self._token_for(user.email)
        later = time.time() + 16 * 60
        with patch('django.core.signing.time.time', return_value=later):
            self._assert_invalid(self.provision(owner_email=user.email, attach_existing_owner=True,
                                                owner_confirmation_token=token))
        tampered = token[:-2] + ('AA' if not token.endswith('AA') else 'BB')
        self._assert_invalid(self.provision(owner_email=user.email, attach_existing_owner=True,
                                            owner_confirmation_token=tampered))

    def test_confirmation_for_an_email_without_account_creates_a_new_owner(self):
        user, _ = _existing_owner()
        token = self._token_for(user.email)
        response = self.provision(owner_email=f'otro-{uuid.uuid4().hex[:6]}@example.test',
                                  attach_existing_owner=True, owner_confirmation_token=token)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['owner']['created'])
        self.assertNotEqual(response.data['owner']['id'], user.pk)

    def test_service_level_requires_both_flag_and_bound_token(self):
        user, _ = _existing_owner()
        kwargs = {**self.payload(owner_email=user.email), 'complimentary_start': self.starts_at,
                  'complimentary_end': self.ends_at, 'granted_by': self.admin}
        with self.assertRaises(ExistingOwnerRequiresConfirmationError) as prompt:
            provision_admin_client(**kwargs)
        with self.assertRaises(ExistingOwnerConfirmationInvalidError):
            provision_admin_client(**kwargs, attach_existing_owner=True, owner_confirmation_token='x:y')
        with self.assertRaises(ExistingOwnerRequiresConfirmationError):
            provision_admin_client(**kwargs, owner_confirmation_token=prompt.exception.confirmation_token)
        result = provision_admin_client(**kwargs, attach_existing_owner=True,
                                        owner_confirmation_token=prompt.exception.confirmation_token)
        self.assertTrue(result.owner_reuse_confirmed)

    def test_payload_shape_is_strict(self):
        user, _ = _existing_owner()
        cases = {
            'flag without token': ({'attach_existing_owner': True}, 'owner_confirmation_token'),
            'token without flag': ({'owner_confirmation_token': 'abc'}, 'attach_existing_owner'),
            'string flag': ({'attach_existing_owner': 'true', 'owner_confirmation_token': 'abc'}, 'attach_existing_owner'),
            'numeric flag': ({'attach_existing_owner': 1, 'owner_confirmation_token': 'abc'}, 'attach_existing_owner'),
            'blank token': ({'attach_existing_owner': True, 'owner_confirmation_token': ''}, 'owner_confirmation_token'),
        }
        for label, (extra, field) in cases.items():
            with self.subTest(case=label):
                response = self.provision(owner_email=user.email, **extra)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field, response.data)
        # attach_existing_owner=false behaves exactly like omitting it
        self.assertEqual(self.provision(owner_email=user.email, attach_existing_owner=False).data['code'], CONFIRM)
        self.assertFalse(Business.objects.filter(default_service='reception').exists())


class OwnerEligibilityTests(_OwnerBase):

    def _assert_rejected(self, user, code=NOT_ELIGIBLE):
        before = _snapshot(user)
        response = self.provision(owner_email=user.email)
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual((response.data['code'], response.data['field']), (code, 'owner_email'))
        self.assertNotIn('confirmation', response.data)
        # Not even a forged confirmation gets past eligibility
        forged = self.provision(owner_email=user.email, attach_existing_owner=True, owner_confirmation_token='x:y')
        self.assertEqual(forged.data['code'], code)
        self.assertEqual(_snapshot(user), before)
        self.assertFalse(Business.objects.filter(default_service='reception').exists())
        return response

    def test_inactive_and_suspended_accounts_are_rejected_and_never_reactivated(self):
        inactive, _ = _existing_owner(is_active=False)
        self._assert_rejected(inactive, code='inactive_owner_account')
        suspended, _ = _existing_owner()
        AccountProfile.objects.filter(user=suspended).update(account_status=AccountProfile.AccountStatus.SUSPENDED)
        self._assert_rejected(suspended, code='inactive_owner_account')

    def test_superusers_staff_and_platform_personnel_are_rejected(self):
        superuser, _ = _existing_owner(is_superuser=True)
        staff, _ = _existing_owner(is_staff=True)
        platform, _ = _existing_owner()
        AccountProfile.objects.filter(user=platform).update(is_platform_staff=True, internal_role='support_agent')
        stale_role, _ = _existing_owner()
        AccountProfile.objects.filter(user=stale_role).update(internal_role='operations')
        for user in (superuser, staff, platform, stale_role, self.admin):
            with self.subTest(user=user.username):
                response = self._assert_rejected(user)
                self.assertNotIn('staff', response.data['detail'].lower())  # generic, no private role

    def test_employee_of_another_business_is_rejected(self):
        employee = User.objects.create_user(username=f'emp-{uuid.uuid4().hex[:6]}@example.test',
                                            email=f'emp-{uuid.uuid4().hex[:6]}@example.test')
        shop = Business.objects.create(name='Ajeno', slug=f'ajeno-{uuid.uuid4().hex[:8]}', status='active')
        Membership.objects.create(user=User.objects.create_user(username=f'jefe-{uuid.uuid4().hex[:6]}'),
                                  business=shop, role='owner')
        _employee_membership(employee, shop, 'cashier')
        self._assert_rejected(employee)

    def test_employee_of_a_branch_is_rejected_by_the_family_owner(self):
        hq = Business.objects.create(name='Casa', slug=f'casa-{uuid.uuid4().hex[:8]}', status='active')
        branch = Business.objects.create(name='Suc', slug=f'suc-{uuid.uuid4().hex[:8]}', parent=hq, status='active')
        Membership.objects.create(user=User.objects.create_user(username=f'jefe-{uuid.uuid4().hex[:6]}'),
                                  business=hq, role='owner')
        employee, _ = _existing_owner()  # owns its own business too
        _employee_membership(employee, branch, 'manager', status=Membership.Status.SUSPENDED)
        self._assert_rejected(employee)

    def test_co_owner_whose_partner_could_reset_the_password_is_rejected(self):
        user, shared = _existing_owner()
        Membership.objects.create(user=User.objects.create_user(username=f'socio-{uuid.uuid4().hex[:6]}'),
                                  business=shared, role='owner')
        self._assert_rejected(user)

    def test_account_linked_to_an_operational_employee_is_rejected(self):
        user, biz = _existing_owner()
        EmployeeProfile.objects.create(business=biz, linked_user=user, first_name='E', last_name='P',
                                       employee_code='E1', role_type='cashier', login_code_hash='x')
        self._assert_rejected(user)

    def test_account_without_profile_is_rejected(self):
        user, _ = _existing_owner()
        AccountProfile.objects.filter(user=user).delete()
        response = self.provision(owner_email=user.email)
        self.assertEqual((response.status_code, response.data['code']), (409, NOT_ELIGIBLE))
        self.assertFalse(AccountProfile.objects.filter(user=user).exists())

    def test_ambiguous_email_is_rejected(self):
        User.objects.create_user(username='dup-a', email='Dup@Example.test')
        User.objects.create_user(username='dup-b', email='dup@example.test')
        response = self.provision(owner_email='dup@example.test')
        self.assertEqual((response.status_code, response.data['code']), (409, 'ambiguous_owner_email'))
        self.assertNotIn('confirmation', response.data)

    def test_only_superadmin_platform_staff_can_confirm(self):
        user, _ = _existing_owner()
        token = self.provision(owner_email=user.email).data['confirmation']['token']
        for role in ('operations', 'support_agent', 'content_admin'):
            client = APIClient()
            client.force_authenticate(user=_staff(role))
            with self.subTest(role=role):
                response = client.post(CLIENTS_URL, self.payload(owner_email=user.email, attach_existing_owner=True,
                                                                 owner_confirmation_token=token), format='json')
                self.assertEqual(response.status_code, 403)
        owner_client = APIClient()
        owner_client.force_authenticate(user=user)
        self.assertEqual(owner_client.post(CLIENTS_URL, self.payload(owner_email=user.email), format='json').status_code, 403)
        self.assertFalse(Business.objects.filter(default_service='reception').exists())


class AuditAtomicityTests(_OwnerBase):

    def _kwargs(self, **overrides):
        payload = self.payload(**overrides)
        return {**payload, 'complimentary_start': self.starts_at, 'complimentary_end': self.ends_at,
                'granted_by': self.admin}

    def _failing_on(self, action):
        def side_effect(**kwargs):
            if kwargs['action'] == action:
                raise RuntimeError('audit down')
            return real_record(**kwargs)
        return patch('apps.accounts.admin_client_provisioning_service.record_platform_action', side_effect=side_effect)

    def test_audit_failure_rolls_back_a_reused_owner_alta_and_keeps_the_account_intact(self):
        user, _ = _existing_owner()
        before = _snapshot(user)
        users = User.objects.count()
        for action in ('ADMIN_CLIENT_CREATED', 'ADMIN_OWNER_PREAUTHORIZED'):
            with self.subTest(action=action), self._failing_on(action), self.assertRaises(RuntimeError):
                call_confirming_owner(provision_admin_client,
                                      **self._kwargs(owner_email=user.email, usage_tier='reception_custom',
                                                     custom_included_sessions=40))
        self.assertEqual(_snapshot(user), before)
        self.assertEqual(User.objects.count(), users)
        self.assertFalse(Business.objects.filter(default_service='reception').exists())
        self.assertFalse(SubscriptionV2.objects.filter(service_type='reception').exists())
        self.assertFalse(ReceptionAIUsagePolicy.objects.exists())
        self.assertFalse(AccessAuditLog.objects.filter(action__in=['ADMIN_CLIENT_CREATED',
                                                                    'ADMIN_COMPLIMENTARY_ACCESS_GRANTED']).exists())

    def test_audit_failure_rolls_back_a_new_owner_alta_including_the_account(self):
        email = f'nuevo-{uuid.uuid4().hex[:6]}@example.test'
        with self._failing_on('ADMIN_OWNER_PREAUTHORIZED'), self.assertRaises(RuntimeError):
            provision_admin_client(**self._kwargs(owner_email=email))
        self.assertFalse(User.objects.filter(email__iexact=email).exists())
        self.assertFalse(Business.objects.filter(default_service='reception').exists())

    def test_audit_failure_over_http_is_a_500_with_nothing_persisted(self):
        user, _ = _existing_owner()
        prompt = self.provision(owner_email=user.email)
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(user=self.admin)
        with self._failing_on('ADMIN_CLIENT_CREATED'):
            response = client.post(CLIENTS_URL, self.payload(
                owner_email=user.email, attach_existing_owner=True,
                owner_confirmation_token=prompt.data['confirmation']['token']), format='json')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(Membership.objects.filter(user=user).count(), 1)
        self.assertFalse(Business.objects.filter(default_service='reception').exists())

    def test_exactly_one_mandatory_event_of_each_kind(self):
        response = self.provision()
        bid = response.data['business_id']
        counts = {a: AccessAuditLog.objects.filter(action=a, business_id=bid).count()
                  for a in ('ADMIN_CLIENT_CREATED', 'ADMIN_OWNER_PREAUTHORIZED', 'ADMIN_COMPLIMENTARY_ACCESS_GRANTED')}
        self.assertEqual(counts, dict.fromkeys(counts, 1))


class PreauthorizedLoginWithReusedOwnerTests(_OwnerBase):

    def test_reused_owner_logs_in_to_the_new_business_and_keeps_the_old_one(self):
        user, previous = _existing_owner()
        response = self.confirm(self.provision(owner_email=user.email), owner_email=user.email)
        new_id = response.data['business_id']
        with self.settings(GOOGLE_OAUTH_CLIENT_ID='test-client-id.apps.googleusercontent.com',
                           REST_FRAMEWORK=_DRF_OVERRIDE), \
                patch('apps.accounts.google_oauth_service.GoogleOAuthService.verify_token') as verify:
            verify.return_value = _google_success(email=user.email, sub='sub-02f4-reused')
            to_new = APIClient().post(PREAUTH_URL, {'credential': 't', 'business_id': new_id})
            to_old = APIClient().post(PREAUTH_URL, {'credential': 't', 'business_id': previous.pk})
            no_link = APIClient().post(PREAUTH_URL, {'credential': 't'})
        self.assertEqual((to_new.status_code, to_new.cookies['bid'].value), (200, str(new_id)))
        self.assertEqual((to_old.status_code, to_old.cookies['bid'].value), (200, str(previous.pk)))
        self.assertEqual((no_link.status_code, no_link.data['code']), (400, 'google_preauthorized_business_required'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('OriginalPass123!'))


class ConcurrentSameEmailTests(TransactionTestCase):
    """Two simultaneous altas for the same NEW email never create two accounts."""

    available_apps = list(settings.INSTALLED_APPS)

    def setUp(self):
        self.admin = _staff()
        self.plan = _ensure_plan()
        self.starts_at = timezone.now().replace(microsecond=0)
        self.ends_at = self.starts_at + timedelta(days=180)

    def test_second_alta_waits_and_then_asks_for_confirmation(self):
        email = f'carrera-{uuid.uuid4().hex[:6]}@example.test'
        barrier = threading.Barrier(2)
        outcomes = []

        def worker(n):
            try:
                barrier.wait(timeout=10)
                try:
                    result = provision_admin_client(
                        business_name=f'Carrera {n}', business_slug=f'carrera-{n}-{uuid.uuid4().hex[:6]}',
                        service_type='gestion', country='AR', currency='ARS', owner_email=email,
                        plan_code=self.plan.code, complimentary_start=self.starts_at,
                        complimentary_end=self.ends_at, granted_by=self.admin, grant_reason='carrera',
                    )
                    outcomes.append(('created', result.owner_created))
                except ExistingOwnerRequiresConfirmationError:
                    outcomes.append(('confirm', None))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(n,)) for n in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertEqual(sorted(outcomes), [('confirm', None), ('created', True)])
        self.assertEqual(User.objects.filter(email__iexact=email).count(), 1)
        self.assertEqual(Membership.objects.filter(user__email__iexact=email).count(), 1)

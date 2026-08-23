"""HTTP contract for ADMIN-CLIENTES 03A client provisioning."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.admin_client_provisioning_service import (
    ActiveComplimentarySubscriptionConflictError,
    ComplimentaryGrantFailedError,
    ComplimentaryPlanNotAvailableError,
    ComplimentaryPlanServiceMismatchError,
    DuplicateBusinessSlugError,
    InactiveOwnerAccountError,
    InvalidBusinessCountryError,
    InvalidBusinessCurrencyError,
    InvalidBusinessNameError,
    InvalidBusinessSlugError,
    InvalidComplimentaryGrantReasonError,
    InvalidComplimentaryPeriodError,
    InvalidComplimentaryServiceTypeError,
    InvalidOwnerEmailError,
    MultipleOwnerAccountsError,
    UnauthorizedProvisioningActorError,
)
from apps.accounts.models import AccessAuditLog, AccountProfile, Membership
from apps.billing.complimentary_access_service import ComplimentaryAccessError
from apps.billing.models import Plan, Subscription, SubscriptionV2
from apps.business.models import Business


User = get_user_model()
URL = '/api/v1/platform-admin/clients/'


def _make_user(*, role=None, platform_staff=False, active=True, email=None):
    email = email or f'user-{uuid.uuid4().hex}@example.com'
    user = User.objects.create_user(
        username=f'username-{uuid.uuid4().hex}',
        email=email,
        password='SecurePass123!',
        is_active=active,
    )
    profile = user.account_profile
    profile.is_platform_staff = platform_staff
    profile.internal_role = role
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    user.refresh_from_db()
    return user


class AdminClientEndpointTestBase(TestCase):
    def setUp(self):
        self.superadmin = _make_user(role='superadmin', platform_staff=True)
        self.operations = _make_user(role='operations', platform_staff=True)
        self.plan, _ = Plan.objects.get_or_create(
            code='gestion_pro',
            defaults={
                'name': 'Gestión Pro',
                'price': Decimal('50000.00'),
                'interval': 'monthly',
                'currency': 'ARS',
                'frequency': 1,
                'frequency_type': 'months',
                'plan_status': 'active',
            },
        )
        self.starts_at = timezone.now().replace(microsecond=0)
        self.ends_at = self.starts_at + timedelta(days=180)

    def payload(self, **overrides):
        data = {
            'business_name': 'Comercio Ejemplo',
            'business_slug': f'comercio-{uuid.uuid4().hex[:10]}',
            'service_type': 'gestion',
            'country': 'AR',
            'currency': 'ARS',
            'owner_email': f'owner-{uuid.uuid4().hex[:10]}@empresa.com',
            'plan_code': self.plan.code,
            'complimentary_start': self.starts_at.isoformat(),
            'complimentary_end': self.ends_at.isoformat(),
            'grant_reason': 'Alta administrativa por cortesía comercial',
        }
        data.update(overrides)
        return data

    def post(self, payload=None, *, user=None):
        client = APIClient()
        client.force_authenticate(user=user or self.superadmin)
        return client.post(URL, payload or self.payload(), format='json')


class AdminClientProvisioningIntegrationTests(AdminClientEndpointTestBase):
    def test_01_superadmin_creates_client_with_new_owner(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['owner']['created'])
        self.assertEqual(Business.objects.count(), 1)
        self.assertEqual(Membership.objects.count(), 1)
        self.assertEqual(SubscriptionV2.objects.count(), 1)

    def test_02_superadmin_reuses_existing_owner(self):
        email = 'owner.workspace@empresa.example'
        owner = _make_user(email=email)

        response = self.post(self.payload(owner_email=email.upper()))

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['owner']['created'])
        self.assertEqual(response.data['owner']['id'], owner.id)
        self.assertEqual(User.objects.filter(email__iexact=email).count(), 1)

    def test_03_response_has_exact_resource_structure(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.data), {
            'business', 'owner', 'membership', 'subscription',
            'owner_email', 'owner_user_id', 'business_id', 'membership_id',
            'login_url',
        })
        self.assertEqual(set(response.data['business']), {
            'id', 'name', 'slug', 'status', 'service_type', 'country', 'currency',
        })
        self.assertEqual(set(response.data['owner']), {'id', 'email', 'created'})
        self.assertEqual(set(response.data['membership']), {'id', 'role', 'status'})
        self.assertEqual(set(response.data['subscription']), {
            'id', 'plan_code', 'provider', 'status',
            'current_period_start', 'current_period_end',
        })
        self.assertEqual(response.data['business']['status'], 'trialing')
        self.assertEqual(response.data['membership']['role'], 'owner')
        self.assertEqual(response.data['membership']['status'], 'active')
        self.assertEqual(response.data['subscription']['provider'], 'manual')
        self.assertEqual(response.data['subscription']['status'], 'trialing')

    def test_04_response_excludes_sensitive_and_fictitious_fields(self):
        response = self.post()
        rendered = json.dumps(response.data, default=str).lower()

        for forbidden in ('password', 'token', 'google', 'provider_sub_id'):
            self.assertNotIn(forbidden, rendered)

    def test_05_unauthenticated_user_is_rejected(self):
        response = APIClient().post(URL, self.payload(), format='json')

        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(Business.objects.count(), 0)

    def test_06_normal_user_is_rejected(self):
        response = self.post(user=_make_user())

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Business.objects.count(), 0)

    def test_07_operations_is_rejected_for_post(self):
        response = self.post(user=self.operations)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Business.objects.count(), 0)

    def test_08_support_agent_is_rejected_for_post(self):
        support = _make_user(role='support_agent', platform_staff=True)

        response = self.post(user=support)

        self.assertEqual(response.status_code, 403)

    def test_09_content_admin_is_rejected_for_post(self):
        content = _make_user(role='content_admin', platform_staff=True)

        response = self.post(user=content)

        self.assertEqual(response.status_code, 403)

    def test_10_superadmin_is_authorized_for_post(self):
        self.assertEqual(self.post().status_code, 201)

    def test_11_operations_keeps_get_access(self):
        client = APIClient()
        client.force_authenticate(user=self.operations)

        response = client.get(URL)

        self.assertEqual(response.status_code, 200)

    def test_12_get_list_contract_is_unchanged(self):
        self.post(self.payload(business_slug='cliente-listado'))
        client = APIClient()
        client.force_authenticate(user=self.operations)

        response = client.get(URL)

        self.assertEqual(set(response.data), {
            'results', 'total', 'page', 'page_size', 'total_pages',
        })
        self.assertEqual(response.data['page'], 1)
        self.assertEqual(response.data['page_size'], 25)
        self.assertEqual(set(response.data['results'][0]), {
            'id', 'name', 'slug', 'email', 'status', 'plan',
            'subscription_status', 'created_at', 'next_renewal',
            'user_count', 'branch_count', 'risk_badges', 'service_type',
        })

    def test_13_missing_required_field_returns_400(self):
        payload = self.payload()
        payload.pop('business_name')

        response = self.post(payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn('business_name', response.data)
        self.assertEqual(Business.objects.count(), 0)

    def test_14_unknown_field_returns_400(self):
        response = self.post(self.payload(password='ForbiddenPass123!'))

        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data)
        self.assertEqual(Business.objects.count(), 0)

    def test_15_invalid_email_returns_400(self):
        response = self.post(self.payload(owner_email='not-an-email'))

        self.assertEqual(response.status_code, 400)
        self.assertIn('owner_email', response.data)

    def test_16_invalid_period_returns_400(self):
        response = self.post(self.payload(
            complimentary_start=self.ends_at.isoformat(),
            complimentary_end=self.starts_at.isoformat(),
        ))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'invalid_complimentary_period')
        self.assertEqual(Business.objects.count(), 0)

    def test_17_blank_grant_reason_returns_400(self):
        response = self.post(self.payload(grant_reason='   '))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'invalid_complimentary_grant_reason')

    def test_18_invalid_service_returns_400(self):
        response = self.post(self.payload(service_type='not-a-service'))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'invalid_complimentary_service_type')

    def test_19_incompatible_plan_returns_400(self):
        response = self.post(self.payload(service_type='menu_qr'))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'complimentary_plan_service_mismatch')
        self.assertEqual(Business.objects.count(), 0)

    def test_20_duplicate_slug_returns_409(self):
        Business.objects.create(name='Existente', slug='slug-ocupado')

        response = self.post(self.payload(business_slug='slug-ocupado'))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data, {
            'code': 'business_slug_conflict',
            'detail': 'El slug ya está utilizado.',
            'field': 'business_slug',
        })
        self.assertEqual(Business.objects.filter(slug='slug-ocupado').count(), 1)

    def test_21_inactive_existing_owner_returns_409(self):
        owner = _make_user(active=False, email='inactive-owner@empresa.com')

        response = self.post(self.payload(owner_email=owner.email))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'inactive_owner_account')
        self.assertEqual(Business.objects.count(), 0)

    def test_22_case_insensitive_ambiguous_email_returns_409(self):
        _make_user(email='ambiguous@empresa.com')
        _make_user(email='AMBIGUOUS@EMPRESA.COM')

        response = self.post(self.payload(owner_email='Ambiguous@Empresa.com'))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'ambiguous_owner_email')
        self.assertEqual(Business.objects.count(), 0)

    def test_23_unclassified_complimentary_failure_returns_422(self):
        with patch(
            'apps.accounts.admin_client_provisioning_service.grant_complimentary_access',
            side_effect=ComplimentaryAccessError('internal domain detail'),
        ):
            response = self.post()

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data, {
            'code': 'complimentary_grant_failed',
            'detail': 'No se pudo otorgar el acceso bonificado.',
            'field': None,
        })
        self.assertNotIn('internal domain detail', json.dumps(response.data))
        self.assertEqual(Business.objects.count(), 0)

    def test_24_resubmission_does_not_create_duplicate_rows_or_audits(self):
        payload = self.payload(business_slug='envio-repetido')

        first = self.post(payload)
        counts_after_first = (
            Business.objects.count(), Membership.objects.count(),
            SubscriptionV2.objects.count(), AccessAuditLog.objects.count(),
        )
        second = self.post(payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.data['code'], 'business_slug_conflict')
        self.assertEqual(counts_after_first, (
            Business.objects.count(), Membership.objects.count(),
            SubscriptionV2.objects.count(), AccessAuditLog.objects.count(),
        ))

    def test_25_domain_errors_leave_zero_partial_rows(self):
        payload = self.payload(
            business_slug='rollback-http',
            owner_email='rollback-http@empresa.com',
            plan_code='missing-plan',
        )

        response = self.post(payload)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Business.objects.filter(slug='rollback-http').exists())
        self.assertFalse(User.objects.filter(email='rollback-http@empresa.com').exists())
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(SubscriptionV2.objects.count(), 0)
        self.assertEqual(AccessAuditLog.objects.count(), 0)

    def test_26_provisioning_does_not_call_mercado_pago(self):
        with patch(
            'apps.billing.mp_service.MercadoPagoService',
            side_effect=AssertionError('Mercado Pago must not be called'),
        ) as mercado_pago:
            response = self.post()

        self.assertEqual(response.status_code, 201)
        mercado_pago.assert_not_called()

    def test_27_provisioning_does_not_create_legacy_subscription(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Subscription.objects.count(), 0)
        self.assertEqual(SubscriptionV2.objects.count(), 1)

    def test_28_provisioning_sends_no_email_or_async_task(self):
        with patch('django.core.mail.send_mail') as send_mail, patch(
            'apps.accounts.tasks.send_verification_email_task.delay',
        ) as verification_task:
            response = self.post()

        self.assertEqual(response.status_code, 201)
        send_mail.assert_not_called()
        verification_task.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    def test_29_audits_and_membership_keep_superadmin_as_actor(self):
        response = self.post()
        business_id = response.data['business']['id']

        actor_ids = set(AccessAuditLog.objects.filter(
            business_id=business_id,
        ).values_list('actor_id', flat=True))
        membership = Membership.objects.get(business_id=business_id)

        self.assertEqual(actor_ids, {self.superadmin.id})
        self.assertEqual(membership.created_by_user_id, self.superadmin.id)

    def test_30_new_owner_has_unusable_password(self):
        response = self.post()
        owner = User.objects.get(pk=response.data['owner']['id'])

        self.assertFalse(owner.has_usable_password())

    def test_31_new_owner_has_no_platform_or_google_identity(self):
        response = self.post()
        owner = User.objects.get(pk=response.data['owner']['id'])
        profile = AccountProfile.objects.get(user=owner)

        self.assertFalse(owner.is_staff)
        self.assertFalse(owner.is_superuser)
        self.assertFalse(profile.is_platform_staff)
        self.assertIsNone(profile.internal_role)
        self.assertFalse(profile.email_verified)
        self.assertIsNone(profile.google_sub)


class AdminClientHTTPMappingUnitTests(AdminClientEndpointTestBase):
    def fake_result(self):
        return SimpleNamespace(
            business=SimpleNamespace(
                id=10, name='Cliente', slug='cliente', status='trialing',
                service_type='gestion', country='AR', currency='ARS',
            ),
            owner_user=SimpleNamespace(id=20, email='owner@empresa.com'),
            owner_created=True,
            membership=SimpleNamespace(id=30, role='owner', status='active'),
            subscription=SimpleNamespace(
                id=uuid.uuid4(), plan_code='gestion_pro', provider='manual',
                status='trialing', current_period_start=self.starts_at,
                current_period_end=self.ends_at,
            ),
        )

    @patch('apps.accounts.platform_admin_clients_views.provision_admin_client')
    def test_32_calls_provisioning_once_with_validated_data_and_actor(self, mocked):
        mocked.return_value = self.fake_result()
        payload = self.payload()

        response = self.post(payload)

        self.assertEqual(response.status_code, 201)
        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(set(kwargs), set(payload) | {'granted_by'})
        self.assertEqual(kwargs['granted_by'], self.superadmin)
        self.assertEqual(kwargs['complimentary_start'], self.starts_at)
        self.assertEqual(kwargs['complimentary_end'], self.ends_at)

    @patch('apps.accounts.platform_admin_clients_views.provision_admin_client')
    def test_33_maps_every_public_domain_exception(self, mocked):
        cases = [
            (UnauthorizedProvisioningActorError, 403, 'unauthorized_provisioning_actor', None),
            (InvalidOwnerEmailError, 400, 'invalid_owner_email', 'owner_email'),
            (MultipleOwnerAccountsError, 409, 'ambiguous_owner_email', 'owner_email'),
            (InactiveOwnerAccountError, 409, 'inactive_owner_account', 'owner_email'),
            (InvalidBusinessSlugError, 400, 'invalid_business_slug', 'business_slug'),
            (DuplicateBusinessSlugError, 409, 'business_slug_conflict', 'business_slug'),
            (InvalidBusinessNameError, 400, 'invalid_business_name', 'business_name'),
            (InvalidBusinessCountryError, 400, 'invalid_business_country', 'country'),
            (InvalidBusinessCurrencyError, 400, 'invalid_business_currency', 'currency'),
            (InvalidComplimentaryPeriodError, 400, 'invalid_complimentary_period', 'complimentary_end'),
            (ComplimentaryPlanNotAvailableError, 400, 'complimentary_plan_not_available', 'plan_code'),
            (ComplimentaryPlanServiceMismatchError, 400, 'complimentary_plan_service_mismatch', 'plan_code'),
            (ActiveComplimentarySubscriptionConflictError, 409, 'active_complimentary_subscription_conflict', 'service_type'),
            (InvalidComplimentaryGrantReasonError, 400, 'invalid_complimentary_grant_reason', 'grant_reason'),
            (InvalidComplimentaryServiceTypeError, 400, 'invalid_complimentary_service_type', 'service_type'),
            (ComplimentaryGrantFailedError, 422, 'complimentary_grant_failed', None),
        ]

        for exception_type, expected_status, code, field in cases:
            with self.subTest(exception_type=exception_type.__name__):
                mocked.side_effect = exception_type('private service detail')
                response = self.post()

                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.data['code'], code)
                self.assertEqual(response.data['field'], field)
                self.assertNotIn('private service detail', response.data['detail'])

    @patch('apps.accounts.platform_admin_clients_views.provision_admin_client')
    def test_34_unexpected_technical_errors_are_not_converted(self, mocked):
        mocked.side_effect = RuntimeError('unexpected technical failure')

        with self.assertRaises(RuntimeError):
            self.post()

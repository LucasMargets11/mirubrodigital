"""ADMIN-CLIENTES 04E — access-delivery fields in the 03A response."""
from __future__ import annotations

import json
import uuid
from urllib.parse import urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings

from apps.accounts.models import Membership
from apps.billing.models import SubscriptionV2
from apps.business.models import Business

from .test_admin_clientes_03a_endpoint import (
    AdminClientEndpointTestBase,
    _make_user,
)


User = get_user_model()


class AdminClientAccessDeliveryContractTests(AdminClientEndpointTestBase):
    @override_settings(FRONTEND_URL='https://frontend.example.com')
    def test_01_delivery_fields_use_the_persisted_resources(self):
        raw_email = f'OWNER-{uuid.uuid4().hex[:8]}@EMPRESA.EXAMPLE'

        response = self.post(self.payload(owner_email=raw_email))

        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.data), {
            'owner_email', 'owner_user_id', 'business_id', 'membership_id',
            'login_url', 'business', 'owner', 'membership', 'subscription',
        })

        owner = User.objects.get(pk=response.data['owner_user_id'])
        business = Business.objects.get(pk=response.data['business_id'])
        membership = Membership.objects.get(
            pk=response.data['membership_id'],
            user=owner,
            business=business,
            role='owner',
        )
        subscription = SubscriptionV2.objects.get(
            pk=response.data['subscription']['id'],
            business=business,
        )

        self.assertEqual(owner.email, raw_email.lower())
        self.assertEqual(response.data['owner_email'], owner.email)
        self.assertEqual(response.data['owner_user_id'], owner.pk)
        self.assertEqual(response.data['business_id'], business.pk)
        self.assertEqual(response.data['membership_id'], membership.pk)

        self.assertEqual(response.data['business']['id'], business.pk)
        self.assertEqual(response.data['owner']['id'], owner.pk)
        self.assertEqual(response.data['owner']['email'], owner.email)
        self.assertEqual(response.data['membership']['id'], membership.pk)
        self.assertEqual(response.data['subscription']['id'], str(subscription.pk))

    @override_settings(FRONTEND_URL='https://frontend.example.com')
    def test_02_existing_owner_keeps_its_id_email_and_effective_membership(self):
        persisted_email = f'Canonical.Owner-{uuid.uuid4().hex[:8]}@Empresa.Example'
        owner = _make_user(email=persisted_email)

        response = self.post(self.payload(owner_email=owner.email.swapcase()))

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['owner']['created'])
        self.assertEqual(response.data['owner_user_id'], owner.pk)
        self.assertEqual(response.data['owner_email'], owner.email)
        membership = Membership.objects.get(
            business_id=response.data['business_id'],
            user=owner,
            role='owner',
            status=Membership.Status.ACTIVE,
        )
        self.assertEqual(response.data['membership_id'], membership.pk)

    @override_settings(FRONTEND_URL='https://www.mirubro.com')
    def test_03_login_url_uses_frontend_url_without_trailing_slash(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data['login_url'],
            'https://www.mirubro.com/entrar/cliente',
        )
        parsed = urlsplit(response.data['login_url'])
        self.assertEqual((parsed.query, parsed.fragment), ('', ''))
        self.assertNotIn(response.data['owner_email'], response.data['login_url'])
        for resource_id in (
            response.data['owner_user_id'],
            response.data['business_id'],
            response.data['membership_id'],
            response.data['subscription']['id'],
        ):
            self.assertNotIn(str(resource_id), response.data['login_url'])

    @override_settings(FRONTEND_URL='https://www.mirubro.com/')
    def test_04_login_url_normalizes_a_trailing_slash(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data['login_url'],
            'https://www.mirubro.com/entrar/cliente',
        )

    @override_settings(FRONTEND_URL='https://frontend.example.com')
    @patch(
        'apps.billing.mp_service.MercadoPagoService',
        side_effect=AssertionError('Mercado Pago must not be called'),
    )
    @patch(
        'apps.accounts.google_oauth_service.GoogleOAuthService.verify_token',
        side_effect=AssertionError('Google OAuth must not be called'),
    )
    @patch('apps.accounts.tasks.send_verification_email_task.delay')
    @patch('django.core.mail.send_mail')
    def test_05_response_has_no_secrets_and_provisioning_has_no_external_effects(
        self,
        send_mail,
        verification_task,
        google_verify,
        mercado_pago,
    ):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        rendered = json.dumps(response.data, default=str).lower()
        for forbidden in (
            'password', 'jwt', 'token', 'google', 'google_sub', 'credential',
        ):
            self.assertNotIn(forbidden, rendered)
        send_mail.assert_not_called()
        verification_task.assert_not_called()
        google_verify.assert_not_called()
        mercado_pago.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(FRONTEND_URL='https://frontend.example.com')
    def test_06_previous_resource_fields_remain_intact(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
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

    @override_settings(FRONTEND_URL='https://frontend.example.com')
    def test_07_existing_error_contract_is_exactly_unchanged(self):
        payload = self.payload(business_slug='04e-duplicate-contract')
        first_response = self.post(payload)

        response = self.post(payload)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data, {
            'code': 'business_slug_conflict',
            'detail': 'El slug ya está utilizado.',
            'field': 'business_slug',
        })

    @override_settings(FRONTEND_URL='https://frontend.example.com')
    def test_08_structural_field_error_contract_is_exactly_unchanged(self):
        payload = self.payload()
        payload.pop('business_name')

        response = self.post(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {
            'business_name': ['Este campo es requerido.'],
        })

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.billing import canonical_pricing
from apps.billing.models import AppointmentsCheckout, SubscriptionV2
from apps.billing.views import PublicAppointmentsCheckoutView, PublicAppointmentsQuoteView
from apps.accounts.models import Membership
from apps.business.models import Business, Subscription as LegacySubscription, SubscriptionAddon

User = get_user_model()


class PublicAppointmentsContractTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username='public-turnos-owner@test.invalid',
            email='public-turnos-owner@test.invalid',
            password='test-password',
        )
        self.business = Business.objects.create(name='Public Turnos Business')
        LegacySubscription.objects.create(
            business=self.business,
            plan='start',
            status='active',
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role='owner',
            status=Membership.Status.ACTIVE,
        )

    def request(self, view, payload, *, user=None, path=None, **headers):
        request = self.factory.post(
            path or '/api/v1/billing/appointments/quote/',
            payload,
            format='json',
            **headers,
        )
        if user is not None:
            force_authenticate(request, user=user)
        return view.as_view()(request)

    def quote(self, payload, **kwargs):
        return self.request(PublicAppointmentsQuoteView, payload, **kwargs)

    def checkout(self, payload, **kwargs):
        return self.request(
            PublicAppointmentsCheckoutView,
            payload,
            path='/api/v1/billing/appointments/checkout/',
            **kwargs,
        )

    def valid_payload(self, **overrides):
        return {
            'plan_code': 'appointments',
            'billing_cycle': 'monthly',
            **overrides,
        }

    def test_public_contract_requires_authentication_and_active_membership(self):
        anonymous = self.request(
            PublicAppointmentsQuoteView,
            self.valid_payload(),
        )
        no_membership_user = User.objects.create_user(
            username='public-turnos-no-membership@test.invalid',
            email='public-turnos-no-membership@test.invalid',
        )
        no_membership = self.quote(
            self.valid_payload(),
            user=no_membership_user,
        )

        self.assertIn(anonymous.status_code, (401, 403))
        self.assertEqual(no_membership.status_code, 403)
        self.assertEqual(no_membership.data['code'], 'business_membership_required')

    def test_owner_quote_uses_canonical_server_price_without_client_business_id(self):
        response = self.quote(self.valid_payload(), user=self.user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['base_amount'], 23000)
        self.assertEqual(response.data['total_amount'], 23000)
        self.assertEqual(response.data['currency'], 'ARS')

    def test_client_cannot_supply_tenant_price_or_provider_fields(self):
        forbidden_fields = (
            'business_id',
            'amount',
            'price',
            'total',
            'currency',
            'entitlements',
            'provider_id',
            'provider_preapproval_id',
            'provider_payment_id',
        )
        for field in forbidden_fields:
            with self.subTest(field=field):
                response = self.quote(
                    self.valid_payload(**{field: 'client-controlled'}),
                    user=self.user,
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data['detail'])

    def test_tenant_context_is_membership_scoped_and_query_parameters_do_not_select_it(self):
        other_business = Business.objects.create(name='Other Turnos Business')
        Membership.objects.create(
            user=self.user,
            business=other_business,
            role='owner',
            status=Membership.Status.ACTIVE,
        )

        ambiguous = self.quote(
            self.valid_payload(),
            user=self.user,
            path=f'/api/v1/billing/appointments/quote/?business_id={self.business.pk}',
        )
        selected = self.quote(
            self.valid_payload(),
            user=self.user,
            HTTP_X_BUSINESS_ID=str(other_business.pk),
        )
        foreign = User.objects.create_user(
            username='public-turnos-foreign@test.invalid',
            email='public-turnos-foreign@test.invalid',
        )
        Membership.objects.create(
            user=foreign,
            business=other_business,
            role='owner',
            status=Membership.Status.ACTIVE,
        )
        forced_foreign = self.quote(
            self.valid_payload(business_id=other_business.pk),
            user=foreign,
        )

        self.assertEqual(ambiguous.status_code, 403)
        self.assertEqual(ambiguous.data['code'], 'business_context_ambiguous')
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(forced_foreign.status_code, 400)
        self.assertIn('business_id', forced_foreign.data['detail'])

    def test_non_owner_membership_is_forbidden(self):
        staff_user = User.objects.create_user(
            username='public-turnos-staff@test.invalid',
            email='public-turnos-staff@test.invalid',
        )
        Membership.objects.create(
            user=staff_user,
            business=self.business,
            role='admin',
            status=Membership.Status.ACTIVE,
        )

        response = self.quote(self.valid_payload(), user=staff_user)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'owner_required')

    def test_public_checkout_requires_authentication_and_owner_membership(self):
        anonymous = self.request(
            PublicAppointmentsCheckoutView,
            self.valid_payload(),
            path='/api/v1/billing/appointments/checkout/',
        )
        staff_user = User.objects.create_user(
            username='public-turnos-checkout-staff@test.invalid',
            email='public-turnos-checkout-staff@test.invalid',
        )
        Membership.objects.create(
            user=staff_user,
            business=self.business,
            role='staff',
            status=Membership.Status.ACTIVE,
        )

        forbidden = self.checkout(self.valid_payload(), user=staff_user)

        self.assertIn(anonymous.status_code, (401, 403))
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.data['code'], 'owner_required')

    def test_invalid_plan_tier_automation_and_extra_values_are_rejected(self):
        invalid_payloads = (
            self.valid_payload(plan_code='custom'),
            self.valid_payload(plan_code='appointments', usage_tier='ai_300'),
            self.valid_payload(plan_code='appointments_ai'),
            self.valid_payload(plan_code='appointments_ai', usage_tier='unknown'),
            self.valid_payload(plan_code='appointments_ai', usage_tier='custom'),
            self.valid_payload(extra_professionals=-1),
            self.valid_payload(automations=2),
            self.valid_payload(automations_quantity=1),
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.quote(payload, user=self.user)
                if payload.get('usage_tier') == 'custom':
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.data['code'], 'manual_contract_required')
                else:
                    self.assertEqual(response.status_code, 400)

    def test_ai_quote_uses_tier_and_includes_automations_without_double_charge(self):
        response = self.quote(
            self.valid_payload(
                plan_code='appointments_ai',
                usage_tier='ai_1500',
                automations=True,
                extra_professionals=2,
            ),
            user=self.user,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['base_amount'], 275000)
        self.assertEqual(response.data['automations'], 'included')
        self.assertEqual(response.data['addons_amount'], 0)
        self.assertEqual(response.data['extras_amount'], 6000)
        self.assertEqual(response.data['total_amount'], 281000)

    def test_yearly_quote_uses_canonical_annual_price(self):
        response = self.quote(
            self.valid_payload(billing_cycle='yearly', extra_professionals=2),
            user=self.user,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['base_amount'], 220800)
        self.assertEqual(response.data['total_amount'], 278400)

    def test_inactive_checkout_is_deterministic_and_has_no_local_or_provider_side_effects(self):
        self.assertFalse(canonical_pricing.get_product('appointments')['is_active'])
        payload = self.valid_payload(
            plan_code='appointments_ai',
            usage_tier='ai_300',
        )

        with patch(
            'apps.billing.mp_service.MercadoPagoService.create_preapproval_plan'
        ) as provider:
            response = self.checkout(payload, user=self.user)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'product_not_active')
        self.assertEqual(AppointmentsCheckout.objects.count(), 0)
        self.assertEqual(SubscriptionV2.objects.count(), 0)
        self.assertEqual(SubscriptionAddon.objects.count(), 0)
        provider.assert_not_called()

    def test_checkout_validates_payload_before_inactive_product_gate(self):
        response = self.checkout(
            self.valid_payload(plan_code='appointments_ai'),
            user=self.user,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('usage_tier', response.data['detail'])
        self.assertEqual(AppointmentsCheckout.objects.count(), 0)

    def test_checkout_rejects_client_selected_business_before_side_effects(self):
        response = self.checkout(
            self.valid_payload(business_id=self.business.pk),
            user=self.user,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('business_id', response.data['detail'])
        self.assertEqual(AppointmentsCheckout.objects.count(), 0)

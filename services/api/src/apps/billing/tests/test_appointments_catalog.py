from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.billing.checkout_session_service import start_checkout
from apps.billing.models import Bundle, Module, Plan
from apps.billing.services import PricingService
from apps.billing.views import BillingViewSet, StartSubscriptionView


class AppointmentsCatalogTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def request_catalog(self, action, user=None, query=None):
        request = self.factory.get('/billing/', query or {})
        if user:
            force_authenticate(request, user=user)
        return BillingViewSet.as_view({'get': action})(request)

    def test_internal_catalog_is_staff_only_and_complete(self):
        for user in (None, SimpleNamespace(is_authenticated=True, is_staff=False)):
            response = self.request_catalog('appointments_catalog', user)
            self.assertIn(response.status_code, (401, 403))
        response = self.request_catalog(
            'appointments_catalog', SimpleNamespace(is_authenticated=True, is_staff=True),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['product']['is_active'])
        self.assertEqual([p['code'] for p in response.data['plans']], [
            'appointments', 'appointments_pro', 'appointments_ai',
        ])
        self.assertEqual(len(response.data['usage_tiers']), 4)
        self.assertEqual(response.data['addons'][0]['code'], 'appointments_automations')
        self.assertEqual(response.data['extras'][0]['quantity_min'], 0)

    def test_scoped_seed_is_idempotent_inactive_and_does_not_change_other_offers(self):
        other_plan = Plan.objects.create(
            code='gestion_start', name='Existing', price=36000, interval='monthly',
        )
        legacy = Bundle.objects.create(
            code='appointments_base', name='Legacy', vertical='appointments',
            pricing_mode='fixed_price', fixed_price_monthly=99,
        )
        other_bundle, _ = Bundle.objects.update_or_create(
            code='menu_qr_basico',
            defaults={
                'name': 'Existing menu', 'vertical': 'menu_qr',
                'pricing_mode': 'fixed_price', 'fixed_price_monthly': 18000,
            },
        )
        other_module = Module.objects.create(
            code='other_module', name='Existing module', vertical='commercial',
            category='operation', price_monthly=1234,
        )
        before = {
            'plan': Plan.objects.filter(pk=other_plan.pk).values().get(),
            'bundles': list(Bundle.objects.order_by('pk').values()),
            'module': Module.objects.filter(pk=other_module.pk).values().get(),
        }
        for _ in range(2):
            call_command('seed_appointments_catalog', stdout=StringIO())
        self.assertEqual(Plan.objects.filter(pk=other_plan.pk).values().get(), before['plan'])
        self.assertEqual(
            list(Bundle.objects.exclude(code__in=[
                'appointments', 'appointments_pro', 'appointments_ai',
            ]).order_by('pk').values()),
            before['bundles'],
        )
        self.assertEqual(Module.objects.filter(pk=other_module.pk).values().get(), before['module'])
        self.assertEqual(Plan.objects.filter(code__in=['appointments', 'appointments_pro']).count(), 2)
        self.assertFalse(Plan.objects.filter(code__startswith='appointments', plan_status='active').exists())
        self.assertFalse(Plan.objects.filter(code='appointments_ai').exists())
        self.assertEqual(Bundle.objects.filter(code__in=[
            'appointments', 'appointments_pro', 'appointments_ai',
        ], is_active=False).count(), 3)
        self.assertEqual(Module.objects.filter(code='appointments_automations', is_active=False).count(), 1)
        self.assertFalse(Module.objects.filter(code='appointments_extra_professional').exists())
        self.assertEqual(
            list(Bundle.objects.get(code='appointments_ai').modules.values_list('code', flat=True)),
            ['appointments_automations'],
        )

    def test_public_catalog_hides_even_accidentally_active_turnos_rows(self):
        for vertical, code, price in (
            ('appointments', 'appointments', 23000),
            ('commercial', 'gestion_start', 36000),
            ('menu_qr', 'menu_qr_basico', 18000),
            ('qr_reviews', 'qr_reviews_base', 15000),
        ):
            Bundle.objects.update_or_create(
                code=code,
                defaults={
                    'name': code, 'vertical': vertical, 'pricing_mode': 'fixed_price',
                    'fixed_price_monthly': price, 'is_active': True,
                },
            )
            Module.objects.update_or_create(
                code=code,
                defaults={
                    'name': code, 'vertical': vertical, 'category': 'operation',
                    'price_monthly': price, 'is_active': True,
                },
            )
        products = self.request_catalog('products')
        self.assertEqual(products.status_code, 200)
        self.assertEqual([p['code'] for p in products.data], ['gestion', 'menu_qr', 'qr_reviews'])
        for action in ('modules', 'bundles'):
            response = self.request_catalog(action)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('appointments', [row['vertical'] for row in response.data])
            self.assertEqual(self.request_catalog(action, query={'vertical': 'appointments'}).data, [])
        self.assertEqual(self.request_catalog('bundles', query={'checkout': 'true', 'vertical': 'appointments'}).data, [])

    def test_seed_disables_an_existing_ia_checkout_row_without_inventing_a_price(self):
        existing = Plan.objects.create(
            code='appointments_ai', name='Existing IA', price=12345,
            interval='monthly', plan_status='active',
        )
        call_command('seed_appointments_catalog', stdout=StringIO())
        existing.refresh_from_db()
        self.assertEqual(existing.plan_status, 'inactive')
        self.assertEqual(existing.price, 12345)

    def test_public_quote_rejects_unpublished_bundles_and_modules(self):
        Bundle.objects.create(
            code='appointments_pro', name='Pro', vertical='appointments',
            pricing_mode='fixed_price', fixed_price_monthly=28000, is_active=True,
        )
        Module.objects.create(
            code='appointments_automations', name='Automations', vertical='appointments',
            category='operation', price_monthly=8500, is_active=True,
        )
        for kwargs in (
            {'vertical': 'appointments', 'plan_type': 'custom'},
            {'vertical': 'commercial', 'plan_type': 'bundle', 'bundle_code': 'appointments_pro'},
            {'vertical': 'commercial', 'plan_type': 'custom',
             'selected_module_codes': ['appointments_automations']},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaisesMessage(ValueError, 'not available'):
                PricingService.calculate_quote(billing_period='monthly', **kwargs)

    def test_checkout_is_blocked_before_any_database_or_provider_work(self):
        with patch('apps.billing.checkout_session_service.Plan.objects.get') as lookup:
            for code in ('appointments', 'appointments_pro', 'appointments_ai'):
                with self.subTest(code=code), self.assertRaisesMessage(ValueError, 'not available'):
                    start_checkout(user=None, tenant=None, plan_code=code)
            lookup.assert_not_called()
        request = self.factory.post('/billing/start-subscription', {
            'email': 'catalog@example.test', 'password': 'test-only',
            'business_name': 'Test', 'plan_code': 'appointments',
        })
        with patch('apps.billing.views.User.objects.filter') as lookup:
            response = StartSubscriptionView.as_view()(request)
            self.assertEqual(response.status_code, 400)
            lookup.assert_not_called()

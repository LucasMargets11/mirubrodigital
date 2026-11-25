"""PROD-02B — Recepcionista IA como servicio propio (`reception`).

Cubre: catálogo no vendible, validación de plan/tier, aislamiento de la
resolución de suscripciones (sin fallback cruzado con Gestión ni Turnos),
entitlements `reception.*` resueltos desde su propia suscripción, contexto de
negocio, cupo de usuarios secundarios, checkout público y provisioning
bloqueados, y compatibilidad de Turnos IA / Turnos Base legacy.
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.billing import canonical_pricing
from apps.billing.appointments_plans import validate_usage_tier
from apps.billing.complimentary_access_service import (
    PlanNotAvailableError, grant_complimentary_access, list_provisioning_options,
)
from apps.billing.models import Plan, SubscriptionV2
from apps.billing.plans import get_seat_limit
from apps.billing.runtime import _extract_plan_tier, is_reception_plan_code, resolve_subscription
from apps.business.context import build_business_context
from apps.business.entitlements import (
    APPOINTMENTS_LEADS_ENTITLEMENT,
    RECEPTION_AI_ENTITLEMENT,
    RECEPTION_CUSTOMERS_ENTITLEMENT,
    RECEPTION_LEADS_ENTITLEMENT,
    has_entitlement,
)
from apps.business.models import Business, Subscription

User = get_user_model()
RECEPTION_ENTITLEMENTS = {RECEPTION_LEADS_ENTITLEMENT, RECEPTION_AI_ENTITLEMENT, RECEPTION_CUSTOMERS_ENTITLEMENT}
TIERS = ['reception_300', 'reception_1500', 'reception_3000', 'reception_custom']


def _business(service='reception', slug=None):
    slug = slug or f'rcp-{uuid.uuid4().hex[:8]}'
    return Business.objects.create(
        name=f'Biz {slug}', slug=slug, service_type=service, default_service=service, status='active',
    )


def _sub(business, service_type, plan_code, usage_tier=None, status=SubscriptionV2.Status.ACTIVE, **extra):
    return SubscriptionV2.objects.create(
        business=business, service_type=service_type, plan_code=plan_code, usage_tier=usage_tier,
        provider=SubscriptionV2.Provider.MANUAL, external_reference=f'SUB-{uuid.uuid4()}',
        status=status, **extra,
    )


def _reception(business, **extra):
    return _sub(business, 'reception', 'reception', 'reception_300', **extra)


def _superadmin():
    user = User.objects.create_user(username=f'sa-{uuid.uuid4().hex}', email=f'{uuid.uuid4().hex}@x.test')
    profile = user.account_profile
    profile.is_platform_staff, profile.internal_role = True, 'superadmin'
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    return user


# ── Catálogo ─────────────────────────────────────────────────────────────────

class ReceptionCatalogTests(SimpleTestCase):

    def test_product_plan_and_tiers_are_unsellable(self):
        catalog = canonical_pricing.get_reception_catalog()
        self.assertEqual(catalog['product']['vertical'], 'reception')
        self.assertIs(catalog['product']['is_active'], False)
        [plan] = catalog['plans']
        self.assertEqual(plan['code'], 'reception')
        self.assertEqual(plan['name'], 'Recepcionista IA')
        self.assertEqual(plan['pricing_mode'], 'usage_tier')
        self.assertIsNone(plan['price_monthly'])
        self.assertIsNone(plan['price_yearly'])
        self.assertEqual(plan['usage_tiers'], TIERS)
        self.assertNotIn('professionals_included', plan)
        self.assertEqual([t['code'] for t in catalog['usage_tiers']], TIERS)
        for tier in catalog['usage_tiers']:
            self.assertEqual((tier['purchase_mode'], tier['billing_mode']), ('contact_sales', 'manual'))
            for key in ('monthly_price', 'annual_price', 'included_conversations',
                        'extra_conversation_price', 'default_extra_spend_limit'):
                self.assertIsNone(tier[key], f'{tier["code"]}.{key}')

    def test_not_available_for_public_checkout_or_product_listing(self):
        self.assertFalse(canonical_pricing.is_plan_product_active('reception'))
        self.assertNotIn('reception', [p['code'] for p in canonical_pricing.get_products_catalog()])
        self.assertIn('reception', canonical_pricing.get_inactive_product_verticals())

    def test_turnos_catalog_untouched(self):
        ai = canonical_pricing.get_plan('appointments_ai')
        self.assertEqual(ai['usage_tiers'], ['ai_300', 'ai_1500', 'ai_3000', 'custom'])
        self.assertTrue(all(t['plan_code'] == 'appointments_ai'
                            for t in canonical_pricing.get_appointments_catalog()['usage_tiers']))

    def test_validator_rejects_any_sellable_or_inconsistent_reception(self):
        with open(canonical_pricing._PRICING_JSON_PATH, encoding='utf-8') as f:
            base = json.load(f)
        canonical_pricing.validate_reception_catalog(copy.deepcopy(base))

        def mutated(fn):
            data = copy.deepcopy(base)
            fn(data)
            return data

        def product(data):
            return next(p for p in data['products'] if p['code'] == 'reception')

        def plan(data):
            return next(p for p in data['plans'] if p['code'] == 'reception')

        def tier(data, code='reception_300'):
            return next(t for t in data['usage_tiers'] if t['code'] == code)

        cases = {
            'active product': lambda d: product(d).update(is_active=True),
            'fixed price': lambda d: plan(d).update(price_monthly=10000),
            'no seats': lambda d: plan(d).update(secondary_users_included=0),
            'professionals': lambda d: plan(d).update(professionals_included=2),
            'foreign tier list': lambda d: plan(d).update(usage_tiers=['ai_300']),
            'priced tier': lambda d: tier(d).update(monthly_price=150000),
            'self service tier': lambda d: tier(d).update(purchase_mode='self_service'),
            'allowance without approval': lambda d: tier(d).update(included_conversations=300),
            'tier of another plan': lambda d: tier(d).update(plan_code='appointments_ai'),
            'missing tier': lambda d: d.update(usage_tiers=[t for t in d['usage_tiers'] if t['code'] != 'reception_1500']),
            'second plan': lambda d: d['plans'].append({**plan(d), 'code': 'reception_pro'}),
        }
        for name, fn in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                canonical_pricing.validate_reception_catalog(mutated(fn))

    def test_plan_tier_detection(self):
        self.assertEqual(_extract_plan_tier('reception'), 'reception')
        self.assertTrue(is_reception_plan_code('reception'))
        self.assertTrue(is_reception_plan_code('bundle-reception-monthly'))
        for code in ('appointments_ai', 'pro', 'gestion_pro_monthly', 'receptionist', ''):
            with self.subTest(code=code):
                self.assertFalse(is_reception_plan_code(code))


class ReceptionUsageTierValidationTests(SimpleTestCase):

    def test_reception_requires_its_own_tier(self):
        for tier in TIERS:
            validate_usage_tier('reception', tier)
        for tier in (None, '', 'ai_300', 'custom', 'reception_999'):
            with self.subTest(tier=tier), self.assertRaises(ValidationError):
                validate_usage_tier('reception', tier)

    def test_reception_tiers_never_valid_for_other_plans(self):
        for plan in ('appointments_ai', 'appointments', 'pro', 'qr_reviews_base'):
            with self.subTest(plan=plan), self.assertRaises(ValidationError):
                validate_usage_tier(plan, 'reception_300')

    def test_turnos_ia_validation_unchanged(self):
        validate_usage_tier('appointments_ai', 'ai_300')
        validate_usage_tier('appointments_ai', None, allow_legacy_null=True)
        with self.assertRaises(ValidationError):
            validate_usage_tier('appointments_ai', None)

    def test_seat_limit_from_catalog(self):
        self.assertEqual(get_seat_limit('reception'),
                         canonical_pricing.get_plan('reception')['secondary_users_included'])
        self.assertGreaterEqual(get_seat_limit('reception'), 1)


# ── Resolución y aislamiento ─────────────────────────────────────────────────

class ReceptionSubscriptionResolutionTests(TestCase):

    def assertNoAccess(self, resolved):
        self.assertFalse(resolved.access_granted)
        self.assertEqual(resolved.entitlements, frozenset())

    def test_reception_resolves_its_own_subscription(self):
        biz = _business()
        sub = _reception(biz)
        resolved = resolve_subscription(biz)
        self.assertEqual((resolved.source, resolved.service_type, resolved.plan), ('v2', 'reception', 'reception'))
        self.assertTrue(resolved.access_granted)
        self.assertEqual(resolved.subscription_v2, sub)
        self.assertEqual(set(resolved.entitlements), RECEPTION_ENTITLEMENTS)
        for code in RECEPTION_ENTITLEMENTS:
            self.assertTrue(has_entitlement(biz, code), code)

    def test_reception_never_grants_gestion_or_turnos(self):
        biz = _business(service='gestion')
        _reception(biz)
        for service in ('gestion', 'appointments', 'menu_qr', 'qr_reviews', 'restaurante'):
            with self.subTest(service=service):
                resolved = resolve_subscription(biz, service_type=service)
                self.assertEqual(resolved.source, 'none')
                self.assertNoAccess(resolved)
        for code in ('gestion.products', 'gestion.customers', 'appointments.customers', APPOINTMENTS_LEADS_ENTITLEMENT):
            self.assertFalse(has_entitlement(biz, code), code)
        # Its own entitlements still resolve with another principal service.
        self.assertTrue(has_entitlement(biz, RECEPTION_LEADS_ENTITLEMENT))

    def test_other_services_never_grant_reception(self):
        cases = {
            'gestion': ('gestion', 'pro', None),
            'menu_qr': ('menu_qr', 'menu_qr_visual', None),
            'appointments': ('appointments', 'appointments_pro', None),
            'appointments_ai': ('appointments', 'appointments_ai', 'ai_300'),
        }
        for name, (service, plan, tier) in cases.items():
            with self.subTest(name):
                biz = _business(service=service)
                _sub(biz, service, plan, tier)
                self.assertNoAccess(resolve_subscription(biz, service_type='reception'))
                self.assertEqual(resolve_subscription(biz, service_type='reception').source, 'none')
                for code in RECEPTION_ENTITLEMENTS:
                    self.assertFalse(has_entitlement(biz, code), code)

    def test_legacy_subscriptions_never_resolve_reception(self):
        for plan, service in (('pro', 'gestion'), ('appointments_base', 'appointments')):
            with self.subTest(plan=plan):
                biz = _business(service=service)
                Subscription.objects.create(business=biz, plan=plan, status='active', service=service)
                self.assertEqual(resolve_subscription(biz, service_type='reception').source, 'none')
                self.assertFalse(has_entitlement(biz, RECEPTION_LEADS_ENTITLEMENT))

    def test_gestion_principal_with_reception_contracted(self):
        biz = _business(service='gestion')
        gestion = _sub(biz, 'gestion', 'pro')
        reception = _reception(biz)
        self.assertEqual(resolve_subscription(biz).subscription_v2, gestion)
        self.assertEqual(resolve_subscription(biz, service_type='reception').subscription_v2, reception)
        self.assertTrue(has_entitlement(biz, 'gestion.customers'))
        self.assertTrue(has_entitlement(biz, RECEPTION_AI_ENTITLEMENT))
        self.assertNotIn(RECEPTION_LEADS_ENTITLEMENT, resolve_subscription(biz).entitlements)

    def test_reception_and_turnos_resolve_independently(self):
        biz = _business(service='appointments')
        turnos = _sub(biz, 'appointments', 'appointments_pro')
        reception = _reception(biz)
        appointments = resolve_subscription(biz, service_type='appointments')
        own = resolve_subscription(biz, service_type='reception')
        self.assertEqual((appointments.subscription_v2, own.subscription_v2), (turnos, reception))
        self.assertTrue(RECEPTION_ENTITLEMENTS.isdisjoint(appointments.entitlements))
        self.assertNotIn('appointments.customers', own.entitlements)
        self.assertFalse(has_entitlement(biz, APPOINTMENTS_LEADS_ENTITLEMENT))
        self.assertTrue(has_entitlement(biz, RECEPTION_LEADS_ENTITLEMENT))

    def test_reception_plan_under_another_service_grants_nothing(self):
        biz = _business(service='gestion')
        _sub(biz, 'gestion', 'reception', 'reception_300')  # mislabeled row
        self.assertEqual(resolve_subscription(biz, service_type='gestion').source, 'none')
        self.assertEqual(resolve_subscription(biz, service_type='reception').source, 'none')
        self.assertFalse(has_entitlement(biz, RECEPTION_LEADS_ENTITLEMENT))
        self.assertFalse(has_entitlement(biz, 'gestion.products'))

    def test_unknown_plan_or_tier_fails_closed(self):
        biz = _business()
        wrong_plan = _sub(biz, 'reception', 'pro')
        self.assertNoAccess(resolve_subscription(biz))
        self.assertFalse(has_entitlement(biz, RECEPTION_LEADS_ENTITLEMENT))
        wrong_plan.delete()
        sub = _reception(biz)
        # A tier from another product written behind clean() (raw update).
        SubscriptionV2.objects.filter(pk=sub.pk).update(usage_tier='ai_300')
        self.assertNoAccess(resolve_subscription(biz))
        SubscriptionV2.objects.filter(pk=sub.pk).update(usage_tier=None)
        self.assertNoAccess(resolve_subscription(biz))
        self.assertFalse(has_entitlement(biz, RECEPTION_AI_ENTITLEMENT))

    def test_model_validation_rejects_invalid_tiers(self):
        biz = _business()
        for tier in (None, 'ai_300', 'custom'):
            with self.subTest(tier=tier), self.assertRaises(ValidationError):
                _sub(biz, 'reception', 'reception', tier)
        with self.assertRaises(ValidationError):
            _sub(biz, 'appointments', 'appointments_ai', 'reception_300')

    def test_inactive_subscription_states(self):
        for status in (SubscriptionV2.Status.CANCELED, SubscriptionV2.Status.CHECKOUT_PENDING):
            with self.subTest(status=status):
                biz = _business()
                _reception(biz, status=status)
                resolved = resolve_subscription(biz)
                self.assertEqual(resolved.source, 'none')
                self.assertNoAccess(resolved)
        biz = _business()
        _reception(biz, status=SubscriptionV2.Status.SUSPENDED)
        resolved = resolve_subscription(biz)
        self.assertEqual(resolved.source, 'v2')
        self.assertFalse(resolved.access_granted)
        self.assertFalse(has_entitlement(biz, RECEPTION_LEADS_ENTITLEMENT))

    def test_future_benefit_grants_nothing_before_start(self):
        biz = _business()
        start = (timezone.now() + timedelta(days=1)).replace(microsecond=0)
        _reception(
            biz, status=SubscriptionV2.Status.TRIALING, is_active=True,
            current_period_start=start, current_period_end=start + timedelta(days=90),
            manual_granted_by=_superadmin(), manual_grant_reason='Beneficio futuro',
        )
        with patch('django.utils.timezone.now', return_value=start - timedelta(seconds=1)):
            self.assertFalse(resolve_subscription(biz).access_granted)
            self.assertFalse(has_entitlement(biz, RECEPTION_LEADS_ENTITLEMENT))
        with patch('django.utils.timezone.now', return_value=start):
            self.assertTrue(resolve_subscription(biz).access_granted)
            self.assertTrue(has_entitlement(biz, RECEPTION_LEADS_ENTITLEMENT))


class TurnosCompatibilityTests(TestCase):

    def test_turnos_ia_keeps_leads(self):
        biz = _business(service='appointments')
        _sub(biz, 'appointments', 'appointments_ai', 'ai_300')
        self.assertTrue(has_entitlement(biz, APPOINTMENTS_LEADS_ENTITLEMENT))
        self.assertTrue(has_entitlement(biz, 'appointments.customers'))

    def test_legacy_turnos_base_keeps_leads(self):
        biz = _business(service='appointments')
        Subscription.objects.create(business=biz, plan='appointments_base', status='active', service='appointments')
        self.assertTrue(has_entitlement(biz, APPOINTMENTS_LEADS_ENTITLEMENT))

    def test_v2_turnos_base_keeps_its_legacy_leads(self):
        # `appointments_base` is not a canonical Turnos plan code: its V2 row
        # resolves through PLAN_ENTITLEMENTS['appointments_base'] (legacy-compat),
        # which includes Leads. Unchanged by PROD-02B.
        biz = _business(service='appointments')
        _sub(biz, 'appointments', 'appointments_base')
        self.assertTrue(has_entitlement(biz, APPOINTMENTS_LEADS_ENTITLEMENT))
        self.assertTrue(has_entitlement(biz, 'appointments.customers'))
        self.assertFalse(has_entitlement(biz, RECEPTION_LEADS_ENTITLEMENT))

    def test_canonical_turnos_plans_without_leads(self):
        for plan in ('appointments', 'appointments_pro'):
            with self.subTest(plan=plan):
                biz = _business(service='appointments')
                _sub(biz, 'appointments', plan)
                self.assertFalse(has_entitlement(biz, APPOINTMENTS_LEADS_ENTITLEMENT))
                self.assertTrue(has_entitlement(biz, 'appointments.customers'))

    def test_gestion_historical_fallback_preserved(self):
        # Non-isolated services keep the historical cross-service fallback.
        biz = _business(service='menu_qr')
        gestion = _sub(biz, 'gestion', 'pro')
        self.assertEqual(resolve_subscription(biz, service_type='menu_qr').subscription_v2, gestion)


# ── Contexto de negocio ──────────────────────────────────────────────────────

class ReceptionBusinessContextTests(TestCase):

    def test_reception_only_business_is_never_gestion(self):
        biz = _business()
        _reception(biz)
        context = build_business_context(biz)
        self.assertEqual(context['service'], 'reception')
        self.assertEqual(context['enabled_services'], ['reception'])
        self.assertTrue(context['features']['reception_core'])
        for flag in ('products', 'inventory', 'sales', 'appointments_core', 'agenda_integration'):
            self.assertFalse(context['features'][flag], flag)
        # PROD-02C: its own Leads and Clientes core capabilities.
        self.assertTrue(context['features']['leads'])
        self.assertTrue(context['features']['customers'])

    def test_invalid_reception_subscription_enables_nothing(self):
        biz = _business()
        _sub(biz, 'reception', 'pro')
        context = build_business_context(biz)
        self.assertNotIn('gestion', context['enabled_services'])
        self.assertFalse(context['features']['products'])
        self.assertFalse(context['features']['reception_core'])

    def test_other_services_do_not_enable_reception(self):
        biz = _business(service='gestion')
        _sub(biz, 'gestion', 'business')
        context = build_business_context(biz)
        self.assertNotIn('reception', context['enabled_services'])
        self.assertFalse(context['features']['reception_core'])


# ── Usuarios secundarios ─────────────────────────────────────────────────────

class ReceptionSeatLimitTests(TestCase):

    def _user(self):
        return User.objects.create_user(username=f'u-{uuid.uuid4().hex[:10]}', password='x')

    def test_limit_comes_from_catalog_and_owner_is_excluded(self):
        biz = _business()
        _reception(biz)
        limit = get_seat_limit('reception')
        Membership.objects.create(user=self._user(), business=biz, role='owner')
        for _ in range(limit):
            Membership.objects.create(user=self._user(), business=biz, role='manager')
        with self.assertRaises(ValidationError):
            Membership.objects.create(user=self._user(), business=biz, role='viewer')
        # The owner is never counted and can still exist on top of the limit.
        Membership.objects.create(user=self._user(), business=biz, role='owner')
        self.assertEqual(Membership.objects.filter(business=biz).exclude(role='owner').count(), limit)

    def test_no_secondary_users_without_resolved_subscription(self):
        for status in (SubscriptionV2.Status.CANCELED, SubscriptionV2.Status.SUSPENDED):
            with self.subTest(status=status):
                biz = _business()
                _reception(biz, status=status)
                Membership.objects.create(user=self._user(), business=biz, role='owner')
                with self.assertRaises(ValidationError):
                    Membership.objects.create(user=self._user(), business=biz, role='manager')

    def test_gestion_subscription_does_not_open_seats_for_reception_business(self):
        biz = _business()
        _sub(biz, 'gestion', 'business')  # would have allowed 25 before the fix
        with self.assertRaises(ValidationError):
            Membership.objects.create(user=self._user(), business=biz, role='manager')

    def test_professional_role_rejected_without_turnos(self):
        biz = _business()
        _reception(biz)
        with self.assertRaises(ValidationError):
            Membership.objects.create(user=self._user(), business=biz, role='professional')


# ── Venta pública y provisioning ─────────────────────────────────────────────

class ReceptionNotSellableTests(TestCase):

    def setUp(self):
        call_command('seed_reception_catalog', stdout=StringIO())

    def test_seed_creates_an_inactive_zero_price_plan_idempotently(self):
        call_command('seed_reception_catalog', stdout=StringIO())
        plan = Plan.objects.get(code='reception')
        self.assertEqual(plan.plan_status, 'inactive')
        self.assertEqual(plan.price, 0)
        self.assertEqual(plan.features_json['vertical'], 'reception')
        self.assertEqual(plan.features_json['usage_tiers'], TIERS)
        self.assertEqual(Plan.objects.filter(code='reception').count(), 1)

    def test_public_signup_rejects_reception(self):
        Plan.objects.create(code='gestion_pro_monthly_rcp', name='Pro', price=50000, interval='monthly')
        client = APIClient()
        for payload in (
            {'plan_code': 'reception'},
            {'plan_code': 'gestion_pro_monthly_rcp', 'service': 'reception'},
        ):
            with self.subTest(payload=payload):
                response = client.post('/api/v1/billing/start-subscription', {
                    'email': f'{uuid.uuid4().hex[:8]}@x.test', 'password': 'Secret-123456',
                    'business_name': 'Nuevo', **payload,
                }, format='json')
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()['error'], 'Product is not available for purchase')
        self.assertFalse(Business.objects.filter(default_service='reception').exists())

    def test_admin_provisioning_not_enabled(self):
        self.assertNotIn('reception', [option['value'] for option in list_provisioning_options()])
        biz = _business(service='reception')
        start = timezone.now()
        with self.assertRaises(PlanNotAvailableError):
            grant_complimentary_access(
                business=biz, plan_code='reception', service_type='reception',
                starts_at=start, ends_at=start + timedelta(days=30), granted_by=_superadmin(),
                reason='No habilitado todavía', usage_tier='reception_300',
            )
        self.assertFalse(SubscriptionV2.objects.filter(business=biz).exists())

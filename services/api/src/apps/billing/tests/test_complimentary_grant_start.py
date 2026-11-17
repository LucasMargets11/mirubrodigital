"""
Complimentary grant start (Turnos IA pilot): a grant created by the admin form
with a future start gives no access until current_period_start.

Before this fix billing.runtime._v2_grants_access only checked the end of the
bonified window, so a manual grant starting tomorrow already opened /app, the
`leads` session flag and GET /api/v1/leads/. The Turnos lifecycle and the AI
authorization already excluded it (appointments_lifecycle.complimentary_grant_active).

The runtime rule is shared by every service (gestion, menu_qr, qr_reviews,
appointments), so the scope tests pin what does NOT change: rows without
current_period_start, Mercado Pago trials, trials with trial_ends_at and
active manual rows.

Time is controlled by patching django.utils.timezone.now.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.billing.complimentary_access_service import grant_complimentary_access
from apps.billing.models import SubscriptionV2
from apps.billing.runtime import _v2_access_until, _v2_grants_access, resolve_subscription
from apps.billing.services.appointments_lifecycle import complimentary_grant_active
from apps.business.entitlements import has_appointments_leads_access
from apps.business.models import Business

User = get_user_model()
ME_URL = '/api/v1/auth/me/'
LEADS_URL = '/api/v1/leads/'
SECOND = timedelta(seconds=1)


def _superadmin():
    user = User.objects.create_user(username=f'sa-{uuid.uuid4().hex}', email=f'{uuid.uuid4().hex}@x.test')
    profile = user.account_profile
    profile.is_platform_staff, profile.internal_role = True, 'superadmin'
    profile.save(update_fields=['is_platform_staff', 'internal_role'])
    return user


class FutureTurnosIAGrantTests(TestCase):
    """Turnos IA grant that starts tomorrow, exactly as /admin/clientes/nuevo creates it."""

    def setUp(self):
        call_command('seed_appointments_catalog', stdout=StringIO())
        self.start = (timezone.now() + timedelta(days=1)).replace(microsecond=0)
        self.end = self.start + timedelta(days=180)
        self.business = Business.objects.create(
            name='Piloto futuro', slug=f'piloto-futuro-{uuid.uuid4().hex[:8]}',
            service_type='appointments', default_service='appointments', status='onboarding',
        )
        self.subscription = grant_complimentary_access(
            business=self.business, plan_code='appointments_ai', service_type='appointments',
            starts_at=self.start, ends_at=self.end, granted_by=_superadmin(),
            reason='Piloto que empieza mañana', usage_tier='ai_300',
        )
        self.business.refresh_from_db()
        self.reception = User.objects.create_user(
            username=f'recepcion-{uuid.uuid4().hex[:8]}@x.test', password='x',
        )
        # Seat check uses the same runtime rule: non-owner members can only be
        # added once the grant started (the owner membership never consumes a seat).
        with patch('django.utils.timezone.now', return_value=self.start - SECOND):
            with self.assertRaises(DjangoValidationError):
                Membership.objects.create(user=self.reception, business=self.business, role='manager')
        with patch('django.utils.timezone.now', return_value=self.start):
            Membership.objects.create(user=self.reception, business=self.business, role='manager')
        self.client = APIClient()
        self.client.force_authenticate(self.reception)

    def snapshot(self, at):
        with patch('django.utils.timezone.now', return_value=at):
            resolved = resolve_subscription(self.business, service_type='appointments')
            me = self.client.get(ME_URL)
            leads = self.client.get(LEADS_URL)
            return {
                'runtime': resolved.access_granted,
                'leads_entitlement': has_appointments_leads_access(self.business),
                'lifecycle': complimentary_grant_active(self.subscription, at=at),
                'me_access_allowed': me.data['subscription']['access_allowed'],
                'me_leads_flag': bool(me.data['features'].get('leads')) and me.data['subscription']['access_allowed'],
                'me_view_leads': me.data['permissions'].get('view_leads'),
                'leads_status': leads.status_code,
            }

    def test_grant_shape_is_the_admin_form_one(self):
        self.assertEqual(
            (self.subscription.provider, self.subscription.status, self.subscription.trial_ends_at,
             self.subscription.current_period_start, self.subscription.current_period_end),
            ('manual', 'trialing', None, self.start, self.end),
        )
        self.assertEqual(self.business.status, 'trialing')

    def test_no_access_just_before_start(self):
        snap = self.snapshot(self.start - SECOND)
        self.assertEqual(snap, {
            'runtime': False, 'leads_entitlement': False, 'lifecycle': False,
            'me_access_allowed': False, 'me_leads_flag': False, 'me_view_leads': True,
            'leads_status': 403,
        })

    def test_access_at_the_start_instant(self):
        snap = self.snapshot(self.start)
        self.assertEqual(snap, {
            'runtime': True, 'leads_entitlement': True, 'lifecycle': True,
            'me_access_allowed': True, 'me_leads_flag': True, 'me_view_leads': True,
            'leads_status': 200,
        })

    def test_access_just_before_end(self):
        self.assertEqual(self.snapshot(self.end - SECOND)['leads_status'], 200)

    def test_no_access_at_end_instant(self):
        snap = self.snapshot(self.end)
        self.assertEqual(
            (snap['runtime'], snap['leads_entitlement'], snap['lifecycle'],
             snap['me_access_allowed'], snap['me_leads_flag'], snap['leads_status']),
            (False, False, False, False, False, 403),
        )

    def test_me_flag_reaches_the_ui_only_with_access(self):
        # The web shows Leads only with access_allowed (app layout) AND
        # features.leads (resolveLeadsAccess). Before the start, /me must not
        # open the app at all.
        with patch('django.utils.timezone.now', return_value=self.start - SECOND):
            me = self.client.get(ME_URL).data
        self.assertFalse(me['subscription']['access_allowed'])

    def test_resolving_before_start_does_not_mutate_the_row(self):
        before = SubscriptionV2.objects.get(pk=self.subscription.pk)
        self.snapshot(self.start - SECOND)
        after = SubscriptionV2.objects.get(pk=self.subscription.pk)
        self.assertEqual(
            (before.status, before.is_active, before.updated_at),
            (after.status, after.is_active, after.updated_at),
        )


class SharedRuleScopeTests(TestCase):
    """_v2_grants_access is shared by every service: only manual grants with a start move."""

    _counter = 0

    def make_sub(self, **fields):
        type(self)._counter += 1
        biz = Business.objects.create(
            name=f'Scope {self._counter}', default_service='gestion', status='trialing',
        )
        data = dict(
            business=biz, service_type='gestion', plan_code='gestion_pro',
            provider=SubscriptionV2.Provider.MANUAL, status=SubscriptionV2.Status.TRIALING,
            external_reference=f'SUB-start-scope-{uuid.uuid4().hex}',
        )
        data.update(fields)
        return SubscriptionV2.objects.create(**data)

    def grants(self, sub, at):
        with patch('django.utils.timezone.now', return_value=at):
            return _v2_grants_access(sub)

    def test_gestion_manual_grant_waits_for_its_start(self):
        now = timezone.now()
        sub = self.make_sub(current_period_start=now + timedelta(days=1), current_period_end=now + timedelta(days=30))
        self.assertFalse(self.grants(sub, now))
        self.assertTrue(self.grants(sub, now + timedelta(days=1)))
        self.assertFalse(self.grants(sub, now + timedelta(days=30)))

    def test_menu_grant_from_admin_form_waits_for_its_start(self):
        now = timezone.now().replace(microsecond=0)
        biz = Business.objects.create(name='Menu futuro', default_service='menu_qr', status='onboarding')
        start = now + timedelta(days=1)
        sub = SubscriptionV2.objects.create(
            business=biz, service_type='menu_qr', plan_code='menu_qr_pro',
            provider=SubscriptionV2.Provider.MANUAL, status=SubscriptionV2.Status.TRIALING,
            external_reference=f'SUB-menu-{uuid.uuid4().hex}',
            current_period_start=start, current_period_end=start + timedelta(days=90),
        )
        with patch('django.utils.timezone.now', return_value=start - SECOND):
            self.assertFalse(resolve_subscription(biz).access_granted)
        with patch('django.utils.timezone.now', return_value=start):
            self.assertTrue(resolve_subscription(biz).access_granted)
        self.assertEqual(_v2_access_until(sub), start + timedelta(days=90))

    def test_manual_row_without_start_keeps_the_end_only_rule(self):
        now = timezone.now()
        sub = self.make_sub(current_period_start=None, current_period_end=now + timedelta(days=1))
        self.assertTrue(self.grants(sub, now))

    def test_mercadopago_trial_without_trial_ends_at_ignores_the_start(self):
        now = timezone.now()
        sub = self.make_sub(
            provider=SubscriptionV2.Provider.MERCADOPAGO,
            current_period_start=now + timedelta(days=5), current_period_end=now - timedelta(days=1),
        )
        self.assertTrue(self.grants(sub, now))

    def test_trial_with_trial_ends_at_keeps_trial_semantics(self):
        now = timezone.now()
        sub = self.make_sub(
            trial_ends_at=now + timedelta(days=2), current_period_start=now + timedelta(days=1),
        )
        self.assertTrue(self.grants(sub, now))

    def test_active_manual_row_ignores_the_start(self):
        now = timezone.now()
        sub = self.make_sub(status=SubscriptionV2.Status.ACTIVE, current_period_start=now + timedelta(days=1))
        self.assertTrue(self.grants(sub, now))

    def test_runtime_and_turnos_lifecycle_agree_on_the_window(self):
        now = timezone.now().replace(microsecond=0)
        sub = self.make_sub(
            service_type='appointments', plan_code='appointments_ai', usage_tier='ai_300',
            current_period_start=now, current_period_end=now + timedelta(days=10),
        )
        for at in (now - SECOND, now, now + timedelta(days=10) - SECOND, now + timedelta(days=10)):
            self.assertEqual(self.grants(sub, at), complimentary_grant_active(sub, at=at), at)

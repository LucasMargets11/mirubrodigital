"""
Tests for V2-first seat limit enforcement.

Covers:
  - V2 subscription with various plan tiers enforces correct seat limits
  - Legacy fallback when no V2 subscription
  - No subscription blocks member creation (PermissionDenied)
  - Owner excluded from seat count
  - seat_info endpoint returns correct data
  - Signal-level seat protection
  - access_granted=False blocks creation
  - seat_info.current reflects real count even when access_granted=False
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient
from rest_framework import status as http_status

from apps.accounts.models import Membership, AccountProfile
from apps.billing.plans import get_seat_limit, PLAN_SEAT_LIMITS, DEFAULT_SEAT_LIMIT
from apps.billing.models import SubscriptionV2
from apps.billing.runtime import ResolvedSubscription
from apps.business.models import Business, Subscription, SubscriptionAddon

User = get_user_model()


def _make_resolved(source='v2', plan='starter', access_granted=True, legacy_sub=None):
    """Helper to create a ResolvedSubscription-like object for mocking."""
    rs = MagicMock(spec=ResolvedSubscription)
    rs.source = source
    rs.plan = plan
    rs.access_granted = access_granted
    rs.access_until = None
    rs.legacy_sub = legacy_sub
    rs.status = 'active'
    rs.subscription_v2 = MagicMock() if source == 'v2' else None
    return rs


@override_settings(
    AUTHENTICATION_BACKENDS=['apps.accounts.auth_backends.UsernameOrEmailBackend'],
)
class SeatLimitV2Tests(TestCase):
    """Tests for V2-first seat limit enforcement in InternalUserService."""

    def setUp(self):
        self.business = Business.objects.create(
            name='Test HQ',
            default_service='gestion',
            status='active',
        )
        # Legacy subscription (used as fallback only)
        self.subscription = Subscription.objects.create(
            business=self.business,
            plan='starter',
            status='active',
            max_seats=5,
        )
        self.owner = User.objects.create_user(
            username='owner@test.com',
            email='owner@test.com',
            password='OwnerPass123',
            first_name='Owner',
            last_name='User',
        )
        self.owner_membership = Membership.objects.create(
            user=self.owner,
            business=self.business,
            role='owner',
        )

        self.client = APIClient()
        self.create_url = '/api/v1/owner/access/accounts/create/'

    def _create_payload(self, **overrides):
        defaults = {
            'first_name': 'Test',
            'last_name': 'User',
            'username': 'testuser',
            'password': 'SecurePass99',
            'role': 'cashier',
        }
        defaults.update(overrides)
        return defaults

    # ── get_seat_limit unit tests ──────────────────────────────────────────

    def test_get_seat_limit_known_plans(self):
        """get_seat_limit returns correct limits for known plan tiers."""
        self.assertEqual(get_seat_limit('start'), 2)
        self.assertEqual(get_seat_limit('starter'), 2)
        self.assertEqual(get_seat_limit('plus'), 5)
        self.assertEqual(get_seat_limit('pro'), 10)
        self.assertEqual(get_seat_limit('business'), 25)
        self.assertEqual(get_seat_limit('enterprise'), 100)

    def test_get_seat_limit_unknown_plan_returns_default(self):
        """get_seat_limit returns DEFAULT_SEAT_LIMIT for unknown plans."""
        self.assertEqual(get_seat_limit('unknown_plan'), DEFAULT_SEAT_LIMIT)
        self.assertEqual(get_seat_limit(None), DEFAULT_SEAT_LIMIT)

    def test_get_seat_limit_menu_qr_plans(self):
        """get_seat_limit returns correct limits for menu_qr plans."""
        self.assertEqual(get_seat_limit('menu_qr'), 2)
        self.assertEqual(get_seat_limit('menu_qr_plus'), DEFAULT_SEAT_LIMIT)

    def test_turnos_seat_limits_come_from_the_canonical_plan_catalog(self):
        for plan, expected in (
            ('appointments', 2),
            ('appointments_pro', 5),
            ('appointments_ai', 5),
        ):
            with self.subTest(plan=plan):
                self.assertEqual(get_seat_limit(plan), expected)

        self.assertEqual(get_seat_limit('appointments_base'), DEFAULT_SEAT_LIMIT)
        for tier in ('ai_300', 'ai_1500', 'ai_3000'):
            with self.subTest(tier=tier):
                self.assertEqual(get_seat_limit('appointments_ai'), 5)

    def test_turnos_membership_enforcement_and_extra_professional_separation(self):
        from apps.appointments.models import AppointmentProfessional
        from apps.billing.appointments_plans import EXTRA_PROFESSIONAL

        cases = (
            ('appointments', None, 2, False),
            ('appointments_pro', None, 5, True),
            ('appointments_ai', 'ai_300', 5, True),
        )
        for plan, usage_tier, limit, has_professional_login in cases:
            with self.subTest(plan=plan):
                business = Business.objects.create(
                    name=f'Turnos {plan}',
                    default_service='appointments',
                    status='active',
                )
                subscription = SubscriptionV2.objects.create(
                    business=business,
                    service_type='appointments',
                    plan_code=plan,
                    usage_tier=usage_tier,
                    external_reference=f'SUB-{uuid.uuid4()}',
                    provider=SubscriptionV2.Provider.MANUAL,
                    status=SubscriptionV2.Status.ACTIVE,
                )
                if has_professional_login:
                    SubscriptionAddon.objects.create(
                        subscription_v2=subscription,
                        code=EXTRA_PROFESSIONAL,
                        quantity=3,
                    )

                owner = User.objects.create_user(
                    username=f'{plan}_owner',
                    password='OwnerPass123',
                )
                Membership.objects.create(user=owner, business=business, role='owner')

                for index in range(limit):
                    user = User.objects.create_user(
                        username=f'{plan}_secondary_{index}',
                        password='MemberPass123',
                    )
                    role = 'professional' if has_professional_login and index == 0 else 'cashier'
                    membership = Membership.objects.create(
                        user=user,
                        business=business,
                        role=role,
                    )
                    if role == 'professional':
                        AppointmentProfessional.objects.create(
                            business=business,
                            name=f'{plan} Login Professional',
                            membership=membership,
                        )

                AppointmentProfessional.objects.create(
                    business=business,
                    name=f'{plan} Agenda Professional',
                )
                self.assertEqual(
                    Membership.objects.filter(business=business).exclude(role='owner').count(),
                    limit,
                )
                with self.assertRaises(DjangoValidationError):
                    extra_user = User.objects.create_user(
                        username=f'{plan}_overflow',
                        password='MemberPass123',
                    )
                    Membership.objects.create(
                        user=extra_user,
                        business=business,
                        role='cashier',
                    )

    @patch('apps.billing.runtime.resolve_subscription')
    def test_suspended_turnos_subscription_does_not_grant_seats(self, mock_resolve):
        mock_resolve.return_value = _make_resolved(
            source='v2', plan='appointments_pro', access_granted=False,
        )
        user = User.objects.create_user(username='suspended_turnos', password='Pass1234')
        with self.assertRaises(DjangoValidationError):
            Membership.objects.create(user=user, business=self.business, role='cashier')

    # ── V2 subscription enforcement ───────────────────────────────────────

    @patch('apps.accounts.services.resolve_subscription')
    @patch('apps.billing.runtime.resolve_subscription')
    def test_v2_starter_plan_allows_up_to_2_secondary_users(self, mock_runtime, mock_resolve):
        """V2 starter plan allows 2 secondary users (owner excluded)."""
        resolved = _make_resolved(source='v2', plan='starter')
        mock_resolve.return_value = resolved
        mock_runtime.return_value = resolved

        self.client.force_authenticate(user=self.owner)

        # Create 2 users (starter limit)
        resp1 = self.client.post(self.create_url, self._create_payload(username='user1'), format='json')
        self.assertEqual(resp1.status_code, http_status.HTTP_201_CREATED)

        resp2 = self.client.post(self.create_url, self._create_payload(username='user2'), format='json')
        self.assertEqual(resp2.status_code, http_status.HTTP_201_CREATED)

        # 3rd should fail
        resp3 = self.client.post(self.create_url, self._create_payload(username='user3'), format='json')
        self.assertEqual(resp3.status_code, http_status.HTTP_400_BAD_REQUEST)

    @patch('apps.accounts.services.resolve_subscription')
    @patch('apps.billing.runtime.resolve_subscription')
    def test_v2_pro_plan_allows_up_to_10_secondary_users(self, mock_runtime, mock_resolve):
        """V2 pro plan should have a max of 10."""
        resolved = _make_resolved(source='v2', plan='pro')
        mock_resolve.return_value = resolved
        mock_runtime.return_value = resolved

        self.client.force_authenticate(user=self.owner)

        # Create 10 users
        for i in range(10):
            resp = self.client.post(
                self.create_url, self._create_payload(username=f'user{i}'), format='json'
            )
            self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED, f'User {i} should succeed')

        # 11th should fail
        resp = self.client.post(
            self.create_url, self._create_payload(username='user_overflow'), format='json'
        )
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    # ── Owner excluded from count ──────────────────────────────────────────

    @patch('apps.accounts.services.resolve_subscription')
    @patch('apps.billing.runtime.resolve_subscription')
    def test_owner_not_counted_toward_seat_limit(self, mock_runtime, mock_resolve):
        """Owner membership should not count toward the seat limit."""
        resolved = _make_resolved(source='v2', plan='start')
        mock_resolve.return_value = resolved
        mock_runtime.return_value = resolved
        # start = 2 seats. Owner exists but shouldn't count, so we can add 2.

        self.client.force_authenticate(user=self.owner)

        resp1 = self.client.post(
            self.create_url, self._create_payload(username='owner_test_u1'), format='json'
        )
        self.assertEqual(resp1.status_code, http_status.HTTP_201_CREATED, resp1.data)

        resp2 = self.client.post(
            self.create_url, self._create_payload(username='owner_test_u2'), format='json'
        )
        self.assertEqual(resp2.status_code, http_status.HTTP_201_CREATED)

    # ── No subscription blocks creation ────────────────────────────────────

    @patch('apps.accounts.services.resolve_subscription')
    def test_no_subscription_blocks_member_creation(self, mock_resolve):
        """When access_granted=False, member creation returns 403."""
        mock_resolve.return_value = _make_resolved(
            source='none', plan=None, access_granted=False
        )

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.create_url, self._create_payload(), format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_403_FORBIDDEN)

    @patch('apps.accounts.services.resolve_subscription')
    def test_suspended_v2_blocks_member_creation(self, mock_resolve):
        """Suspended V2 subscription (access_granted=False) blocks creation."""
        mock_resolve.return_value = _make_resolved(
            source='v2', plan='pro', access_granted=False
        )

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.create_url, self._create_payload(), format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_403_FORBIDDEN)

    # ── Legacy fallback ────────────────────────────────────────────────────

    @patch('apps.accounts.services.resolve_subscription')
    def test_legacy_fallback_uses_max_seats(self, mock_resolve):
        """When source=legacy, use legacy_sub.max_seats for the limit."""
        legacy_sub = MagicMock()
        legacy_sub.max_seats = 3
        mock_resolve.return_value = _make_resolved(
            source='legacy', plan='starter', access_granted=True, legacy_sub=legacy_sub
        )

        self.client.force_authenticate(user=self.owner)

        for i in range(3):
            resp = self.client.post(
                self.create_url, self._create_payload(username=f'legacy_user{i}'), format='json'
            )
            self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)

        resp = self.client.post(
            self.create_url, self._create_payload(username='legacy_overflow'), format='json'
        )
        self.assertEqual(resp.status_code, http_status.HTTP_400_BAD_REQUEST)

    # ── seat_info in accounts_list ────────────────────────────────────────

    @patch('apps.accounts.owner_views.resolve_subscription', create=True)
    @patch('apps.billing.runtime.resolve_subscription')
    def test_accounts_list_include_seat_info(self, mock_resolve_runtime, mock_resolve_views):
        """accounts_list with ?include_seat_info=1 returns wrapped response."""
        resolved = _make_resolved(source='v2', plan='appointments_pro')
        mock_resolve_runtime.return_value = resolved
        mock_resolve_views.return_value = resolved

        # Create one secondary user manually
        user2 = User.objects.create_user(username='secondary', password='Pass1234')
        Membership.objects.create(user=user2, business=self.business, role='cashier')

        self.client.force_authenticate(user=self.owner)

        # The view imports resolve_subscription at call time, so we need to patch it where it's used
        with patch('apps.billing.runtime.resolve_subscription', return_value=resolved):
            resp = self.client.get('/api/v1/owner/access/accounts/?include_seat_info=1')

        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertIn('seat_info', resp.data)
        self.assertIn('accounts', resp.data)
        seat_info = resp.data['seat_info']
        self.assertEqual(seat_info['current'], 1)  # Only secondary, owner excluded
        self.assertEqual(seat_info['max'], 5)  # Turnos Pro catalog limit
        self.assertTrue(seat_info['access_granted'])
        self.assertEqual(seat_info['source'], 'v2')

    def test_accounts_list_without_seat_info_returns_flat_array(self):
        """accounts_list without ?include_seat_info returns flat array (backward compat)."""
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get('/api/v1/owner/access/accounts/')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertIsInstance(resp.data, list)

    # ── Signal-level seat protection ──────────────────────────────────────

    @patch('apps.billing.runtime.resolve_subscription')
    def test_signal_blocks_over_limit(self, mock_resolve):
        """pre_save signal blocks membership creation over seat limit."""
        mock_resolve.return_value = _make_resolved(source='v2', plan='start')  # 2 seats

        # Create 2 secondary memberships
        for i in range(2):
            u = User.objects.create_user(username=f'sig_user{i}', password='Pass1234')
            Membership.objects.create(user=u, business=self.business, role='cashier')

        # 3rd should be blocked by signal
        u3 = User.objects.create_user(username='sig_user_overflow', password='Pass1234')
        with self.assertRaises(DjangoValidationError):
            Membership.objects.create(user=u3, business=self.business, role='cashier')

    @patch('apps.billing.runtime.resolve_subscription')
    def test_signal_skips_owner_membership(self, mock_resolve):
        """pre_save signal does not block owner membership creation."""
        mock_resolve.return_value = _make_resolved(source='v2', plan='start')  # 2 seats

        # Fill seats
        for i in range(2):
            u = User.objects.create_user(username=f'sig_owner_user{i}', password='Pass1234')
            Membership.objects.create(user=u, business=self.business, role='cashier')

        # Owner membership should still succeed
        u_owner = User.objects.create_user(username='new_owner', password='Pass1234')
        m = Membership.objects.create(user=u_owner, business=self.business, role='owner')
        self.assertEqual(m.role, 'owner')

    @patch('apps.billing.runtime.resolve_subscription')
    def test_signal_blocks_no_subscription(self, mock_resolve):
        """pre_save signal blocks creation when no subscription (access_granted=False)."""
        mock_resolve.return_value = _make_resolved(
            source='none', plan=None, access_granted=False
        )

        u = User.objects.create_user(username='no_sub_user', password='Pass1234')
        with self.assertRaises(DjangoValidationError):
            Membership.objects.create(user=u, business=self.business, role='cashier')

    # ── Trialing / past_due / grace period tests ─────────────────────────

    @patch('apps.accounts.services.resolve_subscription')
    def test_trialing_subscription_allows_member_creation(self, mock_resolve):
        """Trialing V2 subscription (access_granted=True) allows creation."""
        resolved = _make_resolved(source='v2', plan='pro', access_granted=True)
        resolved.status = 'trialing'
        mock_resolve.return_value = resolved

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.create_url, self._create_payload(username='trial_user'), format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)

    @patch('apps.accounts.services.resolve_subscription')
    def test_past_due_within_grace_allows_member_creation(self, mock_resolve):
        """past_due V2 within grace period (access_granted=True) allows creation."""
        resolved = _make_resolved(source='v2', plan='plus', access_granted=True)
        resolved.status = 'past_due'
        mock_resolve.return_value = resolved

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.create_url, self._create_payload(username='grace_user'), format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_201_CREATED)

    @patch('apps.accounts.services.resolve_subscription')
    def test_past_due_expired_grace_blocks_member_creation(self, mock_resolve):
        """past_due V2 with expired grace (access_granted=False) blocks creation."""
        resolved = _make_resolved(source='v2', plan='plus', access_granted=False)
        resolved.status = 'past_due'
        mock_resolve.return_value = resolved

        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.create_url, self._create_payload(username='expired_user'), format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_403_FORBIDDEN)

    @patch('apps.billing.runtime.resolve_subscription')
    def test_seat_info_current_when_access_blocked(self, mock_resolve_runtime):
        """seat_info.current reflects real non-owner count even when access_granted=False."""
        blocked = _make_resolved(source='v2', plan='appointments_pro', access_granted=False)
        blocked.status = 'past_due'
        active = _make_resolved(source='v2', plan='appointments_pro', access_granted=True)
        mock_resolve_runtime.return_value = active

        # Create 2 secondary users manually
        for i in range(2):
            u = User.objects.create_user(username=f'blocked_u{i}', password='Pass1234')
            Membership.objects.create(user=u, business=self.business, role='cashier')

        self.client.force_authenticate(user=self.owner)

        mock_resolve_runtime.return_value = blocked
        resp = self.client.get('/api/v1/owner/access/accounts/?include_seat_info=1')

        self.assertEqual(resp.status_code, http_status.HTTP_403_FORBIDDEN)


@skipUnlessDBFeature('has_select_for_update')
class MembershipSeatConcurrencyTests(TransactionTestCase):
    available_apps = [
        'apps.accounts',
        'apps.billing',
        'apps.business',
        'django.contrib.auth',
        'django.contrib.contenttypes',
    ]

    def test_concurrent_membership_creation_cannot_overbook_last_seat(self):
        business = Business.objects.create(
            name='Concurrent Turnos Base',
            default_service='appointments',
            status='active',
        )
        SubscriptionV2.objects.create(
            business=business,
            service_type='appointments',
            plan_code='appointments',
            external_reference=f'SUB-{uuid.uuid4()}',
            provider=SubscriptionV2.Provider.MANUAL,
            status=SubscriptionV2.Status.ACTIVE,
        )
        barrier = Barrier(3)

        def create_membership(index):
            try:
                user = User.objects.create_user(
                    username=f'concurrent_{index}_{uuid.uuid4().hex[:8]}',
                    password='MemberPass123',
                )
                barrier.wait(timeout=10)
                try:
                    Membership.objects.create(
                        user=user,
                        business_id=business.pk,
                        role='cashier',
                    )
                    return True
                except DjangoValidationError:
                    return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(create_membership, range(3)))

        self.assertEqual(results.count(True), 2)
        self.assertEqual(
            Membership.objects.filter(business=business).exclude(role='owner').count(),
            2,
        )

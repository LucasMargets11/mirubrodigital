"""
Bloque 21 — End-to-end lifecycle tests for QR de Reseñas.

Covers cross-module integration scenarios that exercise the full product
lifecycle: entitlements ↔ public flow ↔ notifications ↔ digest ↔ stats ↔
billing upgrade/downgrade.

Each test class simulates a realistic user journey through multiple API
calls, asserting coherent state at each step.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.billing.models import PendingSubscriptionChange, SubscriptionV2
from apps.billing.reviews_views import apply_reviews_plan_downgrade, apply_reviews_plan_upgrade
from apps.billing.views import MercadoPagoWebhookView
from apps.business.models import Business, Subscription

from ..digest import compute_digest_stats, send_digest_for_business
from ..entitlements import is_reviews_pro, reviews_allowed, smart_filter_allowed, trial_active, trial_available
from ..models import Review, ReviewConfig, ReviewMode, ReviewVisit

User = get_user_model()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _user(email='owner@test.com'):
    return User.objects.create_user(email=email, username=email, password='test1234')


def _business(owner, *, plan='qr_reviews_base', slug='e2e-biz'):
    biz = Business.objects.create(name='E2E Biz', slug=slug, default_service='qr_reviews')
    Subscription.objects.create(business=biz, plan=plan, service='qr_reviews', status='active')
    Membership.objects.create(user=owner, business=biz, role='owner', status='active')
    return biz


def _cfg(business, **overrides):
    defaults = dict(
        enabled=True,
        google_place_id='ChIJtest',
        redirect_threshold=4,
        thank_you_message='¡Gracias!',
        mode='direct',
    )
    defaults.update(overrides)
    return ReviewConfig.objects.create(business=business, **defaults)


def _client(user) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _submit(client, slug, rating, *, remote_addr='127.0.0.1', **extra):
    payload = {'rating': rating, **extra}
    return client.post(
        f'/api/v1/reviews/public/{slug}/submit/',
        payload,
        format='json',
        REMOTE_ADDR=remote_addr,
    )


def _landing(client, slug):
    return client.get(f'/api/v1/reviews/public/{slug}/')


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Base plan → full direct mode lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class BaseDirectLifecycleTests(TestCase):
    """
    Base plan with mode=direct: every rating redirects, no Review is ever
    created, no notifications fire, digest has nothing to send.
    """

    def setUp(self):
        cache.clear()
        self.owner = _user('base-direct@test.com')
        self.biz = _business(self.owner, plan='qr_reviews_base', slug='base-direct')
        self.config = _cfg(self.biz, mode='direct')
        self.api = APIClient()  # anonymous for public endpoints
        self.auth = _client(self.owner)

    def test_landing_returns_direct_mode(self):
        res = _landing(self.api, 'base-direct')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['effective_mode'], 'direct')

    def test_all_ratings_redirect_no_review_created(self):
        """Every rating 1-5 returns redirect action, zero Reviews stored."""
        for rating in range(1, 6):
            res = _submit(self.api, 'base-direct', rating)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.data['action'], 'redirect')

        self.assertEqual(Review.objects.filter(business=self.biz).count(), 0)

    @patch('apps.accounts.admin_notification_service.create_admin_notification')
    def test_no_notifications_sent(self, mock_helper):
        """Direct mode never creates Review → signal never fires notification."""
        _submit(self.api, 'base-direct', 1)
        mock_helper.assert_not_called()

    def test_stats_show_visits_but_no_reviews(self):
        """Stats reflect visits from landing but zero reviews."""
        with patch('apps.reviews.views.hash_ip', return_value='visit-ip-0'):
            _landing(self.api, 'base-direct')
        with patch('apps.reviews.views.hash_ip', return_value='visit-ip-1'):
            _landing(self.api, 'base-direct')

        res = self.auth.get('/api/v1/reviews/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['total_reviews'], 0)
        self.assertEqual(res.data['total_visits'], 2)

    def test_digest_returns_none_for_base(self):
        """Base plan is not eligible for digest (no smart_filter_allowed)."""
        _landing(self.api, 'base-direct')  # create a visit
        # send_digest_for_business checks smart_filter_allowed first.
        result = send_digest_for_business(self.biz)
        self.assertFalse(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Pro plan → smart_filter full lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ProSmartFilterLifecycleTests(TestCase):
    """
    Pro plan with mode=smart_filter: high ratings redirect, low ratings
    create internal Review, notification fires, digest picks it up, stats
    reflect everything, status pipeline works.
    """

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        patcher = patch('apps.accounts.admin_notification_service.create_admin_notification', return_value=None)
        self.mock_notif = patcher.start()
        self.addCleanup(patcher.stop)
        self.owner = _user('pro-sf@test.com')
        self.biz = _business(self.owner, plan='qr_reviews_pro', slug='pro-sf')
        self.config = _cfg(self.biz, mode='smart_filter')
        self.api = APIClient()
        self.auth = _client(self.owner)

    def tearDown(self):
        cache.clear()

    def test_landing_returns_smart_filter_mode(self):
        res = _landing(self.api, 'pro-sf')
        self.assertEqual(res.data['effective_mode'], 'smart_filter')
        self.assertTrue(res.data['is_pro'])

    def test_high_rating_redirects_no_review(self):
        res = _submit(self.api, 'pro-sf', 5)
        self.assertEqual(res.data['action'], 'redirect')
        self.assertEqual(Review.objects.filter(business=self.biz).count(), 0)

    def test_low_rating_creates_review_and_notifies(self):
        """Low rating creates Review + triggers email notification."""
        mail.outbox.clear()
        res = _submit(self.api, 'pro-sf', 2, comment='Malo')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['action'], 'submitted')

        review = Review.objects.get(business=self.biz)
        self.assertEqual(review.rating, 2)
        self.assertEqual(review.comment, 'Malo')
        self.assertEqual(review.status, 'new')

        # Admin notification queued for support team
        self.mock_notif.assert_called_once()

    def test_full_status_pipeline(self):
        """new → read → contacted → resolved → read (reopen)."""
        _submit(self.api, 'pro-sf', 1)
        review = Review.objects.get(business=self.biz)

        transitions = ['read', 'contacted', 'resolved', 'read']
        for new_status in transitions:
            res = self.auth.patch(
                f'/api/v1/reviews/{review.id}/',
                {'status': new_status},
                format='json',
            )
            self.assertEqual(res.status_code, 200, f'Failed transition to {new_status}')
            review.refresh_from_db()
            self.assertEqual(review.status, new_status)

    def test_stats_reflect_mixed_submissions(self):
        """Stats correctly count redirects (visits only) and stored reviews."""
        _landing(self.api, 'pro-sf')
        _submit(self.api, 'pro-sf', 5)                          # redirect
        _submit(self.api, 'pro-sf', 2, remote_addr='10.0.0.1')  # stored
        _submit(self.api, 'pro-sf', 1, remote_addr='10.0.0.2')  # stored

        res = self.auth.get('/api/v1/reviews/stats/')
        self.assertEqual(res.data['total_visits'], 1)     # only landing creates visit
        self.assertEqual(res.data['total_reviews'], 2)
        self.assertEqual(res.data['positive_reviews'], 0)  # both < threshold(4)
        self.assertEqual(res.data['negative_reviews'], 2)
        self.assertEqual(res.data['new_reviews'], 2)

    def test_stats_cache_invalidated_on_status_change(self):
        """Stats cache is invalidated when a review status changes."""
        _submit(self.api, 'pro-sf', 2)
        review = Review.objects.get(business=self.biz)

        # First call populates cache
        res1 = self.auth.get('/api/v1/reviews/stats/')
        self.assertEqual(res1.data['new_reviews'], 1)

        # Transition → read
        self.auth.patch(f'/api/v1/reviews/{review.id}/', {'status': 'read'}, format='json')

        # Stats should reflect change (cache was invalidated)
        res2 = self.auth.get('/api/v1/reviews/stats/')
        self.assertEqual(res2.data['new_reviews'], 0)

    def test_digest_picks_up_recent_activity(self):
        """Weekly digest computation reflects reviews created this week."""
        _landing(self.api, 'pro-sf')
        _submit(self.api, 'pro-sf', 1)

        stats = compute_digest_stats(self.biz)
        self.assertIsNotNone(stats)
        self.assertEqual(stats['new_reviews'], 1)
        self.assertEqual(stats['visits'], 1)

    def test_list_filters_work_after_submissions(self):
        """Review list endpoint filters correctly after multiple submissions."""
        _submit(self.api, 'pro-sf', 2, remote_addr='10.0.0.1')
        _submit(self.api, 'pro-sf', 3, remote_addr='10.0.0.2')

        # Filter by rating
        res = self.auth.get('/api/v1/reviews/', {'rating': 2})
        self.assertEqual(len(res.data), 1)

        # Filter by status
        res = self.auth.get('/api/v1/reviews/', {'status': 'new'})
        self.assertEqual(len(res.data), 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Trial lifecycle: activation → smart_filter → expiry → fallback
# ═══════════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TrialLifecycleTests(TestCase):
    """
    Base plan → activate trial → submit low rating (feedback created) →
    trial expires → same submit now redirects → upgrade recovers.
    """

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        patcher = patch('apps.accounts.admin_notification_service.create_admin_notification', return_value=None)
        self.mock_notif = patcher.start()
        self.addCleanup(patcher.stop)
        self.owner = _user('trial-life@test.com')
        self.biz = _business(self.owner, plan='qr_reviews_base', slug='trial-life')
        self.config = _cfg(self.biz, mode='direct')
        self.api = APIClient()
        self.auth = _client(self.owner)

    def tearDown(self):
        cache.clear()

    def test_trial_available_before_activation(self):
        self.assertTrue(trial_available(self.biz))
        self.assertFalse(trial_active(self.biz))

    def test_activate_trial_switches_to_smart_filter(self):
        res = self.auth.post('/api/v1/reviews/trial/activate/')
        self.assertEqual(res.status_code, 200)

        self.config.refresh_from_db()
        self.assertEqual(self.config.mode, 'smart_filter')
        self.assertTrue(self.config.trial_used)
        self.assertIsNotNone(self.config.trial_ends_at)
        self.assertTrue(trial_active(self.biz))
        self.assertFalse(trial_available(self.biz))

    def test_submit_during_active_trial_creates_feedback(self):
        """Active trial allows smart_filter → low rating creates Review."""
        self.auth.post('/api/v1/reviews/trial/activate/')

        mail.outbox.clear()
        res = _submit(self.api, 'trial-life', 2, comment='During trial')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['action'], 'submitted')

        review = Review.objects.get(business=self.biz)
        self.assertEqual(review.rating, 2)

        # Admin notification queued for support team (smart_filter_allowed = True)
        self.mock_notif.assert_called_once()

    def test_expired_trial_falls_back_to_direct(self):
        """After trial expires, effective_mode=direct → all ratings redirect."""
        self.auth.post('/api/v1/reviews/trial/activate/')

        # Expire the trial
        self.config.refresh_from_db()
        self.config.trial_ends_at = timezone.now() - timedelta(hours=1)
        self.config.save(update_fields=['trial_ends_at'])

        self.assertFalse(trial_active(self.biz))
        self.config.refresh_from_db()
        self.assertEqual(self.config.effective_mode, 'direct')

        # Submit now redirects even for low rating
        res = _submit(self.api, 'trial-life', 1)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['action'], 'redirect')

    def test_cannot_reactivate_trial(self):
        """Trial can only be used once."""
        self.auth.post('/api/v1/reviews/trial/activate/')

        # Expire it
        self.config.refresh_from_db()
        self.config.trial_ends_at = timezone.now() - timedelta(hours=1)
        self.config.save(update_fields=['trial_ends_at'])

        # Try again
        res = self.auth.post('/api/v1/reviews/trial/activate/')
        self.assertEqual(res.status_code, 409)

    def test_trial_not_available_for_pro(self):
        """Pro plan gets 409 — they already have smart_filter."""
        sub = self.biz.subscription
        sub.plan = 'qr_reviews_pro'
        sub.save()

        res = self.auth.post('/api/v1/reviews/trial/activate/')
        self.assertEqual(res.status_code, 409)

    def test_data_survives_trial_expiry(self):
        """Reviews created during trial are still visible after expiry."""
        self.auth.post('/api/v1/reviews/trial/activate/')
        _submit(self.api, 'trial-life', 2, comment='Trial feedback')

        # Expire trial
        self.config.refresh_from_db()
        self.config.trial_ends_at = timezone.now() - timedelta(hours=1)
        self.config.save(update_fields=['trial_ends_at'])

        # Reviews still accessible via stats and list
        res = self.auth.get('/api/v1/reviews/stats/')
        self.assertEqual(res.data['total_reviews'], 1)

        res = self.auth.get('/api/v1/reviews/')
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['comment'], 'Trial feedback')


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Upgrade Base → Pro: entitlements + public flow verify
# ═══════════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class UpgradeLifecycleTests(TestCase):
    """
    Base plan → upgrade to Pro → smart_filter now works → notifications fire.
    """

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        patcher = patch('apps.accounts.admin_notification_service.create_admin_notification', return_value=None)
        self.mock_notif = patcher.start()
        self.addCleanup(patcher.stop)
        self.owner = _user('upgrade-life@test.com')
        self.biz = _business(self.owner, plan='qr_reviews_base', slug='upgrade-life')
        self.config = _cfg(self.biz, mode='smart_filter')
        self.api = APIClient()
        self.auth = _client(self.owner)

    def tearDown(self):
        cache.clear()

    def test_before_upgrade_effective_mode_is_direct(self):
        """Base plan with mode=smart_filter → effective_mode=direct."""
        self.assertEqual(self.config.effective_mode, 'direct')
        self.assertFalse(is_reviews_pro(self.biz))
        self.assertFalse(smart_filter_allowed(self.biz))

    def test_submit_before_upgrade_redirects(self):
        res = _submit(self.api, 'upgrade-life', 1)
        self.assertEqual(res.data['action'], 'redirect')
        self.assertEqual(Review.objects.filter(business=self.biz).count(), 0)

    def test_after_upgrade_smart_filter_works(self):
        """apply_reviews_plan_upgrade → smart_filter is now effective."""
        apply_reviews_plan_upgrade(self.biz, 'qr_reviews_pro')

        self.biz.subscription.refresh_from_db()
        self.assertTrue(is_reviews_pro(self.biz))
        self.assertTrue(smart_filter_allowed(self.biz))
        self.config.refresh_from_db()
        self.assertEqual(self.config.effective_mode, 'smart_filter')

    def test_submit_after_upgrade_creates_feedback(self):
        apply_reviews_plan_upgrade(self.biz, 'qr_reviews_pro')

        mail.outbox.clear()
        res = _submit(self.api, 'upgrade-life', 2, comment='After upgrade')
        self.assertEqual(res.status_code, 201)

        review = Review.objects.get(business=self.biz)
        self.assertEqual(review.comment, 'After upgrade')

        # Admin notification queued for support team
        self.mock_notif.assert_called_once()

    def test_stats_reflect_pre_and_post_upgrade(self):
        """Landing before upgrade + review after upgrade → stats coherent."""
        _landing(self.api, 'upgrade-life')  # visit #1

        apply_reviews_plan_upgrade(self.biz, 'qr_reviews_pro')
        cache.clear()  # stats cache uses old plan

        _submit(self.api, 'upgrade-life', 2)  # creates review

        res = self.auth.get('/api/v1/reviews/stats/')
        self.assertEqual(res.data['total_visits'], 1)
        self.assertEqual(res.data['total_reviews'], 1)

    def test_upgrade_during_active_trial(self):
        """Upgrade while trial is active → Pro entitlements take over, trial irrelevant."""
        # Activate trial first
        self.auth.post('/api/v1/reviews/trial/activate/')
        self.config.refresh_from_db()
        self.assertTrue(trial_active(self.biz))

        # Upgrade
        apply_reviews_plan_upgrade(self.biz, 'qr_reviews_pro')

        # Pro entitlement active, trial still technically "active" but irrelevant
        self.assertTrue(is_reviews_pro(self.biz))
        self.assertTrue(smart_filter_allowed(self.biz))

        # Submit works
        res = _submit(self.api, 'upgrade-life', 2)
        self.assertEqual(res.status_code, 201)

    @patch('apps.billing.views.MercadoPagoService')
    def test_webhook_reviews_upgrade_idempotent_double_fire(self, MockMPService):
        """Double-fire of an approved reviews_upgrade webhook must be skipped the second time."""
        pending = PendingSubscriptionChange.objects.create(
            business=self.biz,
            user=self.owner,
            target_plan_code='qr_reviews_pro',
            billing_cycle='monthly',
            total_amount=0,
            is_upgrade=True,
            status='pending_payment',
        )
        MockMPService.return_value.get_payment.return_value = {
            'external_reference': f'reviews_upgrade_{pending.id}',
            'status': 'approved',
        }

        view = MercadoPagoWebhookView()

        # First fire → applies upgrade
        view.process_payment_event(payment_id='pay-idempotent-001')

        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed')
        self.biz.subscription.refresh_from_db()
        self.assertEqual(self.biz.subscription.plan, 'qr_reviews_pro')

        v2_count = SubscriptionV2.objects.filter(business=self.biz, service_type='qr_reviews').count()

        # Second fire → must be skipped due to idempotency guard
        view.process_payment_event(payment_id='pay-idempotent-001')

        pending.refresh_from_db()
        self.assertEqual(pending.status, 'completed', "Status must remain completed after second webhook")

        v2_count_after = SubscriptionV2.objects.filter(business=self.biz, service_type='qr_reviews').count()
        self.assertEqual(v2_count, v2_count_after, "No duplicate SubscriptionV2 must be created")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Downgrade Pro → Base: entitlements + public flow + data preservation
# ═══════════════════════════════════════════════════════════════════════════════

class DowngradeLifecycleTests(TestCase):
    """
    Pro plan with reviews → downgrade to Base → effective_mode falls back
    to direct, existing data preserved, new submissions redirect.
    """

    def setUp(self):
        cache.clear()
        self.owner = _user('downgrade-life@test.com')
        self.biz = _business(self.owner, plan='qr_reviews_pro', slug='downgrade-life')
        self.config = _cfg(self.biz, mode='smart_filter')
        self.api = APIClient()
        self.auth = _client(self.owner)

    def tearDown(self):
        cache.clear()

    def test_before_downgrade_smart_filter_works(self):
        res = _submit(self.api, 'downgrade-life', 2)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Review.objects.filter(business=self.biz).count(), 1)

    def test_after_downgrade_effective_mode_is_direct(self):
        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)

        self.biz.subscription.refresh_from_db()
        self.assertFalse(is_reviews_pro(self.biz))
        self.assertFalse(smart_filter_allowed(self.biz))
        self.config.refresh_from_db()
        self.assertEqual(self.config.effective_mode, 'direct')
        # mode field is NOT changed by downgrade — only effective_mode changes
        self.assertEqual(self.config.mode, 'smart_filter')

    def test_submit_after_downgrade_redirects(self):
        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)

        res = _submit(self.api, 'downgrade-life', 1)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['action'], 'redirect')

    def test_existing_reviews_survive_downgrade(self):
        """Reviews created pre-downgrade are still accessible."""
        _submit(self.api, 'downgrade-life', 2, comment='Before downgrade')
        self.assertEqual(Review.objects.filter(business=self.biz).count(), 1)

        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)
        cache.clear()

        # Still in stats
        res = self.auth.get('/api/v1/reviews/stats/')
        self.assertEqual(res.data['total_reviews'], 1)

        # Still in list
        res = self.auth.get('/api/v1/reviews/')
        self.assertEqual(len(res.data), 1)

    def test_downgrade_creates_audit_record(self):
        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)

        record = PendingSubscriptionChange.objects.filter(
            business=self.biz, is_downgrade=True, status='completed'
        ).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.config_snapshot['previous_plan'], 'qr_reviews_pro')

    def test_pending_feedback_survives_downgrade(self):
        """Feedback with status=new or contacted survives downgrade intact."""
        _submit(self.api, 'downgrade-life', 2, comment='Pending')
        review = Review.objects.get(business=self.biz)
        self.auth.patch(f'/api/v1/reviews/{review.id}/', {'status': 'read'}, format='json')
        self.auth.patch(f'/api/v1/reviews/{review.id}/', {'status': 'contacted'}, format='json')

        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)

        review.refresh_from_db()
        self.assertEqual(review.status, 'contacted')
        self.assertEqual(review.comment, 'Pending')


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Cross-module: notifications + digest coherence
# ═══════════════════════════════════════════════════════════════════════════════

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class NotificationsDigestCoherenceTests(TestCase):
    """
    Validate that immediate notification and weekly digest are coherent:
    - Same review triggers both (if eligible)
    - Throttle applies to immediate but not digest
    - Digest skips ineligible plans
    - Digest counts only recent reviews
    """

    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        patcher = patch('apps.accounts.admin_notification_service.create_admin_notification', return_value=None)
        self.mock_notif = patcher.start()
        self.addCleanup(patcher.stop)
        self.owner = _user('notif-digest@test.com')
        self.biz = _business(self.owner, plan='qr_reviews_pro', slug='notif-digest')
        self.config = _cfg(self.biz, mode='smart_filter')
        self.api = APIClient()

    def tearDown(self):
        cache.clear()

    def test_single_review_triggers_notification_and_appears_in_digest(self):
        """One submission → 1 email immediately + counts in digest stats."""
        mail.outbox.clear()
        _submit(self.api, 'notif-digest', 2, comment='Test')

        # Admin notification queued for support team
        self.mock_notif.assert_called_once()

        # Digest sees it
        stats = compute_digest_stats(self.biz)
        self.assertIsNotNone(stats)
        self.assertEqual(stats['new_reviews'], 1)
        self.assertEqual(stats['negative_count'], 1)

    def test_notification_throttle_does_not_affect_digest(self):
        """Multiple reviews each trigger in-app notification, and digest counts all."""
        mail.outbox.clear()
        _submit(self.api, 'notif-digest', 1, remote_addr='10.0.0.1')
        _submit(self.api, 'notif-digest', 2, remote_addr='10.0.0.2')
        _submit(self.api, 'notif-digest', 3, remote_addr='10.0.0.3')

        # In-app notification called for each negative review (no throttle)
        self.assertEqual(self.mock_notif.call_count, 3)

        # Digest: counts all 3
        stats = compute_digest_stats(self.biz)
        self.assertEqual(stats['new_reviews'], 3)

    def test_digest_skips_after_downgrade(self):
        """After downgrade, digest returns False (not eligible)."""
        _submit(self.api, 'notif-digest', 2)  # creates review while Pro

        apply_reviews_plan_downgrade(self.biz, 'qr_reviews_base', user=self.owner)

        result = send_digest_for_business(self.biz)
        self.assertFalse(result)

    def test_digest_only_counts_recent_reviews(self):
        """Reviews older than window are not counted in digest."""
        _submit(self.api, 'notif-digest', 2)
        review = Review.objects.get(business=self.biz)

        # Age the review beyond 7 days
        Review.objects.filter(pk=review.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )

        stats = compute_digest_stats(self.biz)
        # No recent reviews → None (unread is all-time, but new_reviews counts recent)
        if stats is not None:
            self.assertEqual(stats['new_reviews'], 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Edge cases & hardening
# ═══════════════════════════════════════════════════════════════════════════════

class EdgeCaseHardeningTests(TestCase):
    """
    Exercises edge cases that could lead to inconsistent state.
    """

    def setUp(self):
        cache.clear()
        self.owner = _user('edge@test.com')
        self.api = APIClient()

    def tearDown(self):
        cache.clear()

    def test_submit_without_redirect_url(self):
        """
        Config has no Google URL → redirect_url is None.
        In direct mode, redirect_url=None in response (frontend handles gracefully).
        """
        biz = Business.objects.create(name='No URL Biz', slug='no-url', default_service='qr_reviews')
        Subscription.objects.create(business=biz, plan='qr_reviews_base', service='qr_reviews', status='active')
        ReviewConfig.objects.create(
            business=biz,
            enabled=True,
            mode='direct',
            redirect_threshold=4,
            # No google_place_id, no google_review_url, no custom_redirect_url
        )

        res = _submit(self.api, 'no-url', 5)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['action'], 'redirect')
        self.assertIsNone(res.data['redirect_url'])

    def test_disabled_config_blocks_landing_and_submit(self):
        """disabled config → 404 on landing, 403 on submit."""
        biz = Business.objects.create(name='Disabled Biz', slug='disabled', default_service='qr_reviews')
        Subscription.objects.create(business=biz, plan='qr_reviews_base', service='qr_reviews', status='active')
        ReviewConfig.objects.create(business=biz, enabled=False, mode='direct')

        res = _landing(self.api, 'disabled')
        self.assertEqual(res.status_code, 404)

        res = _submit(self.api, 'disabled', 3)
        self.assertEqual(res.status_code, 403)

    def test_no_config_blocks_landing(self):
        """No ReviewConfig → landing returns 404."""
        biz = Business.objects.create(name='No Config', slug='no-config', default_service='qr_reviews')
        Subscription.objects.create(business=biz, plan='qr_reviews_base', service='qr_reviews', status='active')

        res = _landing(self.api, 'no-config')
        self.assertEqual(res.status_code, 404)

    def test_inactive_subscription_blocks_landing(self):
        """Inactive subscription → reviews_allowed=False → 404."""
        biz = Business.objects.create(name='Inactive Sub', slug='inactive-sub', default_service='qr_reviews')
        Subscription.objects.create(business=biz, plan='qr_reviews_base', service='qr_reviews', status='inactive')
        ReviewConfig.objects.create(business=biz, enabled=True, mode='direct', google_place_id='ChIJ')

        res = _landing(self.api, 'inactive-sub')
        self.assertEqual(res.status_code, 404)

    def test_dedup_across_mode_change(self):
        """
        Submit in smart_filter (creates review) → mode changes to direct →
        dedup should not affect direct mode (which never checks dedup).
        """
        biz = Business.objects.create(name='Dedup Biz', slug='dedup', default_service='qr_reviews')
        Subscription.objects.create(business=biz, plan='qr_reviews_pro', service='qr_reviews', status='active')
        config = ReviewConfig.objects.create(
            business=biz, enabled=True, mode='smart_filter',
            redirect_threshold=4, google_place_id='ChIJ',
        )

        # Submit low rating → stored
        res = _submit(self.api, 'dedup', 2)
        self.assertEqual(res.status_code, 201)

        # Switch to direct mode
        config.mode = 'direct'
        config.save(update_fields=['mode'])

        # Submit again → direct mode redirects regardless (no dedup check)
        res = _submit(self.api, 'dedup', 2)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['action'], 'redirect')

    def test_config_patch_validates_threshold_range(self):
        """Config PATCH rejects threshold outside 1-5."""
        biz = Business.objects.create(name='Thresh Biz', slug='thresh', default_service='qr_reviews')
        Subscription.objects.create(business=biz, plan='qr_reviews_base', service='qr_reviews', status='active')
        ReviewConfig.objects.create(business=biz, enabled=True, mode='direct')
        Membership.objects.create(user=self.owner, business=biz, role='owner', status='active')
        auth = _client(self.owner)

        res = auth.patch('/api/v1/reviews/config/', {'redirect_threshold': 0}, format='json')
        self.assertEqual(res.status_code, 400)

        res = auth.patch('/api/v1/reviews/config/', {'redirect_threshold': 6}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_upgrade_downgrade_roundtrip_preserves_reviews(self):
        """Base → upgrade → create reviews → downgrade → reviews still exist."""
        biz = Business.objects.create(name='Roundtrip', slug='roundtrip', default_service='qr_reviews')
        Subscription.objects.create(business=biz, plan='qr_reviews_base', service='qr_reviews', status='active')
        ReviewConfig.objects.create(
            business=biz, enabled=True, mode='smart_filter',
            redirect_threshold=4, google_place_id='ChIJ',
        )
        Membership.objects.create(user=self.owner, business=biz, role='owner', status='active')

        # Upgrade
        apply_reviews_plan_upgrade(biz, 'qr_reviews_pro')
        _submit(self.api, 'roundtrip', 2, remote_addr='10.0.0.1', comment='Round 1')
        _submit(self.api, 'roundtrip', 3, remote_addr='10.0.0.2', comment='Round 2')

        self.assertEqual(Review.objects.filter(business=biz).count(), 2)

        # Downgrade
        apply_reviews_plan_downgrade(biz, 'qr_reviews_base', user=self.owner)

        # Reviews preserved
        self.assertEqual(Review.objects.filter(business=biz).count(), 2)

        # Submit now redirects (effective_mode → direct)
        res = _submit(self.api, 'roundtrip', 1, remote_addr='10.0.0.3')
        self.assertEqual(res.data['action'], 'redirect')

        # Re-upgrade
        apply_reviews_plan_upgrade(biz, 'qr_reviews_pro')

        # Smart filter works again + old reviews are still there
        res = _submit(self.api, 'roundtrip', 1, remote_addr='10.0.0.4', comment='Round 3')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Review.objects.filter(business=biz).count(), 3)

    def test_trial_expired_with_prior_data_and_then_upgrade(self):
        """
        base → trial → create feedback → trial expires → upgrade to Pro →
        old data accessible + smart_filter works again.
        """
        biz = Business.objects.create(name='TExp', slug='texp', default_service='qr_reviews')
        Subscription.objects.create(business=biz, plan='qr_reviews_base', service='qr_reviews', status='active')
        config = ReviewConfig.objects.create(
            business=biz, enabled=True, mode='smart_filter',
            redirect_threshold=4, google_place_id='ChIJ',
            trial_used=True,
            trial_ends_at=timezone.now() + timedelta(days=7),
        )

        # During trial: create feedback
        _submit(self.api, 'texp', 2, remote_addr='10.0.0.1', comment='Trial data')
        self.assertEqual(Review.objects.filter(business=biz).count(), 1)

        # Expire trial
        config.trial_ends_at = timezone.now() - timedelta(hours=1)
        config.save(update_fields=['trial_ends_at'])

        # Now redirects
        res = _submit(self.api, 'texp', 1, remote_addr='10.0.0.2')
        self.assertEqual(res.data['action'], 'redirect')

        # Upgrade to Pro
        apply_reviews_plan_upgrade(biz, 'qr_reviews_pro')

        # Smart filter works again
        res = _submit(self.api, 'texp', 1, remote_addr='10.0.0.3', comment='After Pro')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Review.objects.filter(business=biz).count(), 2)

    def test_v2_sync_created_on_upgrade_and_updated_on_downgrade(self):
        """SubscriptionV2 is created on upgrade and updated on downgrade."""
        biz = Business.objects.create(name='V2 Sync', slug='v2sync', default_service='qr_reviews')
        Subscription.objects.create(business=biz, plan='qr_reviews_base', service='qr_reviews', status='active')
        Membership.objects.create(user=self.owner, business=biz, role='owner', status='active')

        # No V2 initially
        self.assertEqual(
            SubscriptionV2.objects.filter(business=biz, service_type='qr_reviews').count(), 0
        )

        # Upgrade creates V2
        apply_reviews_plan_upgrade(biz, 'qr_reviews_pro')
        v2 = SubscriptionV2.objects.get(business=biz, service_type='qr_reviews')
        self.assertEqual(v2.plan_code, 'qr_reviews_pro')
        self.assertEqual(v2.status, SubscriptionV2.Status.ACTIVE)

        # Downgrade updates V2
        apply_reviews_plan_downgrade(biz, 'qr_reviews_base', user=self.owner)
        v2.refresh_from_db()
        self.assertEqual(v2.plan_code, 'qr_reviews_base')

    def test_multiple_rapid_submits_deduplicated(self):
        """Same IP within 10-min window is blocked after first Review."""
        biz = Business.objects.create(name='Rapid', slug='rapid', default_service='qr_reviews')
        Subscription.objects.create(business=biz, plan='qr_reviews_pro', service='qr_reviews', status='active')
        ReviewConfig.objects.create(
            business=biz, enabled=True, mode='smart_filter',
            redirect_threshold=4, google_place_id='ChIJ',
        )

        res1 = _submit(self.api, 'rapid', 2)
        self.assertEqual(res1.status_code, 201)

        res2 = _submit(self.api, 'rapid', 1)
        self.assertEqual(res2.status_code, 429)

        self.assertEqual(Review.objects.filter(business=biz).count(), 1)

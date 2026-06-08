"""
HOTFIX-RI-REVIEWS-CARTELES — unit tests for `print_posters_allowed`.

Carteles (printable QR posters) are granted to:
  • Standalone Pro (qr_reviews_pro).
  • Bundle plans that include Carteles (Restaurante Inteligente → 'plus').

Standalone Base (qr_reviews / qr_reviews_base) does NOT get Carteles.
"""
from __future__ import annotations

from django.test import TestCase

from apps.business.models import Business, Subscription

from ..entitlements import print_posters_allowed


def _make(plan: str, *, service: str, default_service: str, status: str = 'active') -> Business:
    biz = Business.objects.create(name=f'Biz {plan}', default_service=default_service)
    Subscription.objects.create(business=biz, plan=plan, service=service, status=status)
    return biz


class PrintPostersAllowedTests(TestCase):
    def test_qr_reviews_pro_standalone_allowed(self):
        biz = _make('qr_reviews_pro', service='qr_reviews', default_service='qr_reviews')
        self.assertTrue(print_posters_allowed(biz))

    def test_qr_reviews_base_standalone_denied(self):
        biz = _make('qr_reviews', service='qr_reviews', default_service='qr_reviews')
        self.assertFalse(print_posters_allowed(biz))

    def test_qr_reviews_base_explicit_denied(self):
        biz = _make('qr_reviews_base', service='qr_reviews', default_service='qr_reviews')
        self.assertFalse(print_posters_allowed(biz))

    def test_restaurante_inteligente_bundle_allowed(self):
        biz = _make('plus', service='restaurante', default_service='restaurante')
        self.assertTrue(print_posters_allowed(biz))

    def test_business_no_subscription_denied(self):
        biz = Business.objects.create(name='No sub', default_service='qr_reviews')
        self.assertFalse(print_posters_allowed(biz))

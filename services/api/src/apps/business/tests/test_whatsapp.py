"""WhatsApp público del Business (Slice 6D): normalización, URL wa.me y branding."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessBranding, BusinessPlan, Subscription
from apps.business.whatsapp import build_whatsapp_url, normalize_whatsapp_phone

User = get_user_model()
BRANDING_URL = '/api/v1/settings/branding/'


class NormalizeWhatsappPhoneTests(SimpleTestCase):
  def test_valid_inputs(self):
    cases = {
      '+54 9 11 1234-5678': '5491112345678',
      '+5491112345678': '5491112345678',
      '0054 9 11 1234 5678': '5491112345678',
      '54 11 1234 5678': '5491112345678',       # sin el 9 → se agrega (móvil AR)
      '011 1234-5678': '5491112345678',         # nacional con 0
      '(351) 456-7890': '5493514567890',        # nacional sin 0
      '+34 612 345 678': '34612345678',         # internacional no AR
    }
    for raw, expected in cases.items():
      with self.subTest(raw=raw):
        self.assertEqual(normalize_whatsapp_phone(raw), expected)

  def test_invalid_inputs(self):
    for raw in (
      None, '', '   ', 'abc', '11 15 1234 5678', '1234', '+0 123 456 789', '+54 11 1234',
      'javascript:alert(1)', 'https://wa.me/5491112345678', '+54+9111234567', '1' * 40,
      '612345678',  # nacional no AR: sin país no se adivina
    ):
      with self.subTest(raw=raw):
        self.assertIsNone(normalize_whatsapp_phone(raw))

  def test_national_non_ar_business_requires_international(self):
    self.assertIsNone(normalize_whatsapp_phone('11 1234 5678', country='UY'))
    self.assertEqual(normalize_whatsapp_phone('+598 94 123 456', country='UY'), '59894123456')


class BuildWhatsappUrlTests(SimpleTestCase):
  def test_only_wa_me_with_encoded_text(self):
    url = build_whatsapp_url('+5491112345678', 'Hola & chau? #1 / ñ')
    parts = urlsplit(url)
    self.assertEqual((parts.scheme, parts.netloc, parts.path), ('https', 'wa.me', '/5491112345678'))
    self.assertEqual(parse_qs(parts.query)['text'], ['Hola & chau? #1 / ñ'])
    self.assertNotIn(' ', url)
    self.assertNotIn('#', url)

  def test_invalid_phone_or_empty_text_gives_none(self):
    self.assertIsNone(build_whatsapp_url('javascript:alert(1)', 'Hola'))
    self.assertIsNone(build_whatsapp_url('', 'Hola'))
    self.assertIsNone(build_whatsapp_url('+5491112345678', ''))


class BrandingWhatsappFieldTests(APITestCase):
  def setUp(self):
    self.biz = Business.objects.create(name='Barbería', default_service='appointments', slug='barberia-wa')
    Subscription.objects.create(business=self.biz, plan=BusinessPlan.APPOINTMENTS_BASE, service='appointments', status='active')
    BusinessBranding.objects.get_or_create(business=self.biz)
    user = User.objects.create_user(username='wa-owner', password='x')
    Membership.objects.create(user=user, business=self.biz, role='owner')
    self.client.force_authenticate(user=user)

  def test_owner_sets_normalized_whatsapp(self):
    res = self.client.patch(BRANDING_URL, {'whatsapp_phone': '11 1234-5678'}, format='json')
    self.assertEqual(res.status_code, 200, res.content)
    self.assertEqual(res.data['whatsapp_phone'], '+5491112345678')
    self.assertEqual(BusinessBranding.objects.get(business=self.biz).whatsapp_phone, '+5491112345678')

  def test_invalid_whatsapp_rejected(self):
    for raw in ('11 15 1234 5678', 'javascript:alert(1)', 'https://wa.me/549111'):
      with self.subTest(raw=raw):
        res = self.client.patch(BRANDING_URL, {'whatsapp_phone': raw}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('whatsapp_phone', res.data)
    self.assertEqual(BusinessBranding.objects.get(business=self.biz).whatsapp_phone, '')

  def test_blank_clears(self):
    BusinessBranding.objects.filter(business=self.biz).update(whatsapp_phone='+5491112345678')
    res = self.client.patch(BRANDING_URL, {'whatsapp_phone': ''}, format='json')
    self.assertEqual(res.status_code, 200, res.content)
    self.assertEqual(BusinessBranding.objects.get(business=self.biz).whatsapp_phone, '')

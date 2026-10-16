"""Slice 7B.4: página pública de reservas visible desde el panel.

La sesión (`/api/v1/auth/me/`) expone `current.business.public_booking`
derivado de la misma regla que el backend público (`_resolve_public_business`).
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.access import BUSINESS_COOKIE_NAME
from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription

from ..public_page import public_booking_snapshot, public_booking_unavailable_reason
from ..public_views import _resolve_public_business

User = get_user_model()

ME_URL = '/api/v1/auth/me/'


def _business(name, slug, *, status='active', service='appointments'):
  biz = Business.objects.create(name=name, default_service=service, slug=slug, status=status)
  Subscription.objects.create(
    business=biz,
    plan=BusinessPlan.APPOINTMENTS_BASE if service == 'appointments' else BusinessPlan.START,
    service=service,
    status='active',
  )
  return biz


@override_settings(PUBLIC_MENU_BASE_URL='https://app.example.test', FRONTEND_URL='https://ignored.example.test')
class PublicBookingSessionTests(APITestCase):
  def setUp(self):
    self.biz = _business('Peluquería Sol', 'peluqueria-sol')
    self.other = _business('Otro Negocio', 'otro-negocio')
    self.user = User.objects.create_user(username='owner-sol', email='owner@sol.test', password='x')
    Membership.objects.create(user=self.user, business=self.biz, role='owner')

  def _me(self, user=None, business=None):
    self.client.force_authenticate(user or self.user)
    self.client.cookies[BUSINESS_COOKIE_NAME] = str((business or self.biz).id)
    resp = self.client.get(ME_URL)
    self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
    return resp.data['current']['business']['public_booking']

  def test_available_business_exposes_canonical_url(self):
    data = self._me()
    self.assertEqual(data, {
      'available': True,
      'url': 'https://app.example.test/t/peluqueria-sol',
      'reason': None,
    })

  def test_url_only_contains_slug_no_ids(self):
    url = self._me()['url']
    self.assertTrue(url.endswith('/t/peluqueria-sol'))
    self.assertNotIn(str(self.biz.id), url.replace('peluqueria-sol', ''))
    self.assertNotIn('?', url)

  def test_manager_sees_same_link(self):
    manager = User.objects.create_user(username='mgr-sol', email='mgr@sol.test', password='x')
    Membership.objects.create(user=manager, business=self.biz, role='manager')
    self.assertEqual(self._me(user=manager)['url'], 'https://app.example.test/t/peluqueria-sol')

  def test_tenant_isolation_uses_current_membership_only(self):
    # Cookie apuntando a un Business sin membresía → se ignora, nunca se expone otro slug.
    data = self._me(business=self.other)
    self.assertEqual(data['url'], 'https://app.example.test/t/peluqueria-sol')

  def test_switch_between_own_businesses(self):
    Membership.objects.create(user=self.user, business=self.other, role='owner')
    self.assertEqual(self._me(business=self.other)['url'], 'https://app.example.test/t/otro-negocio')

  def test_not_publishable_business_has_no_url(self):
    Business.objects.filter(pk=self.biz.pk).update(status='suspended')
    data = self._me()
    self.assertEqual(data, {'available': False, 'url': None, 'reason': 'not_publishable'})

  def test_missing_slug_has_no_url(self):
    Business.objects.filter(pk=self.biz.pk).update(slug=None)
    data = self._me()
    self.assertEqual(data, {'available': False, 'url': None, 'reason': 'missing_slug'})

  def test_business_without_appointments_gets_null(self):
    menu_biz = _business('Resto', 'resto', service='gestion')
    Membership.objects.create(user=self.user, business=menu_biz, role='owner')
    self.assertIsNone(self._me(business=menu_biz))


@override_settings(PUBLIC_MENU_BASE_URL='', FRONTEND_URL='https://front.example.test/')
class PublicBookingRuleParityTests(APITestCase):
  """El panel y el endpoint público aplican exactamente la misma regla."""

  def test_panel_and_public_resolver_agree(self):
    cases = [
      _business('A', 'a-active'),
      _business('B', 'b-trial', status='trialing'),
      _business('C', 'c-pastdue', status='past_due'),
      _business('D', 'd-onboarding', status='onboarding'),
      _business('E', 'e-canceled', status='canceled'),
      _business('F', 'f-resto', service='gestion'),
    ]
    for biz in cases:
      with self.subTest(slug=biz.slug):
        snapshot = public_booking_snapshot(biz)
        self.assertEqual(snapshot['available'], _resolve_public_business(biz.slug) is not None)
        public = self.client.get(f'/api/v1/appointments/public/{biz.slug}/')
        self.assertEqual(snapshot['available'], public.status_code == status.HTTP_200_OK)

  def test_falls_back_to_frontend_url(self):
    biz = _business('G', 'g-biz')
    self.assertEqual(public_booking_snapshot(biz)['url'], 'https://front.example.test/t/g-biz')

  def test_reason_codes(self):
    self.assertEqual(public_booking_unavailable_reason(_business('H', 'h', status='suspended')), 'not_publishable')
    self.assertEqual(public_booking_unavailable_reason(_business('I', 'i', service='gestion')), 'service_disabled')

"""Slice 7D.1: la sesión expone `current.business.timezone` (solo lectura).

Es la misma zona canónica que usa el backend de Turnos
(`resolve_business_timezone`): `Business.timezone`, con fallback a
`settings.TIME_ZONE` si falta o es inválida.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.access import BUSINESS_COOKIE_NAME
from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

User = get_user_model()
ME_URL = '/api/v1/auth/me/'
SWITCH_URL = '/api/v1/auth/switch-business/'


def _business(name, tz):
  business = Business.objects.create(name=name, default_service='gestion', status='active', timezone=tz)
  Subscription.objects.create(business=business, plan='starter', status='active', max_seats=5)
  return business


class SessionBusinessTimezoneTests(TestCase):
  def setUp(self):
    self.biz_ar = _business('Biz AR', 'America/Argentina/Buenos_Aires')
    self.biz_es = _business('Biz ES', 'Europe/Madrid')
    self.user = User.objects.create_user(username='tz@test.com', email='tz@test.com', password='x')
    Membership.objects.create(user=self.user, business=self.biz_ar, role='owner')
    self.client = APIClient()
    self.client.force_authenticate(user=self.user)

  def me(self, business=None):
    if business is not None:
      self.client.cookies[BUSINESS_COOKIE_NAME] = str(business.pk)
    res = self.client.get(ME_URL)
    self.assertEqual(res.status_code, 200, res.content)
    return res.data

  # 1. expone la timezone del Business actual
  def test_exposes_current_business_timezone(self):
    self.assertEqual(self.me()['current']['business']['timezone'], 'America/Argentina/Buenos_Aires')

  # 2. cambiar de Business cambia la timezone
  def test_switching_business_changes_timezone(self):
    Membership.objects.create(user=self.user, business=self.biz_es, role='owner')
    self.assertEqual(self.me(self.biz_ar)['current']['business']['timezone'], 'America/Argentina/Buenos_Aires')
    self.assertEqual(self.me(self.biz_es)['current']['business']['timezone'], 'Europe/Madrid')
    res = self.client.post(SWITCH_URL, {'business_id': self.biz_ar.pk}, format='json')
    self.assertEqual(res.status_code, 200, res.content)
    self.assertEqual(res.data['current']['business']['timezone'], 'America/Argentina/Buenos_Aires')

  # 3. un Business ajeno no filtra su timezone
  def test_foreign_business_timezone_not_leaked(self):
    data = self.me(self.biz_es)  # cookie de un Business sin membresía → cae al propio
    self.assertEqual(data['current']['business']['id'], self.biz_ar.pk)
    self.assertEqual(data['current']['business']['timezone'], 'America/Argentina/Buenos_Aires')
    self.assertNotIn('Europe/Madrid', str(data))
    res = self.client.post(SWITCH_URL, {'business_id': self.biz_es.pk}, format='json')
    self.assertEqual(res.status_code, 404)
    self.assertNotIn('Europe/Madrid', res.content.decode())

  # 4. no se puede sobreescribir desde este endpoint
  def test_timezone_is_read_only(self):
    for method in (self.client.patch, self.client.put, self.client.post):
      res = method(ME_URL, {'current': {'business': {'timezone': 'Asia/Tokyo'}}, 'timezone': 'Asia/Tokyo'}, format='json')
      self.assertEqual(res.status_code, 405)
    self.biz_ar.refresh_from_db()
    self.assertEqual(self.biz_ar.timezone, 'America/Argentina/Buenos_Aires')
    self.assertEqual(self.me()['current']['business']['timezone'], 'America/Argentina/Buenos_Aires')

  # Fallback legacy: timezone vacía/inválida → settings.TIME_ZONE (nunca UTC).
  @override_settings(TIME_ZONE='America/Argentina/Buenos_Aires')
  def test_invalid_or_empty_timezone_falls_back_to_project_default(self):
    for legacy in ('', 'Not/AZone'):
      Business.objects.filter(pk=self.biz_ar.pk).update(timezone=legacy)
      with self.subTest(legacy=legacy):
        self.assertEqual(self.me()['current']['business']['timezone'], 'America/Argentina/Buenos_Aires')

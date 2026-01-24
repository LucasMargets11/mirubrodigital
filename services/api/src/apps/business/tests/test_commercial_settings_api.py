from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, CommercialSettings, Subscription


class CommercialSettingsAPITests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(
      username='manager',
      email='manager@example.com',
      password='testpass123',
    )

  def _bootstrap_business(self, role: str = 'manager') -> Business:
    business = Business.objects.create(name='Demo Biz')
    Subscription.objects.create(business=business, plan='starter', status='active')
    Membership.objects.create(user=self.user, business=business, role=role)
    self.client.force_authenticate(user=self.user)
    self.client.cookies['bid'] = str(business.id)
    return business

  def test_get_returns_defaults(self):
    business = self._bootstrap_business()
    url = reverse('business:commercial-settings')

    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    payload = response.data
    self.assertFalse(payload['allow_sell_without_stock'])
    self.assertTrue(payload['block_sales_if_no_open_cash_session'])
    self.assertTrue(payload['warn_on_low_stock_threshold_enabled'])
    self.assertEqual(payload['low_stock_threshold_default'], 5)

  def test_patch_updates_settings(self):
    business = self._bootstrap_business()
    url = reverse('business:commercial-settings')
    payload = {
      'allow_sell_without_stock': True,
      'low_stock_threshold_default': 10,
      'enable_sales_notes': False,
    }

    response = self.client.patch(url, payload, format='json')

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    data = response.data
    self.assertTrue(data['allow_sell_without_stock'])
    self.assertEqual(data['low_stock_threshold_default'], 10)
    self.assertFalse(data['enable_sales_notes'])

    settings = CommercialSettings.objects.for_business(business)
    self.assertTrue(settings.allow_sell_without_stock)
    self.assertEqual(settings.low_stock_threshold_default, 10)
    self.assertFalse(settings.enable_sales_notes)

  def test_permission_required_for_cashier_role(self):
    self._bootstrap_business(role='cashier')
    url = reverse('business:commercial-settings')

    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

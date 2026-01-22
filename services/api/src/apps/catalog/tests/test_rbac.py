from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription
from apps.catalog.models import Product


class CatalogRBACTests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(email='owner@example.com', password='pass1234')

  def _create_business(self, name: str, plan: str = 'starter') -> Business:
    business = Business.objects.create(name=name)
    Subscription.objects.create(business=business, plan=plan, status='active')
    return business

  def _authenticate(self, business: Business):
    self.client.force_authenticate(user=self.user)
    self.client.cookies['bid'] = str(business.id)

  def test_cross_tenant_access_denied(self):
    primary_business = self._create_business('Main Biz')
    other_business = self._create_business('Second Biz')
    Membership.objects.create(user=self.user, business=primary_business, role='owner')
    Membership.objects.create(user=self.user, business=other_business, role='owner')
    product = Product.objects.create(
      business=other_business,
      name='Producto ajeno',
      sku='SKU-1',
      barcode='111',
      cost=25,
      price=50,
    )

    self._authenticate(primary_business)
    url = reverse('catalog:product-detail', kwargs={'pk': product.pk})
    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

  def test_cost_hidden_without_manage_permission(self):
    business = self._create_business('Solo lectura')
    Membership.objects.create(user=self.user, business=business, role='viewer')
    Product.objects.create(
      business=business,
      name='Producto visible',
      sku='SKU-2',
      barcode='222',
      cost=99,
      price=120,
    )

    self._authenticate(business)
    url = reverse('catalog:product-list')
    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(isinstance(response.data, list))
    self.assertGreater(len(response.data), 0)
    self.assertNotIn('cost', response.data[0])

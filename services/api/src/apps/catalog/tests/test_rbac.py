from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription
from apps.catalog.models import Product
from apps.inventory.models import ProductStock, StockLocation


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

class PrimaryStockCatalogTests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(
      username='catalog-stock-reader',
      email='catalog-stock-reader@example.com',
      password='pass1234',
    )

  def _create_business(self, name: str) -> Business:
    business = Business.objects.create(name=name)
    Subscription.objects.create(business=business, plan='starter', status='active')
    return business

  def _authenticate(self, business: Business):
    Membership.objects.create(user=self.user, business=business, role='viewer')
    self.client.force_authenticate(user=self.user)
    self.client.cookies['bid'] = str(business.id)

  def test_product_list_reads_only_primary_stock_and_does_not_create_locations(self):
    business = self._create_business('Saldos por ubicación')
    product = Product.objects.create(
      business=business,
      name='Producto con dos saldos',
      sku='SKU-PRIMARY',
      cost=25,
      price=50,
    )
    empty_product = Product.objects.create(
      business=business,
      name='Producto sin saldo',
      sku='SKU-EMPTY',
      cost=25,
      price=50,
    )
    primary = StockLocation.objects.create(
      business=business,
      name='Local principal',
      is_primary=True,
      is_active=True,
    )
    depot = StockLocation.objects.create(
      business=business,
      name='Depósito',
      is_active=True,
    )
    ProductStock.objects.create(
      business=business,
      product=product,
      location=primary,
      quantity=3,
    )
    ProductStock.objects.create(
      business=business,
      product=product,
      location=depot,
      quantity=10,
    )
    self._authenticate(business)

    response = self.client.get(reverse('catalog:product-list'))

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    products = {row['id']: row for row in response.data}
    self.assertEqual(
      products[str(product.pk)]['stock_quantity'],
      ProductStock.objects.get(product=product, location=primary).quantity,
    )
    self.assertIsNone(products[str(empty_product.pk)]['stock_quantity'])
    self.assertEqual(StockLocation.objects.filter(business=business).count(), 2)

  def test_catalog_read_without_locations_has_no_creation_side_effect(self):
    business = self._create_business('Catálogo sin ubicaciones')
    Product.objects.create(
      business=business,
      name='Producto sin saldo inicial',
      sku='SKU-NO-STOCK',
      cost=25,
      price=50,
    )
    self._authenticate(business)

    response = self.client.get(reverse('catalog:product-list'))

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(StockLocation.objects.filter(business=business).count(), 0)

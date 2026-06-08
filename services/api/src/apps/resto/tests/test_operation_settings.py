from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, CommercialSettings, Subscription
from apps.orders.models import Order
from apps.resto.models import RestaurantOperationSettings, Table


class RestaurantOperationSettingsAPITests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(
      username='resto-owner',
      email='resto-owner@example.com',
      password='pass1234',
    )
    self.business = Business.objects.create(name='Resto Ops', default_service='restaurante')
    Subscription.objects.create(
      business=self.business,
      plan=BusinessPlan.PLUS,
      service='restaurante',
      status='active',
    )
    Membership.objects.create(user=self.user, business=self.business, role='owner')
    self.client.force_authenticate(self.user)
    self.client.cookies['bid'] = str(self.business.id)

  def test_settings_defaults_are_created_per_business(self):
    settings = RestaurantOperationSettings.objects.for_business(self.business)

    self.assertEqual(settings.business, self.business)
    self.assertTrue(settings.tables_enabled)
    self.assertTrue(settings.kitchen_enabled)
    self.assertTrue(settings.counter_orders_enabled)
    self.assertTrue(settings.pos_quick_sale_enabled)
    self.assertTrue(settings.allow_pickup_orders)
    self.assertTrue(settings.allow_dine_in_orders)
    self.assertFalse(settings.allow_delivery_orders)
    self.assertEqual(settings.default_pos_mode, RestaurantOperationSettings.DefaultPosMode.QUICK_SALE)

  def test_can_read_operation_settings(self):
    url = reverse('resto:operation-settings')

    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(response.data['tables_enabled'])
    self.assertTrue(response.data['kitchen_enabled'])
    self.assertEqual(response.data['default_pos_mode'], 'quick_sale')

  def test_can_update_tables_enabled(self):
    url = reverse('resto:operation-settings')

    response = self.client.patch(url, {'tables_enabled': False}, format='json')

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertFalse(response.data['tables_enabled'])
    self.assertFalse(RestaurantOperationSettings.objects.for_business(self.business).tables_enabled)

  def test_can_update_kitchen_enabled(self):
    url = reverse('resto:operation-settings')

    response = self.client.patch(url, {'kitchen_enabled': False}, format='json')

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertFalse(response.data['kitchen_enabled'])
    self.assertFalse(RestaurantOperationSettings.objects.for_business(self.business).kitchen_enabled)

  def test_tables_enabled_false_does_not_delete_existing_tables(self):
    Table.objects.create(business=self.business, code='A1', name='Mesa A1', capacity=4)
    url = reverse('resto:operation-settings')

    response = self.client.patch(url, {'tables_enabled': False}, format='json')

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertTrue(Table.objects.filter(business=self.business, code='A1').exists())


class RestaurantOperationSettingsPosCounterTests(APITestCase):
  def setUp(self):
    self.business = Business.objects.create(name='Resto Ops POS', default_service='restaurante', status='active')
    Subscription.objects.create(
      business=self.business,
      plan=BusinessPlan.PLUS,
      service='restaurante',
      status='active',
    )
    self.user = get_user_model().objects.create_user(
      username='owner-pos',
      email='owner-pos@example.com',
      password='pass1234',
    )
    Membership.objects.create(user=self.user, business=self.business, role='owner')

    from apps.sales.tests.test_pos_counter_orders import _employee_client, _make_employee, _make_product

    self.employee = _make_employee(self.business)
    self.client = _employee_client(self.employee, self.business)
    self.product = _make_product(self.business)

    commercial_settings = CommercialSettings.objects.for_business(self.business)
    commercial_settings.block_sales_if_no_open_cash_session = False
    commercial_settings.require_customer_for_sales = False
    commercial_settings.save()

  def _payload(self):
    return {
      'items': [
        {
          'product_id': str(self.product.pk),
          'quantity': '1',
        }
      ],
      'customer_name': 'Mostrador operativo',
      'send_to_kitchen': True,
    }

  def test_pos_counter_order_rejects_when_kitchen_disabled(self):
    settings = RestaurantOperationSettings.objects.for_business(self.business)
    settings.kitchen_enabled = False
    settings.save(update_fields=['kitchen_enabled', 'updated_at'])

    response = self.client.post('/api/v1/pos/orders/counter/', self._payload(), format='json')

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    self.assertEqual(response.data['code'], 'kitchen_disabled')
    self.assertEqual(Order.objects.count(), 0)

  def test_pos_counter_order_rejects_when_counter_orders_disabled(self):
    settings = RestaurantOperationSettings.objects.for_business(self.business)
    settings.counter_orders_enabled = False
    settings.save(update_fields=['counter_orders_enabled', 'updated_at'])

    response = self.client.post('/api/v1/pos/orders/counter/', self._payload(), format='json')

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    self.assertEqual(response.data['code'], 'counter_orders_disabled')
    self.assertEqual(Order.objects.count(), 0)

  def test_pos_quick_sale_still_works_when_kitchen_disabled(self):
    settings = RestaurantOperationSettings.objects.for_business(self.business)
    settings.kitchen_enabled = False
    settings.save(update_fields=['kitchen_enabled', 'updated_at'])

    response = self.client.post(
      '/api/v1/pos/sales/',
      {
        'payment_method': 'cash',
        'items': [
          {
            'product_id': str(self.product.pk),
            'quantity': 1,
          }
        ],
      },
      format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
    self.assertEqual(Order.objects.count(), 0)

  def test_tables_flag_does_not_remove_existing_table_rows(self):
    Table.objects.create(business=self.business, code='B1', name='Salon B1', capacity=2)
    settings = RestaurantOperationSettings.objects.for_business(self.business)
    settings.tables_enabled = False
    settings.save(update_fields=['tables_enabled', 'updated_at'])

    self.assertTrue(Table.objects.filter(business=self.business, code='B1').exists())
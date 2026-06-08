from __future__ import annotations

from django.test import TestCase
from rest_framework import status

from apps.accounts.models import EmployeeProfile
from apps.cash.models import Payment
from apps.inventory.models import StockMovement
from apps.orders.models import Order
from apps.resto.models import RestaurantOperationSettings
from apps.sales.models import Sale
from apps.sales.tests.test_pos_counter_orders import (
    _employee_client,
    _make_business,
    _make_employee,
    _make_product,
)

URL_COUNTER_ORDERS = '/api/v1/pos/orders/counter/'
URL_POS_KITCHEN_BOARD = '/api/v1/pos/orders/kitchen/board/'


class PosKitchenEndpointsTests(TestCase):

    def setUp(self):
        self.business = _make_business('PosKitchenBiz')
        self.product = _make_product(self.business, name='Pizza napolitana')
        self.cashier_employee = _make_employee(
            self.business,
            code='EMP-CASHIER-01',
            role_type=EmployeeProfile.RoleType.CASHIER,
        )
        self.cashier_client = _employee_client(self.cashier_employee, self.business)
        self.kitchen_employee = _make_employee(
            self.business,
            code='EMP-KITCHEN-01',
            role_type=EmployeeProfile.RoleType.KITCHEN,
        )
        self.kitchen_client = _employee_client(self.kitchen_employee, self.business)

    def _create_counter_order(self, client, customer_name='Mesa 1'):
        response = client.post(
            URL_COUNTER_ORDERS,
            {
                'items': [
                    {
                        'product_id': str(self.product.pk),
                        'quantity': '1',
                        'note': 'bien cocido',
                    }
                ],
                'customer_name': customer_name,
                'send_to_kitchen': True,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.json()

    def test_kitchen_employee_can_list_kitchen_board(self):
        created_order = self._create_counter_order(self.cashier_client)

        response = self.kitchen_client.get(URL_POS_KITCHEN_BOARD)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        ids = {item['id'] for item in response.json()}
        self.assertIn(created_order['id'], ids)

    def test_employee_without_kitchen_role_is_rejected(self):
        cashier = _make_employee(
            self.business,
            code='EMP-CASHIER-02',
            role_type=EmployeeProfile.RoleType.CASHIER,
        )
        cashier_client = _employee_client(cashier, self.business)

        response = cashier_client.get(URL_POS_KITCHEN_BOARD)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'kitchen_permission_required')

    def test_manager_can_access_kitchen_board(self):
        manager = _make_employee(
            self.business,
            code='EMP-MANAGER-01',
            role_type=EmployeeProfile.RoleType.MANAGER_OP,
        )
        manager_client = _employee_client(manager, self.business)

        response = manager_client.get(URL_POS_KITCHEN_BOARD)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_kitchen_disabled_returns_403(self):
        settings = RestaurantOperationSettings.objects.for_business(self.business)
        settings.kitchen_enabled = False
        settings.save(update_fields=['kitchen_enabled', 'updated_at'])

        response = self.kitchen_client.get(URL_POS_KITCHEN_BOARD)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'kitchen_disabled')

    def test_only_orders_from_same_business_are_returned(self):
        own_order = self._create_counter_order(self.cashier_client, customer_name='Negocio A')

        other_business = _make_business('PosKitchenOtherBiz')
        other_product = _make_product(other_business, name='Empanada')
        other_kitchen = _make_employee(
            other_business,
            code='EMP-KITCHEN-02',
            role_type=EmployeeProfile.RoleType.KITCHEN,
        )
        other_cashier = _make_employee(
            other_business,
            code='EMP-CASHIER-02',
            role_type=EmployeeProfile.RoleType.CASHIER,
        )
        other_client = _employee_client(other_cashier, other_business)
        other_response = other_client.post(
            URL_COUNTER_ORDERS,
            {
                'items': [{'product_id': str(other_product.pk), 'quantity': '1'}],
                'customer_name': 'Negocio B',
                'send_to_kitchen': True,
            },
            format='json',
        )
        self.assertEqual(other_response.status_code, status.HTTP_201_CREATED, other_response.data)

        response = self.kitchen_client.get(URL_POS_KITCHEN_BOARD)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        ids = {item['id'] for item in response.json()}
        self.assertIn(own_order['id'], ids)
        self.assertNotIn(other_response.json()['id'], ids)

    def test_pending_to_in_progress_and_in_progress_to_ready(self):
        created_order = self._create_counter_order(self.cashier_client)
        order = Order.objects.get(pk=created_order['id'])
        item = order.items.first()
        self.assertIsNotNone(item)

        in_progress_response = self.kitchen_client.patch(
            f'/api/v1/pos/orders/kitchen/items/{item.id}/',
            {'kitchen_status': 'in_progress'},
            format='json',
        )
        self.assertEqual(in_progress_response.status_code, status.HTTP_200_OK, in_progress_response.data)

        item.refresh_from_db()
        self.assertEqual(item.kitchen_status, item.KitchenStatus.IN_PROGRESS)

        ready_response = self.kitchen_client.patch(
            f'/api/v1/pos/orders/kitchen/items/{item.id}/',
            {'kitchen_status': 'ready'},
            format='json',
        )
        self.assertEqual(ready_response.status_code, status.HTTP_200_OK, ready_response.data)

        item.refresh_from_db()
        self.assertEqual(item.kitchen_status, item.KitchenStatus.READY)

    def test_ready_can_be_marked_done_and_disappears_from_active_board(self):
        created_order = self._create_counter_order(self.cashier_client)
        order = Order.objects.get(pk=created_order['id'])

        ready_response = self.kitchen_client.patch(
            f'/api/v1/pos/orders/kitchen/orders/{order.id}/bulk/',
            {'kitchen_status': 'ready'},
            format='json',
        )
        self.assertEqual(ready_response.status_code, status.HTTP_200_OK, ready_response.data)

        done_response = self.kitchen_client.patch(
            f'/api/v1/pos/orders/kitchen/orders/{order.id}/bulk/',
            {'kitchen_status': 'done'},
            format='json',
        )
        self.assertEqual(done_response.status_code, status.HTTP_200_OK, done_response.data)

        order.refresh_from_db()
        self.assertTrue(order.items.exists())
        self.assertTrue(all(item.kitchen_status == item.KitchenStatus.DONE for item in order.items.all()))

        board_response = self.kitchen_client.get(URL_POS_KITCHEN_BOARD)
        self.assertEqual(board_response.status_code, status.HTTP_200_OK, board_response.data)
        ids = {item['id'] for item in board_response.json()}
        self.assertNotIn(created_order['id'], ids)

    def test_cannot_update_kitchen_item_from_another_business(self):
        own_order = self._create_counter_order(self.cashier_client)
        own_item = Order.objects.get(pk=own_order['id']).items.first()
        self.assertIsNotNone(own_item)

        other_business = _make_business('PosKitchenOtherBizUpdate')
        other_product = _make_product(other_business, name='Taco')
        other_cashier = _make_employee(
            other_business,
            code='EMP-CASHIER-03',
            role_type=EmployeeProfile.RoleType.CASHIER,
        )
        other_kitchen = _make_employee(
            other_business,
            code='EMP-KITCHEN-03',
            role_type=EmployeeProfile.RoleType.KITCHEN,
        )
        other_cashier_client = _employee_client(other_cashier, other_business)
        other_kitchen_client = _employee_client(other_kitchen, other_business)
        other_response = other_cashier_client.post(
            URL_COUNTER_ORDERS,
            {
                'items': [{'product_id': str(other_product.pk), 'quantity': '1'}],
                'customer_name': 'Negocio B',
                'send_to_kitchen': True,
            },
            format='json',
        )
        self.assertEqual(other_response.status_code, status.HTTP_201_CREATED, other_response.data)

        forbidden_update = other_kitchen_client.patch(
            f'/api/v1/pos/orders/kitchen/items/{own_item.id}/',
            {'kitchen_status': 'in_progress'},
            format='json',
        )
        self.assertEqual(forbidden_update.status_code, status.HTTP_404_NOT_FOUND)

    def test_kitchen_updates_do_not_create_sales_payments_or_stock(self):
        created_order = self._create_counter_order(self.cashier_client)
        order = Order.objects.get(pk=created_order['id'])

        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

        response = self.kitchen_client.patch(
            f'/api/v1/pos/orders/kitchen/orders/{order.id}/bulk/',
            {'kitchen_status': 'in_progress'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        done_response = self.kitchen_client.patch(
            f'/api/v1/pos/orders/kitchen/orders/{order.id}/bulk/',
            {'kitchen_status': 'done'},
            format='json',
        )
        self.assertEqual(done_response.status_code, status.HTTP_200_OK, done_response.data)

        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

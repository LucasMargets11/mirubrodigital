from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription
from apps.orders.models import Order
from apps.resto.models import Table, TableLayout, TablePlacement


class TableConfigurationAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='tables-admin', email='tables@example.com', password='pass1234'
        )
        self.business = Business.objects.create(name='Restaurante Test', default_service='restaurante')
        Subscription.objects.create(business=self.business, plan=BusinessPlan.PLUS, status='active')
        Membership.objects.create(user=self.user, business=self.business, role='owner')
        self.client.force_authenticate(self.user)
        self.client.cookies['bid'] = str(self.business.id)

        self.layout = TableLayout.objects.create(business=self.business, grid_cols=8, grid_rows=6)
        self.table_a = Table.objects.create(business=self.business, code='A1', name='Mesa A1', capacity=4)
        self.table_b = Table.objects.create(business=self.business, code='A2', name='Mesa A2', capacity=2)
        TablePlacement.objects.create(
            business=self.business,
            layout=self.layout,
            table=self.table_a,
            x=1,
            y=1,
        )
        TablePlacement.objects.create(
            business=self.business,
            layout=self.layout,
            table=self.table_b,
            x=2,
            y=1,
        )

    def test_get_configuration_returns_tables_and_layout(self):
        url = reverse('resto:table-config')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['tables']), 2)
        self.assertEqual(response.data['layout']['gridCols'], 8)
        self.assertEqual(len(response.data['layout']['placements']), 2)

    def test_put_configuration_upserts_tables_and_layout(self):
        url = reverse('resto:table-config')
        new_table_id = uuid.uuid4()
        payload = {
            'tables': [
                {
                    'id': str(self.table_a.id),
                    'code': 'A1',
                    'name': 'Mesa Principal',
                    'capacity': 6,
                    'is_enabled': True,
                },
                {
                    'id': str(new_table_id),
                    'code': 'B1',
                    'name': 'Terraza',
                    'capacity': 4,
                    'is_enabled': True,
                },
            ],
            'layout': {
                'gridCols': 10,
                'gridRows': 6,
                'placements': [
                    {'tableId': str(self.table_a.id), 'x': 1, 'y': 1, 'w': 1, 'h': 1, 'rotation': 0},
                    {'tableId': str(new_table_id), 'x': 2, 'y': 1, 'w': 1, 'h': 1, 'rotation': 0},
                ],
            },
        }

        response = self.client.put(url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tables = Table.objects.filter(business=self.business).order_by('code')
        self.assertEqual(tables.count(), 2)
        self.table_a.refresh_from_db()
        self.assertEqual(self.table_a.capacity, 6)
        self.assertEqual(tables.first().code, 'A1')
        layout = TableLayout.objects.get(business=self.business)
        self.assertEqual(layout.grid_cols, 10)
        self.assertEqual(layout.placements.count(), 2)
        self.assertTrue(Table.objects.filter(code='B1', business=self.business).exists())


class RestaurantTablesMapStateAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='map-user', email='map@example.com', password='pass1234'
        )
        self.business = Business.objects.create(name='Restaurante Test', default_service='restaurante')
        Subscription.objects.create(business=self.business, plan=BusinessPlan.PLUS, status='active')
        Membership.objects.create(user=self.user, business=self.business, role='owner')
        self.client.force_authenticate(self.user)
        self.client.cookies['bid'] = str(self.business.id)

        self.layout = TableLayout.objects.create(business=self.business, grid_cols=8, grid_rows=6)
        self.table_a = Table.objects.create(business=self.business, code='A1', name='Mesa A1', capacity=4)
        self.table_b = Table.objects.create(
            business=self.business,
            code='A2',
            name='Mesa A2',
            capacity=2,
            is_paused=True,
        )
        TablePlacement.objects.create(business=self.business, layout=self.layout, table=self.table_a, x=1, y=1)
        TablePlacement.objects.create(
            business=self.business,
            layout=self.layout,
            table=self.table_b,
            x=2,
            y=1,
            w=2,
            h=1,
            rotation=0,
            z_index=2,
        )

    def test_map_state_reflects_active_orders_and_status(self):
        Order.objects.create(
            business=self.business,
            table=self.table_a,
            table_name=self.table_a.name,
            number=101,
            status=Order.Status.OPEN,
            total_amount=120,
        )

        url = reverse('restaurant-tables-map')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tables = response.data['tables']
        self.assertEqual(len(tables), 2)
        table_a_payload = next(item for item in tables if item['id'] == str(self.table_a.id))
        self.assertEqual(table_a_payload['state'], 'OCCUPIED')
        self.assertIsNotNone(table_a_payload['active_order'])
        self.assertIsNotNone(table_a_payload['position'])
        self.assertGreater(table_a_payload['position']['w'], 0)

        table_b_payload = next(item for item in tables if item['id'] == str(self.table_b.id))
        self.assertEqual(table_b_payload['state'], 'PAUSED')
        self.assertIsNone(table_b_payload['active_order'])
        self.assertEqual(table_b_payload['position']['z_index'], 2)

    def test_tables_snapshot_returns_layout_positions(self):
        url = reverse('restaurant-tables')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data
        self.assertIn('layout', payload)
        self.assertEqual(payload['layout']['gridCols'], 8)
        self.assertEqual(len(payload['tables']), 2)
        first = payload['tables'][0]
        self.assertIn('position', first)

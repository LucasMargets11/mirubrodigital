from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, CommercialSettings, Subscription
from apps.menu.models import MenuItem
from apps.orders.models import Order, OrderDraft, OrderDraftItem
from apps.resto.models import Table


class OrderDraftAPITests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(
      username='drafts', email='drafts@example.com', password='pass1234'
    )

  def _create_business(self, name: str = 'Restaurante Mirubro') -> Business:
    business = Business.objects.create(name=name, default_service='restaurante')
    Subscription.objects.create(business=business, plan=BusinessPlan.PLUS, status='active')
    settings = CommercialSettings.objects.for_business(business)
    settings.allow_sell_without_stock = True
    settings.save()
    return business

  def _authenticate(self, business: Business, role: str = 'salon'):
    Membership.objects.create(user=self.user, business=business, role=role)
    self.client.force_authenticate(self.user)
    self.client.cookies['bid'] = str(business.id)

  def _create_menu_item(self, business: Business, name: str = 'Empanada Clásica', price: Decimal = Decimal('120.00')) -> MenuItem:
    return MenuItem.objects.create(business=business, name=name, price=price)

  def _create_table(self, business: Business, code: str = 'M1', name: str = 'Mesa 1') -> Table:
    return Table.objects.create(business=business, code=code, name=name)

  def _create_draft(self, business: Business, **overrides) -> OrderDraft:
    payload = {
      'business': business,
      'channel': overrides.get('channel', Order.Channel.DELIVERY),
      'customer_name': overrides.get('customer_name', ''),
      'table_name': overrides.get('table_name', ''),
      'note': overrides.get('note', ''),
    }
    draft = OrderDraft.objects.create(**payload)
    return draft

  def test_list_returns_only_editing_drafts_for_business(self):
    business = self._create_business()
    other_business = self._create_business('Otro negocio')
    target_draft = OrderDraft.objects.create(business=business, customer_name='Ana')
    OrderDraft.objects.create(business=business, status=OrderDraft.Status.SUBMITTED)
    OrderDraft.objects.create(business=other_business, customer_name='Beto')
    self._authenticate(business)

    url = reverse('orders:order-draft-list')
    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(len(response.data), 1)
    self.assertEqual(response.data[0]['id'], str(target_draft.id))

  def test_create_draft_via_api(self):
    business = self._create_business()
    self._authenticate(business)

    url = reverse('orders:order-draft-list')
    payload = {
      'channel': Order.Channel.DELIVERY,
      'customer_name': 'Lucia',
      'note': 'Sin cebolla',
      'client_reference': 'mobile-123',
    }
    response = self.client.post(url, payload, format='json')

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    self.assertEqual(response.data['customer_name'], 'Lucia')
    self.assertEqual(response.data['status'], OrderDraft.Status.EDITING)
    self.assertEqual(OrderDraft.objects.filter(business=business).count(), 1)

  def test_add_item_updates_totals(self):
    business = self._create_business()
    draft = self._create_draft(business)
    menu_item = self._create_menu_item(business, price=Decimal('150.00'))
    self._authenticate(business)

    url = reverse('orders:order-draft-items', args=[draft.id])
    response = self.client.post(
      url,
      {
        'menu_item_id': str(menu_item.id),
        'quantity': '2',
        'unit_price': '150.00',
        'note': 'Extra queso',
      },
      format='json',
    )

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    draft.refresh_from_db()
    self.assertEqual(draft.items_count, 1)
    self.assertEqual(draft.total_amount, Decimal('300.00'))

  def test_update_item_recalculates_totals(self):
    business = self._create_business()
    draft = self._create_draft(business)
    item = OrderDraftItem.objects.create(
      draft=draft,
      name='Combo',
      quantity=Decimal('1'),
      unit_price=Decimal('200.00'),
      total_price=Decimal('200.00'),
    )
    draft.recalculate_totals()
    self._authenticate(business)

    url = reverse('orders:order-draft-item-detail', args=[draft.id, item.id])
    response = self.client.patch(url, {'quantity': '3'}, format='json')

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    draft.refresh_from_db()
    self.assertEqual(draft.items_count, 1)
    self.assertEqual(draft.total_amount, Decimal('600.00'))

  def test_delete_item_clears_totals(self):
    business = self._create_business()
    draft = self._create_draft(business)
    OrderDraftItem.objects.create(
      draft=draft,
      name='Soda',
      quantity=Decimal('2'),
      unit_price=Decimal('50.00'),
      total_price=Decimal('100.00'),
    )
    draft.recalculate_totals()
    self._authenticate(business)

    item = draft.items.first()
    url = reverse('orders:order-draft-item-detail', args=[draft.id, item.id])
    response = self.client.delete(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    draft.refresh_from_db()
    self.assertEqual(draft.items_count, 0)
    self.assertEqual(draft.total_amount, Decimal('0'))

  def test_assign_table_without_permission_fails(self):
    business = self._create_business()
    draft = self._create_draft(business, channel=Order.Channel.DINE_IN)
    table = self._create_table(business)
    self._authenticate(business, role='cashier')

    url = reverse('orders:order-draft-assign-table', args=[draft.id])
    response = self.client.post(url, {'table_id': str(table.id)}, format='json')

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('No tenés permisos para asignar mesas.', str(response.data))

  def test_assign_table_with_permission_updates_draft(self):
    business = self._create_business()
    draft = self._create_draft(business, channel=Order.Channel.DINE_IN)
    table = self._create_table(business)
    self._authenticate(business, role='salon')

    url = reverse('orders:order-draft-assign-table', args=[draft.id])
    with patch('apps.orders.views.request_has_permission', return_value=True):
      response = self.client.post(
        url,
        {
          'table_id': str(table.id),
          'table_name': 'Mesa Terraza',
        },
        format='json',
      )

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    draft.refresh_from_db()
    self.assertEqual(draft.table_id, table.id)
    self.assertEqual(draft.table_name, 'Mesa Terraza')

  def test_confirm_draft_creates_order(self):
    business = self._create_business()
    draft = self._create_draft(business, channel=Order.Channel.DELIVERY, customer_name='Luis')
    OrderDraftItem.objects.create(
      draft=draft,
      name='Hamburguesa',
      quantity=Decimal('2'),
      unit_price=Decimal('180.00'),
      total_price=Decimal('360.00'),
    )
    draft.recalculate_totals()
    self._authenticate(business)

    url = reverse('orders:order-draft-confirm', args=[draft.id])
    response = self.client.post(url, {}, format='json')

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    draft.refresh_from_db()
    self.assertEqual(draft.status, OrderDraft.Status.SUBMITTED)
    self.assertIsNotNone(draft.order_id)
    self.assertEqual(Order.objects.filter(business=business).count(), 1)

  def test_confirm_draft_requires_table_for_dine_in(self):
    business = self._create_business()
    draft = self._create_draft(business, channel=Order.Channel.DINE_IN)
    OrderDraftItem.objects.create(
      draft=draft,
      name='Milanesa',
      quantity=Decimal('1'),
      unit_price=Decimal('250.00'),
      total_price=Decimal('250.00'),
    )
    draft.recalculate_totals()
    self._authenticate(business)

    url = reverse('orders:order-draft-confirm', args=[draft.id])
    response = self.client.post(url, {}, format='json')

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn('Seleccioná una mesa', str(response.data))

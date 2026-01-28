from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription
from apps.menu.models import MenuCategory, MenuItem


class MenuAPITests(APITestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(
      username='menu-user', email='menu@example.com', password='pass1234'
    )

  def _create_business(self, name: str = 'Casa Central', plan: str = BusinessPlan.PLUS) -> Business:
    business = Business.objects.create(name=name, default_service='restaurante')
    Subscription.objects.create(business=business, plan=plan, status='active')
    return business

  def _authenticate(self, business: Business, role: str = 'owner') -> None:
    Membership.objects.create(user=self.user, business=business, role=role)
    self.client.force_authenticate(self.user)
    self.client.cookies['bid'] = str(business.id)

  def _upload(self, workbook: Workbook) -> SimpleUploadedFile:
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return SimpleUploadedFile(
      'menu.xlsx',
      buffer.read(),
      content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )

  def test_list_categories_returns_only_active_business_data(self):
    business = self._create_business()
    other = self._create_business('Otra Sucursal')
    MenuCategory.objects.create(business=business, name='Bebidas', description='', position=1)
    MenuCategory.objects.create(business=business, name='Platos', description='', position=2)
    MenuCategory.objects.create(business=other, name='Oculta', description='', position=1)

    self._authenticate(business)
    url = reverse('menu:category-list')
    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    names = [category['name'] for category in response.data]
    self.assertEqual(names, ['Bebidas', 'Platos'])

  def test_import_requires_restaurant_feature(self):
    business = self._create_business(plan=BusinessPlan.PRO)
    self._authenticate(business)
    workbook = Workbook()
    workbook.active.append(['Nombre'])
    payload = {'file': self._upload(workbook)}

    url = reverse('menu:import')
    response = self.client.post(url, payload)

    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

  def test_import_creates_categories_and_items(self):
    business = self._create_business()
    self._authenticate(business)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['Categoría', 'Nombre', 'Descripción', 'Precio', 'Disponible', 'Tags'])
    sheet.append(['Pizzas', 'Muzza', 'Clásica', Decimal('100'), 'Sí', 'veg'])
    sheet.append(['Pizzas', 'Fugazza', 'Con cebolla', Decimal('120'), 'Sí', 'cebolla'])

    url = reverse('menu:import')
    response = self.client.post(url, {'file': self._upload(workbook)})

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(MenuCategory.objects.filter(business=business).count(), 1)
    self.assertEqual(MenuItem.objects.filter(business=business).count(), 2)
    self.assertEqual(response.data['summary']['created_items'], 2)

  def test_export_returns_workbook(self):
    business = self._create_business()
    self._authenticate(business)
    category = MenuCategory.objects.create(business=business, name='Bebidas', description='', position=1)
    MenuItem.objects.create(
      business=business,
      category=category,
      name='Limonada',
      description='Refrescante',
      price=Decimal('80.00'),
      sku='DRINK-1',
    )

    url = reverse('menu:export')
    response = self.client.get(url)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(
      response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    self.assertIn('attachment; filename="carta-', response['Content-Disposition'])

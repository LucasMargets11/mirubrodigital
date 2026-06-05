from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription
from apps.catalog.models import Product, ProductCategory
from apps.menu.models import MenuCategory, MenuItem, ensure_public_menu_config


class MenuItemProductLinkTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='menu-product-link-user',
            email='menu-product-link@example.com',
            password='pass1234',
        )
        self.business = Business.objects.create(name='Menu Product Link', default_service='restaurante')
        Subscription.objects.create(
            business=self.business,
            plan=BusinessPlan.PLUS,
            status='active',
            service='restaurante',
        )
        Membership.objects.create(user=self.user, business=self.business, role='owner')
        self.client.force_authenticate(self.user)
        self.client.cookies['bid'] = str(self.business.id)

        self.menu_category = MenuCategory.objects.create(
            business=self.business,
            name='Principal',
            position=1,
            is_active=True,
        )
        self.product_category = ProductCategory.objects.create(
            business=self.business,
            name='Comidas',
            is_active=True,
        )
        self.product = Product.objects.create(
            business=self.business,
            category=self.product_category,
            name='Producto Real',
            price='1250.00',
            is_active=True,
        )

    def test_create_menu_item_without_product_still_works(self):
        response = self.client.post(
            reverse('menu:item-list'),
            {
                'category_id': str(self.menu_category.id),
                'name': 'Item Legacy',
                'price': '500.00',
                'is_available': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data['product'])
        self.assertIsNone(response.data['product_name'])

    def test_create_menu_item_with_product_and_serialize_product_fields(self):
        response = self.client.post(
            reverse('menu:item-list'),
            {
                'category_id': str(self.menu_category.id),
                'product': str(self.product.id),
                'name': 'Item Vinculado',
                'price': '1300.00',
                'is_available': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_id = response.data['id']

        detail = self.client.get(reverse('menu:item-detail', kwargs={'pk': created_id}))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['product'], str(self.product.id))
        self.assertEqual(detail.data['product_name'], self.product.name)
        self.assertEqual(str(detail.data['product_price']), '1250.00')
        self.assertEqual(detail.data['product_category'], self.product_category.name)
        self.assertTrue(detail.data['product_is_active'])


class PublicMenuProductCompatibilityTests(APITestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name='Public Menu Product Link',
            slug='public-menu-product-link',
            status='active',
            default_service='menu_qr',
        )
        Subscription.objects.create(
            business=self.business,
            plan=BusinessPlan.MENU_QR,
            service='menu_qr',
            status='active',
        )

        self.menu_category = MenuCategory.objects.create(
            business=self.business,
            name='Bebidas',
            position=1,
            is_active=True,
        )
        self.product_category = ProductCategory.objects.create(
            business=self.business,
            name='Barra',
            is_active=True,
        )
        self.active_product = Product.objects.create(
            business=self.business,
            category=self.product_category,
            name='Limonada Real',
            price='900.00',
            is_active=True,
        )
        self.inactive_product = Product.objects.create(
            business=self.business,
            category=self.product_category,
            name='Producto Inactivo',
            price='800.00',
            is_active=False,
        )

        MenuItem.objects.create(
            business=self.business,
            category=self.menu_category,
            name='Legacy Visible',
            price='700.00',
            is_available=True,
            position=1,
        )
        MenuItem.objects.create(
            business=self.business,
            category=self.menu_category,
            product=self.active_product,
            name='Vinculado Activo',
            price='950.00',
            is_available=True,
            position=2,
        )
        MenuItem.objects.create(
            business=self.business,
            category=self.menu_category,
            product=self.inactive_product,
            name='Vinculado Inactivo',
            price='850.00',
            is_available=True,
            position=3,
        )

        self.config = ensure_public_menu_config(self.business)
        self.config.enabled = True
        self.config.save(update_fields=['enabled'])

    def test_public_menu_slug_keeps_legacy_items_and_display_fields(self):
        response = self.client.get(reverse('menu:public-by-slug', kwargs={'slug': self.config.slug}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['slug'], self.config.slug)

        items = response.data['categories'][0]['items']
        names = [item['name'] for item in items]

        self.assertIn('Legacy Visible', names)
        self.assertIn('Vinculado Activo', names)

        legacy_item = next(item for item in items if item['name'] == 'Legacy Visible')
        self.assertEqual(legacy_item['display_name'], 'Legacy Visible')
        self.assertEqual(str(legacy_item['display_price']), '700.00')
        self.assertTrue(legacy_item['display_available'])

    def test_public_menu_linked_product_exposes_product_reference_and_filters_inactive_product(self):
        response = self.client.get(reverse('menu:public-by-slug', kwargs={'slug': self.config.slug}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = response.data['categories'][0]['items']

        linked_active = next(item for item in items if item['name'] == 'Vinculado Activo')
        self.assertEqual(str(linked_active['product']), str(self.active_product.id))
        self.assertEqual(linked_active['product_name'], self.active_product.name)
        self.assertEqual(str(linked_active['product_price']), '900.00')
        self.assertEqual(linked_active['product_category'], self.product_category.name)
        self.assertTrue(linked_active['product_is_active'])

        names = [item['name'] for item in items]
        self.assertNotIn('Vinculado Inactivo', names)

    def test_public_resolve_by_public_id_still_works(self):
        response = self.client.get(
            reverse('menu:public-resolve', kwargs={'public_id': self.config.public_id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['slug'], self.config.slug)

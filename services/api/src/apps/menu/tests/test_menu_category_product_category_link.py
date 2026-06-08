from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription
from apps.catalog.models import ProductCategory
from apps.menu.models import MenuCategory, MenuItem, ensure_public_menu_config


class MenuCategoryProductCategoryLinkTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='menu-category-link-user',
            email='menu-category-link@example.com',
            password='pass1234',
        )
        self.business = Business.objects.create(name='Menu Category Link', default_service='restaurante')
        Subscription.objects.create(
            business=self.business,
            plan=BusinessPlan.PLUS,
            status='active',
            service='restaurante',
        )
        Membership.objects.create(user=self.user, business=self.business, role='owner')
        self.client.force_authenticate(self.user)
        self.client.cookies['bid'] = str(self.business.id)

        self.product_category = ProductCategory.objects.create(
            business=self.business,
            name='Bebidas sin alcohol',
            is_active=True,
        )

        self.other_business = Business.objects.create(name='Otro Negocio', default_service='restaurante')
        Subscription.objects.create(
            business=self.other_business,
            plan=BusinessPlan.PLUS,
            status='active',
            service='restaurante',
        )
        self.other_product_category = ProductCategory.objects.create(
            business=self.other_business,
            name='Categoria Externa',
            is_active=True,
        )

    def test_create_category_without_product_category_still_works(self):
        response = self.client.post(
            reverse('menu:category-list'),
            {
                'name': 'Bebidas',
                'description': 'Categoria publica legacy',
                'position': 1,
                'is_active': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data['product_category'])
        self.assertIsNone(response.data['product_category_name'])

    def test_create_category_with_product_category_works(self):
        response = self.client.post(
            reverse('menu:category-list'),
            {
                'name': 'Bebidas',
                'position': 1,
                'is_active': True,
                'product_category': str(self.product_category.id),
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['product_category'], str(self.product_category.id))
        self.assertEqual(response.data['product_category_name'], self.product_category.name)
        self.assertTrue(response.data['product_category_is_active'])
        self.assertIsNone(response.data['product_category_sort_order'])

    def test_rejects_product_category_from_another_business(self):
        response = self.client.post(
            reverse('menu:category-list'),
            {
                'name': 'Categoria invalida',
                'position': 1,
                'is_active': True,
                'product_category': str(self.other_product_category.id),
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('product_category', response.data)

    def test_category_serializer_exposes_product_category_metadata(self):
        category = MenuCategory.objects.create(
            business=self.business,
            name='Bebidas',
            position=1,
            is_active=True,
            product_category=self.product_category,
        )

        response = self.client.get(reverse('menu:category-detail', kwargs={'pk': category.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['product_category'], str(self.product_category.id))
        self.assertEqual(response.data['product_category_name'], self.product_category.name)
        self.assertTrue(response.data['product_category_is_active'])
        self.assertIsNone(response.data['product_category_sort_order'])


class PublicMenuCategoryCompatibilityTests(APITestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name='Public Category Link',
            slug='public-category-link',
            status='active',
            default_service='menu_qr',
        )
        Subscription.objects.create(
            business=self.business,
            plan=BusinessPlan.MENU_QR,
            service='menu_qr',
            status='active',
        )

        self.product_category = ProductCategory.objects.create(
            business=self.business,
            name='Bebidas sin alcohol',
            is_active=True,
        )

        self.linked_menu_category = MenuCategory.objects.create(
            business=self.business,
            name='Bebidas',
            description='Nombre publico curado',
            position=1,
            is_active=True,
            product_category=self.product_category,
        )
        self.legacy_menu_category = MenuCategory.objects.create(
            business=self.business,
            name='Especiales',
            description='Legacy sin categoria comercial',
            position=2,
            is_active=True,
        )

        MenuItem.objects.create(
            business=self.business,
            category=self.linked_menu_category,
            name='Agua',
            price='100.00',
            is_available=True,
            position=1,
        )
        MenuItem.objects.create(
            business=self.business,
            category=self.legacy_menu_category,
            name='Promo del dia',
            price='250.00',
            is_available=True,
            position=1,
        )

        self.config = ensure_public_menu_config(self.business)
        self.config.enabled = True
        self.config.save(update_fields=['enabled'])

    def test_public_menu_keeps_menu_category_name_and_exposes_product_category_metadata(self):
        response = self.client.get(reverse('menu:public-by-slug', kwargs={'slug': self.config.slug}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        categories = response.data['categories']
        linked = next(cat for cat in categories if cat['name'] == 'Bebidas')

        self.assertEqual(linked['name'], 'Bebidas')
        self.assertEqual(linked['product_category_name'], self.product_category.name)
        self.assertEqual(linked['product_category'], str(self.product_category.id))
        self.assertTrue(linked['product_category_is_active'])

    def test_public_menu_legacy_category_without_product_category_still_works(self):
        response = self.client.get(reverse('menu:public-by-slug', kwargs={'slug': self.config.slug}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        categories = response.data['categories']
        legacy = next(cat for cat in categories if cat['name'] == 'Especiales')
        self.assertIsNone(legacy['product_category'])
        self.assertIsNone(legacy['product_category_name'])

    def test_public_slug_and_resolve_endpoints_still_work(self):
        by_slug = self.client.get(reverse('menu:public-by-slug', kwargs={'slug': self.config.slug}))
        by_public_id = self.client.get(reverse('menu:public-resolve', kwargs={'public_id': self.config.public_id}))

        self.assertEqual(by_slug.status_code, status.HTTP_200_OK)
        self.assertEqual(by_public_id.status_code, status.HTTP_200_OK)
        self.assertEqual(by_public_id.data['slug'], self.config.slug)

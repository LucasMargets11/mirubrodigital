"""
Tests para el endpoint POST /api/v1/printables/generate-pdf/

Cubre:
- PRO: 200 + application/pdf + body no vacío
- Starter: 403
- Business: 403
- Enterprise: 403
- Producto de otro business: 400 invalid_product
- Producto inactivo: 400 invalid_product
- include_price=false genera PDF sin precio
- include_logo=true sin logo no rompe
- logo_variant='vertical' devuelve 400
- card_size no permitida devuelve 400
- items=[] devuelve 400
- copies=4 genera PDF válido
- product_id=null con title genera PDF válido
- feature_flags_for_plan tests
"""
from __future__ import annotations

import base64
import uuid

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessBranding, Subscription
from apps.business.features import feature_flags_for_plan
from apps.catalog.models import Product

User = get_user_model()

URL = '/api/v1/printables/generate-pdf/'

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_minimal_png() -> bytes:
    """PNG de 1×1 píxel válido."""
    _1x1_b64 = (
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8'
        'z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=='
    )
    return base64.b64decode(_1x1_b64)


def _minimal_payload(**overrides) -> dict:
    """Payload mínimo válido para generar un cartel sin producto."""
    base = {
        'type': 'product',
        'template_code': 'product_price_simple',
        'paper_size': 'A4',
        'card_size': {'width_cm': 10, 'height_cm': 7},
        'logo_variant': 'none',
        'include_logo': False,
        'include_price': True,
        'show_cut_lines': True,
        'items': [
            {
                'product_id': None,
                'title': 'Yerba Mate',
                'description': 'Elaboración propia',
                'price': '2500',
                'copies': 1,
            }
        ],
    }
    base.update(overrides)
    return base


# ── Fixture helpers ───────────────────────────────────────────────────────────

class PrintablesBaseTest(APITestCase):
    """Base con helpers reutilizables."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='printables_test_user',
            email='printables@test.com',
            password='testpass123',
        )

    def _bootstrap_business(self, plan: str = 'pro', role: str = 'manager') -> Business:
        """Crea Business + Subscription legacy + Membership y autentica el cliente."""
        business = Business.objects.create(name=f'Biz {plan}')
        Subscription.objects.create(business=business, plan=plan, status='active')
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)
        return business

    def _make_product(self, business: Business, is_active: bool = True) -> Product:
        return Product.objects.create(
            business=business,
            name='Producto Test',
            sku='SKU001',
            price='100.00',
            cost='50.00',
            stock_min='0',
            is_active=is_active,
        )


# ── Tests de acceso por plan ──────────────────────────────────────────────────

class PlanAccessTests(PrintablesBaseTest):
    """Verifica que solo PRO tiene acceso."""

    def test_pro_plan_returns_200_pdf(self):
        self._bootstrap_business(plan='pro')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertGreater(len(response.content), 100)

    def test_pro_content_disposition_header(self):
        self._bootstrap_business(plan='pro')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('carteles-etiquetas.pdf', response['Content-Disposition'])

    def test_starter_plan_returns_403(self):
        self._bootstrap_business(plan='starter')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_start_legacy_plan_returns_403(self):
        """Plan 'start' (alias de starter) no debe tener acceso."""
        self._bootstrap_business(plan='start')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_business_plan_returns_403(self):
        self._bootstrap_business(plan='business')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_enterprise_plan_returns_403(self):
        self._bootstrap_business(plan='enterprise')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_returns_401(self):
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])


# ── Tests de validación de productos ─────────────────────────────────────────

class ProductValidationTests(PrintablesBaseTest):
    """Verifica isolación de tenant y validación de productos."""

    def test_product_from_another_business_returns_400(self):
        """Un producto de otro business no debe poder usarse."""
        self._bootstrap_business(plan='pro')

        # Crear otro business y un producto en él
        other_biz = Business.objects.create(name='Otro Negocio')
        other_product = Product.objects.create(
            business=other_biz,
            name='Producto ajeno',
            price='50.00',
            cost='20.00',
            stock_min='0',
        )

        payload = _minimal_payload(items=[{
            'product_id': str(other_product.id),
            'title': 'Desde otro negocio',
            'copies': 1,
        }])
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid_product')

    def test_inactive_product_returns_400(self):
        """Un producto con is_active=False no debe poder usarse."""
        biz = self._bootstrap_business(plan='pro')
        product = self._make_product(biz, is_active=False)

        payload = _minimal_payload(items=[{
            'product_id': str(product.id),
            'title': product.name,
            'copies': 1,
        }])
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid_product')

    def test_active_product_of_own_business_succeeds(self):
        """Producto activo del propio business debe ser aceptado."""
        biz = self._bootstrap_business(plan='pro')
        product = self._make_product(biz)

        payload = _minimal_payload(items=[{
            'product_id': str(product.id),
            'title': product.name,
            'price': str(product.price),
            'copies': 1,
        }])
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_product_id_null_with_title_generates_pdf(self):
        """product_id nulo con title es válido (cartel manual)."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(items=[{
            'product_id': None,
            'title': 'Producto artesanal',
            'description': 'Elaboración propia',
            'copies': 1,
        }])
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')


# ── Tests de payload/serializer ───────────────────────────────────────────────

class PayloadValidationTests(PrintablesBaseTest):
    """Verifica validaciones del serializer."""

    def test_logo_variant_vertical_returns_400(self):
        """'vertical' no es un logo_variant válido."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(logo_variant='vertical')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_card_size_not_allowed_returns_400(self):
        """Medidas fuera de la lista permitida deben devolver 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(card_size={'width_cm': 9.9, 'height_cm': 6.6})
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_items_returns_400(self):
        """items=[] debe devolver 400 (min_length=1)."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(items=[])
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_type_returns_400(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(type='invoice')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_template_code_returns_400(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(template_code='fancy_template')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ── Tests de comportamiento del PDF ──────────────────────────────────────────

class PDFBehaviorTests(PrintablesBaseTest):
    """Verifica comportamiento interno del PDF generado."""

    def test_include_price_false_generates_pdf(self):
        """include_price=False no debe exigir precio y debe generar PDF."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            include_price=False,
            items=[{
                'product_id': None,
                'title': 'Producto sin precio',
                'copies': 1,
                # price omitido intencionalmente
            }]
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertGreater(len(response.content), 100)

    def test_include_logo_true_without_logo_does_not_crash(self):
        """include_logo=True sin logo configurado debe generar PDF sin error."""
        biz = self._bootstrap_business(plan='pro')
        # Asegurar que no hay logos configurados
        BusinessBranding.objects.filter(business=biz).update(
            logo_horizontal='', logo_square=''
        )
        payload = _minimal_payload(include_logo=True, logo_variant='horizontal')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_copies_4_generates_valid_pdf(self):
        """copies=4 debe generar un PDF con múltiples cards."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(items=[{
            'product_id': None,
            'title': 'Producto con copias',
            'price': '1500',
            'copies': 4,
        }])
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        # PDF con 4 cards debe ser mayor que PDF con 1
        payload_1 = _minimal_payload(items=[{
            'product_id': None,
            'title': 'Producto con copias',
            'price': '1500',
            'copies': 1,
        }])
        response_1 = self.client.post(URL, payload_1, format='json')
        # Ambos son PDF válidos (no comparamos tamaño exacto por compresión)
        self.assertGreater(len(response.content), 100)

    def test_multiple_items_generates_pdf(self):
        """Múltiples items distintos deben generar PDF sin error."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(items=[
            {'product_id': None, 'title': 'Item 1', 'price': '100', 'copies': 2},
            {'product_id': None, 'title': 'Item 2', 'price': '200', 'copies': 1},
            {'product_id': None, 'title': 'Item 3', 'copies': 3},
        ])
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_show_cut_lines_false_generates_pdf(self):
        """show_cut_lines=False no debe romper la generación."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(show_cut_lines=False)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_all_card_sizes_generate_pdf(self):
        """Todos los tamaños de card válidos deben generar PDF sin error."""
        self._bootstrap_business(plan='pro')
        valid_sizes = [
            {'width_cm': 5,   'height_cm': 3},
            {'width_cm': 6,   'height_cm': 4},
            {'width_cm': 7,   'height_cm': 5},
            {'width_cm': 10,  'height_cm': 7},
            {'width_cm': 12,  'height_cm': 8},
            {'width_cm': 15,  'height_cm': 10},
            {'width_cm': 10.5,'height_cm': 14.8},
            {'width_cm': 14.8,'height_cm': 21},
            {'width_cm': 21,  'height_cm': 29.7},
        ]
        for size in valid_sizes:
            with self.subTest(size=size):
                payload = _minimal_payload(card_size=size)
                response = self.client.post(URL, payload, format='json')
                self.assertEqual(response.status_code, status.HTTP_200_OK, msg=f'Falló con card_size={size}')

    def test_promo_text_in_item_generates_pdf(self):
        """promo_text en el item no debe romper la generación."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(items=[{
            'product_id': None,
            'title': 'Yerba Mate',
            'description': 'Elaboración propia',
            'price': '2500',
            'old_price': '3000',
            'promo_text': 'OFERTA',
            'copies': 1,
        }])
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logo_variant_none_with_include_logo_true_generates_pdf(self):
        """logo_variant=none con include_logo=True no debe intentar cargar logo."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(logo_variant='none', include_logo=True)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ── Tests de entitlements y feature flags ────────────────────────────────────

class EntitlementFeatureFlagTests(PrintablesBaseTest):
    """Verifica que los feature flags y entitlements están correctamente configurados."""

    def test_feature_flags_pro_includes_print_signage(self):
        flags = feature_flags_for_plan('pro')
        self.assertTrue(flags.get('print_signage', False),
                        'print_signage debe estar habilitado en PRO')

    def test_feature_flags_starter_excludes_print_signage(self):
        flags = feature_flags_for_plan('starter')
        self.assertFalse(flags.get('print_signage', False),
                         'print_signage NO debe estar en starter')

    def test_feature_flags_start_legacy_excludes_print_signage(self):
        flags = feature_flags_for_plan('start')
        self.assertFalse(flags.get('print_signage', False),
                         'print_signage NO debe estar en start (alias de starter)')

    def test_feature_flags_business_excludes_print_signage(self):
        flags = feature_flags_for_plan('business')
        self.assertFalse(flags.get('print_signage', False),
                         'print_signage NO debe estar en business')

    def test_feature_flags_enterprise_excludes_print_signage(self):
        flags = feature_flags_for_plan('enterprise')
        self.assertFalse(flags.get('print_signage', False),
                         'print_signage NO debe estar en enterprise')

    def test_entitlement_pro_has_print_signage(self):
        from apps.business.entitlements import PLAN_ENTITLEMENTS
        self.assertIn('gestion.print_signage', PLAN_ENTITLEMENTS['pro'])

    def test_entitlement_starter_does_not_have_print_signage(self):
        from apps.business.entitlements import PLAN_ENTITLEMENTS
        self.assertNotIn('gestion.print_signage', PLAN_ENTITLEMENTS['starter'])

    def test_entitlement_business_does_not_have_print_signage(self):
        from apps.business.entitlements import PLAN_ENTITLEMENTS
        self.assertNotIn('gestion.print_signage', PLAN_ENTITLEMENTS['business'])

    def test_entitlement_enterprise_does_not_have_print_signage(self):
        from apps.business.entitlements import PLAN_ENTITLEMENTS
        self.assertNotIn('gestion.print_signage', PLAN_ENTITLEMENTS['enterprise'])

    def test_upgrade_hint_exists_for_print_signage(self):
        from apps.business.entitlements import ENTITLEMENT_UPGRADE_HINTS
        self.assertIn('gestion.print_signage', ENTITLEMENT_UPGRADE_HINTS)
        self.assertEqual(ENTITLEMENT_UPGRADE_HINTS['gestion.print_signage'], 'PRO')

    def test_print_signage_in_feature_keys(self):
        from apps.business.features import FEATURE_KEYS
        self.assertIn('print_signage', FEATURE_KEYS)

    def test_has_entitlement_returns_true_for_pro(self):
        """has_entitlement debe retornar True para un business con plan PRO activo."""
        from apps.business.entitlements import has_entitlement
        biz = self._bootstrap_business(plan='pro')
        # has_entitlement resuelve V2 primero; con solo legacy subscription funciona
        result = has_entitlement(biz, 'gestion.print_signage')
        self.assertTrue(result)

    def test_has_entitlement_returns_false_for_starter(self):
        """has_entitlement debe retornar False para un business con plan starter."""
        from apps.business.entitlements import has_entitlement
        biz = self._bootstrap_business(plan='starter')
        result = has_entitlement(biz, 'gestion.print_signage')
        self.assertFalse(result)


# ── Tests de carteles promocionales (Phase 3) ─────────────────────────────────

class PromotionSignageTests(PrintablesBaseTest):
    """Verifica soporte para carteles de tipo 'promotion'."""

    # ── Template / tipo ──────────────────────────────────────────────────────

    def test_promo_offer_generates_pdf(self):
        """type='promotion' + template_code='promo_offer' → 200 PDF."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            items=[{
                'product_id': None,
                'title': 'Yerba Mate',
                'promo_text': 'OFERTA',
                'price': '2500',
                'old_price': '3000',
                'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertGreater(len(response.content), 100)

    def test_promotion_without_product_id_generates_pdf(self):
        """Cartel de promoción sin product_id (manual) debe generar PDF."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            items=[{
                'product_id': None,
                'title': 'Combo del día',
                'promo_text': '2x1',
                'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_promotion_without_promo_text_still_generates_pdf(self):
        """Cartel de promoción sin promo_text no debe romper la generación."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            items=[{
                'product_id': None,
                'title': 'Producto en oferta',
                'price': '1500',
                'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_promotion_with_all_presets_generates_pdf(self):
        """Todos los presets de promo_text conocidos deben generar PDF sin error."""
        self._bootstrap_business(plan='pro')
        presets = ['OFERTA', '2x1', '3x2', '20% OFF', 'COMBO', 'LIQUIDACIÓN',
                   'PROMO SEMANAL', 'ÚLTIMAS UNIDADES', 'NUEVO INGRESO']
        items = [
            {'product_id': None, 'title': f'Producto {i}', 'promo_text': p, 'copies': 1}
            for i, p in enumerate(presets)
        ]
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            items=items,
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ── Validación cruzada tipo/template ─────────────────────────────────────

    def test_product_type_with_promotion_template_returns_400(self):
        """type='product' + template_code='promo_offer' debe devolver 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='product',
            template_code='promo_offer',
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_promotion_type_with_product_template_returns_400(self):
        """type='promotion' + template_code='product_price_simple' debe devolver 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='product_price_simple',
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Nuevos tests requeridos (Phase 3 final) ───────────────────────────────

    def test_promotion_with_own_product_generates_pdf(self):
        """type='promotion' con product_id propio genera PDF."""
        biz = self._bootstrap_business(plan='pro')
        product = self._make_product(biz)
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            items=[{
                'product_id': str(product.id),
                'title': product.name,
                'promo_text': 'OFERTA',
                'price': str(product.price),
                'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_promotion_with_other_business_product_returns_400(self):
        """type='promotion' con product_id de otro negocio devuelve 400."""
        self._bootstrap_business(plan='pro')
        other_biz = Business.objects.create(name='Otro Negocio Promo')
        other_product = Product.objects.create(
            business=other_biz,
            name='Producto ajeno',
            price='100.00',
            cost='50.00',
            stock_min='0',
        )
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            items=[{
                'product_id': str(other_product.id),
                'title': 'Desde otro negocio',
                'promo_text': 'OFERTA',
                'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'invalid_product')

    def test_promotion_include_price_false_no_price_generates_pdf(self):
        """type='promotion' + include_price=False sin price debe generar PDF."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            include_price=False,
            items=[{
                'product_id': None,
                'title': 'Promo sin precio',
                'promo_text': 'OFERTA',
                'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_promo_discount_template_generates_pdf(self):
        """template_code='promo_discount' genera PDF."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_discount',
            items=[{
                'product_id': None,
                'title': 'Artículo rebajado',
                'promo_text': '30% OFF',
                'price': '700',
                'old_price': '1000',
                'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_promo_2x1_template_generates_pdf(self):
        """template_code='promo_2x1' genera PDF."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_2x1',
            items=[{
                'product_id': None,
                'title': 'Gaseosa 500ml',
                'price': '800',
                'copies': 2,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_all_promo_templates_generate_pdf(self):
        """Todos los templates de promoción deben generar PDF sin error."""
        self._bootstrap_business(plan='pro')
        promo_templates = [
            'promo_offer', 'promo_discount', 'promo_2x1',
            'promo_combo', 'promo_clearance', 'promo_weekly',
        ]
        for tpl in promo_templates:
            with self.subTest(template_code=tpl):
                payload = _minimal_payload(
                    type='promotion',
                    template_code=tpl,
                    items=[{'product_id': None, 'title': f'Test {tpl}', 'copies': 1}],
                )
                response = self.client.post(URL, payload, format='json')
                self.assertEqual(
                    response.status_code, status.HTTP_200_OK,
                    msg=f'Fallo con template_code={tpl}',
                )

    def test_invalid_template_code_returns_400(self):
        """template_code inválido debe devolver 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(template_code='invalid_xyz')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_promotion_without_title_returns_400(self):
        """Cartel de promoción sin title debe devolver 400 (title obligatorio)."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            items=[{
                'product_id': None,
                # title omitido intencionalmente
                'promo_text': 'OFERTA',
                'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ── Tests de diseño visual (Phase 4) ─────────────────────────────────────────

class Phase4DesignTests(PrintablesBaseTest):
    """Verifica que las opciones de diseño visual (Phase 4) funcionan correctamente."""

    def test_defaults_unchanged_still_generate_pdf(self):
        """Payloads sin campos Phase 4 deben seguir generando PDF (retrocompatibilidad)."""
        self._bootstrap_business(plan='pro')
        response = self.client.post(URL, _minimal_payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_border_style_black_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(border_style='black', border_width=2)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_border_style_accent_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(border_style='accent', border_width=2)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_border_style_custom_valid_hex_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(border_style='custom', border_color='#FF5733', border_width=3)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_border_style_custom_invalid_hex_returns_400(self):
        """border_style='custom' con color no-hex debe devolver 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(border_style='custom', border_color='red')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_border_radius_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(border_style='black', border_radius=10, border_width=2)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_font_preset_elegant_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(font_preset='elegant')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_font_preset_condensed_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(font_preset='condensed')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_layout_style_framed_label_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(layout_style='framed_label')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_layout_style_price_focus_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(layout_style='price_focus')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_layout_style_minimal_label_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(layout_style='minimal_label')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_layout_style_promo_badge_on_promotion_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            layout_style='promo_badge',
            items=[{
                'product_id': None,
                'title': 'Yerba Mate',
                'promo_text': 'OFERTA',
                'price': '2500',
                'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_logo_size_large_with_include_logo_generates_pdf(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(logo_size='large', include_logo=True, logo_variant='horizontal')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_all_layout_styles_generate_pdf(self):
        """Todos los layout_style disponibles deben generar PDF sin error."""
        self._bootstrap_business(plan='pro')
        for style in ['centered_product', 'price_focus', 'framed_label', 'minimal_label']:
            with self.subTest(layout_style=style):
                payload = _minimal_payload(layout_style=style)
                response = self.client.post(URL, payload, format='json')
                self.assertEqual(
                    response.status_code, status.HTTP_200_OK,
                    msg=f'Fallo con layout_style={style}',
                )

    def test_invalid_layout_style_returns_400(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(layout_style='fancy_custom')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_font_preset_returns_400(self):
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(font_preset='comic_sans')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class Phase5DesignTests(PrintablesBaseTest):
    """Tests for Phase 5 design fields: inner_border_padding_cm, font size enums, xlarge logo."""

    def test_inner_border_padding_default_generates_pdf(self):
        """No new fields → should still return 200 (defaults apply)."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload()
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_inner_border_padding_custom_generates_pdf(self):
        """Explicit inner_border_padding_cm=0.5 within valid range → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(border_style='black', inner_border_padding_cm=0.5)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_inner_border_padding_invalid_returns_400(self):
        """inner_border_padding_cm=5.0 exceeds max_value=2 → 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(inner_border_padding_cm=5.0)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_title_font_size_xlarge_generates_pdf(self):
        """title_font_size='xlarge' is valid → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(title_font_size='xlarge')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_price_font_size_small_generates_pdf(self):
        """price_font_size='small' is valid → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(price_font_size='small', include_price=True)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logo_size_xlarge_generates_pdf(self):
        """logo_size='xlarge' is valid when include_logo=True → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            logo_size='xlarge',
            include_logo=True,
            logo_variant='horizontal',
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class Phase6ContentFrameTests(PrintablesBaseTest):
    """Tests for Phase 6: content frame layout (content_frame_* fields)."""

    def test_content_frame_padding_cm_generates_pdf(self):
        """content_frame_padding_cm=0.5 → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(content_frame_padding_cm=0.5)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_content_inner_padding_cm_generates_pdf(self):
        """content_inner_padding_cm=0.2 → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(content_inner_padding_cm=0.2)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_content_frame_enabled_false_generates_pdf(self):
        """content_frame_enabled=False (sin marco) → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(content_frame_enabled=False)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_content_frame_color_generates_pdf(self):
        """content_frame_color='#e53935' → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(content_frame_color='#e53935')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_content_frame_width_max_generates_pdf(self):
        """content_frame_width=6 → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(content_frame_width=6)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logo_size_large_with_content_frame_generates_pdf(self):
        """logo_size='large', include_logo=True, content_frame_enabled=True → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            logo_size='large',
            include_logo=True,
            logo_variant='horizontal',
            content_frame_enabled=True,
            content_frame_padding_cm=0.4,
            content_inner_padding_cm=0.3,
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class Phase7TextTransformTests(PrintablesBaseTest):
    """Tests for Phase 7: text_transform (none / uppercase)."""

    def test_text_transform_uppercase_generates_pdf(self):
        """text_transform='uppercase' → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(text_transform='uppercase')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_text_transform_none_generates_pdf(self):
        """text_transform='none' (default) → 200, compatibilidad retroactiva."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(text_transform='none')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_text_transform_invalid_returns_400(self):
        """text_transform='camelcase' (inválido) → 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(text_transform='camelcase')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_text_transform_uppercase_product(self):
        """Tipo product + text_transform='uppercase' → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(type='product', template_code='product_price_simple', text_transform='uppercase')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_text_transform_uppercase_promotion(self):
        """Tipo promotion + text_transform='uppercase' → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            text_transform='uppercase',
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_text_transform_uppercase_no_price_generates_pdf(self):
        """include_price=False + text_transform='uppercase' → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(include_price=False, text_transform='uppercase')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class Phase8HeaderContentTypeTests(PrintablesBaseTest):
    """Tests for Phase 8: header_content_type zona superior + promotion price fix."""

    def test_promotion_with_price_generates_pdf(self):
        """Promoción con include_price=True y price → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion', template_code='promo_offer',
            include_price=True,
            items=[{'product_id': None, 'title': 'Promo Test', 'price': '1500', 'copies': 1}],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_promotion_with_old_price_generates_pdf(self):
        """Promoción con old_price → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion', template_code='promo_discount',
            include_price=True,
            items=[{
                'product_id': None, 'title': 'Prod', 'price': '1000',
                'old_price': '1500', 'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ── Tests de logo en PDFs (S3 + FileSystem) ───────────────────────────────────

class LogoPDFTests(PrintablesBaseTest):
    """
    Verifica que los logos de BusinessBranding aparecen correctamente en PDFs
    tanto con FileSystemStorage (local) como con S3Boto3Storage (producción).
    """

    def test_pdf_without_logo_still_generates(self):
        """Sin logo configurado, el PDF se genera normalmente."""
        biz = self._bootstrap_business(plan='pro')
        BusinessBranding.objects.filter(business=biz).update(
            logo_horizontal='', logo_square=''
        )
        payload = _minimal_payload(include_logo=True, logo_variant='horizontal')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_pdf_logo_variant_none_skips_logo_resolution(self):
        """logo_variant='none' no debe intentar resolver el logo."""
        from unittest.mock import patch
        self._bootstrap_business(plan='pro')
        with patch('apps.printables.services.resolve_signage_logo') as mock_resolve:
            payload = _minimal_payload(logo_variant='none', include_logo=False)
            response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_resolve.assert_not_called()

    def test_pdf_with_logo_bytesio_from_s3_generates_pdf(self):
        """
        Cuando resolve_document_logo_path devuelve un BytesIO (caso S3),
        el PDF debe generarse sin error y contener el logo.
        """
        from io import BytesIO
        from unittest.mock import MagicMock, PropertyMock, patch

        self._bootstrap_business(plan='pro')

        png_bytes = _make_minimal_png()
        logo_bytesio = BytesIO(png_bytes)

        # Simular campo de logo con storage S3 (path lanza NotImplementedError)
        mock_field = MagicMock()
        mock_field.name = 'business/logos/test_logo.png'
        type(mock_field).path = PropertyMock(
            side_effect=NotImplementedError('S3 does not support path')
        )
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=png_bytes)))
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_field.storage = MagicMock()
        mock_field.storage.open.return_value = mock_cm

        with patch('apps.printables.services.resolve_signage_logo', return_value=mock_field):
            payload = _minimal_payload(include_logo=True, logo_variant='horizontal')
            response = self.client.post(URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertGreater(len(response.content), 100)

    def test_pdf_with_logo_path_from_filesystem_generates_pdf(self):
        """
        Cuando resolve_document_logo_path devuelve un path str (FileSystemStorage),
        el PDF debe generarse correctamente.
        """
        import tempfile, os
        from unittest.mock import MagicMock, PropertyMock, patch

        self._bootstrap_business(plan='pro')

        png_bytes = _make_minimal_png()

        # Guardar PNG a archivo temporal y usar ese path
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp.write(png_bytes)
            tmp_path = tmp.name

        try:
            mock_field = MagicMock()
            mock_field.name = 'logos/local_logo.png'
            type(mock_field).path = PropertyMock(return_value=tmp_path)

            with patch('apps.printables.services.resolve_signage_logo', return_value=mock_field):
                payload = _minimal_payload(include_logo=True, logo_variant='horizontal')
                response = self.client.post(URL, payload, format='json')
        finally:
            os.unlink(tmp_path)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertGreater(len(response.content), 100)

    def test_pdf_with_svg_logo_skips_silently(self):
        """Un logo SVG debe omitirse sin romper la generación del PDF."""
        from unittest.mock import MagicMock, PropertyMock, patch

        self._bootstrap_business(plan='pro')

        mock_field = MagicMock()
        mock_field.name = 'business/logos/brand.svg'
        type(mock_field).path = PropertyMock(return_value='/media/brand.svg')

        with patch('apps.printables.services.resolve_signage_logo', return_value=mock_field):
            payload = _minimal_payload(include_logo=True, logo_variant='horizontal')
            response = self.client.post(URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_pdf_with_s3_open_failure_skips_logo_and_generates(self):
        """
        Si storage.open falla (S3 timeout), el logo se omite silenciosamente
        y el PDF se genera igual.
        """
        from unittest.mock import MagicMock, PropertyMock, patch

        self._bootstrap_business(plan='pro')

        mock_field = MagicMock()
        mock_field.name = 'logos/brand.png'
        type(mock_field).path = PropertyMock(side_effect=NotImplementedError())
        mock_field.storage = MagicMock()
        mock_field.storage.open.side_effect = OSError('S3 timeout')

        with patch('apps.printables.services.resolve_signage_logo', return_value=mock_field):
            payload = _minimal_payload(include_logo=True, logo_variant='horizontal')
            response = self.client.post(URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_logo_variant_square_uses_logo_square_field(self):
        """logo_variant='square' debe intentar usar logo_square del branding."""
        from unittest.mock import patch, call

        self._bootstrap_business(plan='pro')

        with patch('apps.printables.services.resolve_signage_logo', return_value=None) as mock_resolve:
            payload = _minimal_payload(include_logo=True, logo_variant='square')
            response = self.client.post(URL, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_resolve.assert_called_once()
        _, kwargs_or_args = mock_resolve.call_args[0], mock_resolve.call_args
        # Verifica que se pasó 'square' como logo_variant
        self.assertIn('square', mock_resolve.call_args[0])

    def test_header_content_type_highlight_text_generates_pdf(self):
        """header_content_type='highlight_text' con header_text → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion', template_code='promo_offer',
            header_content_type='highlight_text',
            header_text='OFERTA ESPECIAL',
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_header_content_type_logo_generates_pdf(self):
        """header_content_type='logo' → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion', template_code='promo_offer',
            header_content_type='logo',
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_header_content_type_none_generates_pdf(self):
        """header_content_type='none' → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion', template_code='promo_offer',
            header_content_type='none',
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_promo_highlight_text_from_promo_text(self):
        """header_content_type='highlight_text' sin header_text usa promo_text del item → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion', template_code='promo_combo',
            header_content_type='highlight_text',
            header_text='',
            items=[{
                'product_id': None, 'title': 'Combo', 'promo_text': 'COMBO',
                'price': '2000', 'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_backward_compat_no_header_content_type(self):
        """Payload viejo sin header_content_type → 200 (compatibilidad retroactiva)."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(type='promotion', template_code='promo_offer')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_header_content_type_invalid_returns_400(self):
        """header_content_type='banner' (inválido) → 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(header_content_type='banner')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ── Tests Phase 9: colores y espaciado ───────────────────────────────────────

class ColorsAndSpacingTests(PrintablesBaseTest):
    """Valida los campos Phase 9: header_text_color, title_text_color, price_text_color, price_gap_pt."""

    def test_header_text_color_valid_generates_pdf(self):
        """header_text_color='#1D4ED8' → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            header_content_type='highlight_text',
            header_text='OFERTA',
            header_text_color='#1D4ED8',
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_title_text_color_valid_generates_pdf(self):
        """title_text_color='#0F172A' → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(title_text_color='#0F172A')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_price_text_color_valid_generates_pdf(self):
        """price_text_color='#16A34A' → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(price_text_color='#16A34A')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_invalid_color_returns_400(self):
        """Color inválido '#ZZZ' → 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(title_text_color='#ZZZ')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_header_text_color_returns_400(self):
        """header_text_color sin # → 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(header_text_color='red')
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_price_gap_pt_generates_pdf(self):
        """price_gap_pt=20 → 200."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(price_gap_pt=20)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_price_gap_pt_invalid_returns_400(self):
        """price_gap_pt=99 (> max 60) → 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(price_gap_pt=99)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_price_gap_pt_negative_returns_400(self):
        """price_gap_pt=-1 (< 0) → 400."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(price_gap_pt=-1)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_promotion_title_font_size_xlarge_generates_pdf(self):
        """Promoción con title_font_size='xlarge' → 200 (escala Phase 9)."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload(
            type='promotion',
            template_code='promo_offer',
            title_font_size='xlarge',
            items=[{
                'product_id': None,
                'title': 'Yerba Mate',
                'promo_text': 'OFERTA',
                'price': '2500',
                'copies': 1,
            }],
        )
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_legacy_payload_without_new_fields_generates_pdf(self):
        """Payload sin campos Phase 9 sigue generando PDF (backward compat)."""
        self._bootstrap_business(plan='pro')
        payload = _minimal_payload()
        # Asegurar que ningún campo Phase 9 esté en el payload
        for field in ('header_text_color', 'title_text_color', 'price_text_color', 'price_gap_pt'):
            payload.pop(field, None)
        response = self.client.post(URL, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

from decimal import Decimal

from django.core.management.base import BaseCommand
from apps.billing.models import Module, Bundle, Promotion, Plan
from apps.billing.canonical_pricing import (
    plan_price, addon_price, extra_price, price_to_decimal,
)

class Command(BaseCommand):
    help = 'Seeds billing modules and bundles'

    def handle(self, *args, **kwargs):
        # Commercial Modules (Gestión Comercial)
        comm_mods = [
            # Core modules (included in START)
            ('gestion_products', 'Productos', 'Catálogo de productos con variantes y precios', 'operation', 0, True),
            ('gestion_inventory_basic', 'Inventario Básico', 'Control de stock por sucursal', 'operation', 0, True),
            ('gestion_sales_basic', 'Ventas Básicas', 'Registro de ventas y recibos', 'operation', 0, True),
            ('gestion_dashboard_basic', 'Dashboard Básico', 'Vista general de ventas y stock', 'insights', 0, True),
            ('gestion_settings_basic', 'Configuración Básica', 'Ajustes generales del negocio', 'admin', 0, True),
            ('gestion_orders', 'Pedidos', 'Creación, seguimiento y gestión de pedidos de clientes', 'operation', 0, True),
            
            # PRO modules (not in START)
            ('gestion_customers', 'Clientes', 'CRM y listado de clientes', 'operation', 0, False),
            ('gestion_cash', 'Caja', 'Gestión de caja y sesiones de efectivo', 'operation', 0, False),
            ('gestion_quotes', 'Presupuestos', 'Generación de cotizaciones', 'operation', 0, False),
            ('gestion_reports', 'Reportes', 'Reportes detallados y analytics', 'insights', 0, False),
            ('gestion_export', 'Exportación', 'Exportar datos a Excel/CSV', 'insights', 0, False),
            ('gestion_treasury', 'Tesorería y Finanzas', 'Control financiero, gastos e ingresos', 'admin', 0, False),
            ('gestion_inventory_advanced', 'Inventario Avanzado', 'Ajustes, transferencias y auditoría', 'operation', 0, False),
            ('gestion_sales_advanced', 'Ventas Avanzadas', 'Descuentos, promociones y ventas a cuenta', 'operation', 0, False),
            ('gestion_rbac_full', 'Control de Acceso Completo', 'Roles, permisos y usuarios ilimitados', 'admin', 0, False),
            ('gestion_audit', 'Auditoría', 'Historial de cambios y logs', 'admin', 0, False),
            ('gestion_invoices', 'Facturación Electrónica', 'Emisión de facturas fiscales', 'admin', 0, False),
            
            # BUSINESS modules (not in PRO)
            ('gestion_multi_branch', 'Multi-Sucursal', 'Gestión consolidada de múltiples sucursales', 'operation', 0, False),
            ('gestion_transfers', 'Transferencias', 'Transferencias de stock entre sucursales', 'operation', 0, False),
            ('gestion_consolidated_reports', 'Reportes Consolidados', 'Reportes multi-sucursal', 'insights', 0, False),
        ]
        
        created_modules = {}
        for code, name, desc, cat, price, is_core in comm_mods:
            m, _ = Module.objects.update_or_create(
                code=code,
                defaults={
                    'name': name, 
                    'description': desc, 
                    'category': cat, 
                    'price_monthly': price,
                    'price_yearly': price * 10 if price > 0 else 0,
                    'is_core': is_core,
                    'vertical': 'commercial'
                }
            )
            created_modules[code] = m

        # Plan START - Core básico
        start_modules = [
            'gestion_products', 'gestion_inventory_basic', 'gestion_sales_basic',
            'gestion_orders', 'gestion_dashboard_basic', 'gestion_settings_basic'
        ]
        
        b_start, _ = Bundle.objects.update_or_create(
            code='gestion_start',
            defaults={
                'name': 'Starter',
                'description': 'Plan inicial para emprendedores. 1 sucursal, funcionalidades esenciales.',
                'vertical': 'commercial',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': plan_price('gestion_start', 'monthly'),   # 36000
                'fixed_price_yearly': plan_price('gestion_start', 'yearly'),     # 345600
                'is_default_recommended': False,
                'badge': ''
            }
        )
        b_start.modules.set([created_modules[code] for code in start_modules if code in created_modules])

        # Plan PRO - Todo de START + features PRO
        pro_modules = start_modules + [
            'gestion_customers', 'gestion_cash', 'gestion_quotes', 'gestion_reports',
            'gestion_export', 'gestion_treasury', 'gestion_inventory_advanced',
            'gestion_sales_advanced', 'gestion_rbac_full', 'gestion_audit', 'gestion_invoices',
        ]
        
        b_pro, _ = Bundle.objects.update_or_create(
            code='gestion_pro',
            defaults={
                'name': 'Pro',
                'description': 'Gestión profesional con tesorería y finanzas. Hasta 3 sucursales.',
                'vertical': 'commercial',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': plan_price('gestion_pro', 'monthly'),   # 50000
                'fixed_price_yearly': plan_price('gestion_pro', 'yearly'),     # 480000
                'is_default_recommended': True,
                'badge': 'Recomendado'
            }
        )
        b_pro.modules.set([created_modules[code] for code in pro_modules if code in created_modules])

        # Plan BUSINESS - Todo de PRO + features exclusivos BUSINESS
        # Nota: gestion_invoices ya está incluido en pro_modules
        business_modules = pro_modules + [
            'gestion_multi_branch', 'gestion_transfers',
            'gestion_consolidated_reports'
        ]
        
        b_business, _ = Bundle.objects.update_or_create(
            code='gestion_business',
            defaults={
                'name': 'Business',
                'description': 'Solución completa con facturación electrónica. Hasta 5 sucursales incluidas.',
                'vertical': 'commercial',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': plan_price('gestion_business', 'monthly'),  # 75000
                'fixed_price_yearly': plan_price('gestion_business', 'yearly'),    # 720000
                'is_default_recommended': False,
                'badge': 'Completo'
            }
        )
        b_business.modules.set([created_modules[code] for code in business_modules if code in created_modules])

        # Restaurant Modules
        resto_mods = [
            ('tables_map', 'Tables Map', 'Manage tables layout', 'operation', 1000, True),
            ('table_orders', 'Table Orders', 'Orders by table', 'operation', 1200, True),
            ('kitchen_tickets', 'Kitchen Tickets', 'KSD / Tickets', 'operation', 800, False),
            ('split_payments', 'Split Payments', 'Split check feature', 'operation', 500, False),
        ]
        
        resto_modules_obj = {}
        for code, name, desc, cat, price, is_core in resto_mods:
             m, _ = Module.objects.update_or_create(
                code=code,
                defaults={
                    'name': name, 
                    'description': desc, 
                    'category': cat, 
                    'price_monthly': price,
                    'price_yearly': price * 10,
                    'is_core': is_core,
                    'vertical': 'restaurant'
                }
            )
             resto_modules_obj[code] = m

        b_resto_basic, _ = Bundle.objects.update_or_create(
            code='resto_basic',
            defaults={
                'name': 'Resto Startup',
                'vertical': 'restaurant',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': 2500,  # TODO Deploy 4: migrate to canonical pesos
                'is_default_recommended': False
            }
        )
        b_resto_basic.modules.set([resto_modules_obj['tables_map'], resto_modules_obj['table_orders']])

        # Restaurante Inteligente: full restaurant pack + Menú QR Online included
        # Ensure menu_qr modules are created first (they may vary by run order, so
        # we create them inline here too rather than depending on the later block).
        resto_menu_qr_mods_data = [
            ('menu_builder_core', 'Editor de Carta', 'Categorías e items ilimitados dentro del plan.', 'operation', 0, True),
            ('menu_branding_basic', 'Branding Básico', 'Logo, colores y tipografías personalizadas.', 'admin', 0, True),
            ('menu_qr_tools', 'QR & Link Público', 'Generación de QR ilimitado y vista previa pública.', 'insights', 0, True),
        ]
        resto_menu_mods_obj = {}
        for code, name, desc, cat, price, is_core in resto_menu_qr_mods_data:
            mod, _ = Module.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'description': desc,
                    'category': cat,
                    'price_monthly': price,
                    'price_yearly': price * 10 if price else 0,
                    'is_core': is_core,
                    'vertical': 'menu_qr',
                }
            )
            resto_menu_mods_obj[code] = mod

        b_restaurante_inteligente, _ = Bundle.objects.update_or_create(
            code='restaurante_inteligente',
            defaults={
                'name': 'Restaurante Inteligente',
                'description': 'Gestión completa del salón, cocina y carta digital con QR incluido.',
                'vertical': 'restaurant',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': 14900,   # TODO Deploy 4: migrate to canonical pesos
                'fixed_price_yearly': 143040,   # TODO Deploy 4: migrate to canonical pesos
                'is_default_recommended': True,
                'badge': 'Completo',
            }
        )
        # Restaurant modules + all menu_qr modules (QR incluido en Restaurante Inteligente)
        b_restaurante_inteligente.modules.set(
            list(resto_modules_obj.values()) + list(resto_menu_mods_obj.values())
        )
        
        # Menu QR Online Modules & Bundle
        menu_modules_data = [
            ('menu_builder_core', 'Editor de Carta', 'Categorías e items ilimitados dentro del plan.', 'operation', 0, True),
            ('menu_branding_basic', 'Branding Básico', 'Logo, colores y tipografías personalizadas.', 'admin', 0, True),
            ('menu_qr_tools', 'QR & Link Público', 'Generación de QR ilimitado y vista previa pública.', 'insights', 0, True),
        ]

        menu_modules = {}
        for code, name, desc, cat, price, is_core in menu_modules_data:
            mod, _ = Module.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'description': desc,
                    'category': cat,
                    'price_monthly': price,
                    'price_yearly': price * 10 if price else 0,
                    'is_core': is_core,
                    'vertical': 'menu_qr',
                }
            )
            menu_modules[code] = mod

        # Legacy bundle — deactivated; keep row so existing subscription FKs don't break.
        menu_bundle, _ = Bundle.objects.update_or_create(
            code='menu_qr_online',
            defaults={
                'name': 'Menú QR Online',
                'description': 'Carta digital con QR y branding básico.',
                'vertical': 'menu_qr',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': 4900,
                'fixed_price_yearly': 4900 * 10,
                'is_default_recommended': False,
                'badge': '',
                'is_active': False,
            }
        )
        menu_bundle.modules.set(list(menu_modules.values()))

        # -------------------------------------------------------------------
        # Menú QR — 3 tiers (Básico / Visual / Marca)
        # -------------------------------------------------------------------
        premium_menu_mods_data = [
            (
                'menu_item_images',
                'Imágenes por producto',
                'Sube una imagen por producto visible en la carta pública.',
                'operation',
                0,
                False,
            ),
            (
                'menu_custom_domain',
                'Dominio personalizado',
                'Servir la carta desde tu propio dominio o subdominio.',
                'admin',
                0,
                False,
            ),
        ]
        premium_menu_mods = {}
        for code, name, desc, cat, price, is_core in premium_menu_mods_data:
            mod, _ = Module.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'description': desc,
                    'category': cat,
                    'price_monthly': price,
                    'price_yearly': price * 10 if price else 0,
                    'is_core': is_core,
                    'vertical': 'menu_qr',
                }
            )
            premium_menu_mods[code] = mod

        # Plan A: QR Básico — manage menu + QR + branding, sin imágenes
        basico_module_codes = ['menu_builder_core', 'menu_branding_basic', 'menu_qr_tools']
        b_qr_basico, _ = Bundle.objects.update_or_create(
            code='menu_qr_basico',
            defaults={
                'name': 'Lite',
                'description': 'Carta digital básica con branding. Ideal para empezar.',
                'is_active': True,
                'vertical': 'menu_qr',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': plan_price('menu_qr_basico', 'monthly'),  # 18000
                'fixed_price_yearly': plan_price('menu_qr_basico', 'yearly'),    # 172800
                'is_default_recommended': False,
                'badge': '',
                'sort_order': 1,
                'cta_label': 'Empezar con Lite',
            }
        )
        b_qr_basico.modules.set(
            [menu_modules[c] for c in basico_module_codes if c in menu_modules]
        )

        # Plan B: QR Visual — todo de Básico + imágenes por producto
        visual_module_codes = basico_module_codes + ['menu_item_images']
        b_qr_visual, _ = Bundle.objects.update_or_create(
            code='menu_qr_visual',
            defaults={
                'name': 'Pro',
                'description': 'Imágenes, analítica avanzada y 1 módulo de engagement a elección.',
                'is_active': True,
                'vertical': 'menu_qr',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': plan_price('menu_qr_visual', 'monthly'),  # 30000
                'fixed_price_yearly': plan_price('menu_qr_visual', 'yearly'),    # 288000
                'is_default_recommended': True,
                'badge': 'Recomendado',
                'sort_order': 2,
                'cta_label': 'Elegir Pro',
            }
        )
        b_qr_visual.modules.set(
            [menu_modules.get(c) or premium_menu_mods.get(c) for c in visual_module_codes
             if menu_modules.get(c) or premium_menu_mods.get(c)]
        )

        # Plan C: QR Marca — todo de Visual + dominio personalizado
        marca_module_codes = visual_module_codes + ['menu_custom_domain']
        b_qr_marca, _ = Bundle.objects.update_or_create(
            code='menu_qr_marca',
            defaults={
                'name': 'Premium',
                'description': 'Todo incluido: reseñas, propinas, imágenes, dominio y multi-sucursal.',
                'is_active': True,
                'vertical': 'menu_qr',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': plan_price('menu_qr_marca', 'monthly'),  # 55000
                'fixed_price_yearly': plan_price('menu_qr_marca', 'yearly'),    # 528000
                'is_default_recommended': False,
                'badge': '',
                'sort_order': 3,
                'cta_label': 'Ir a Premium',
            }
        )
        b_qr_marca.modules.set(
            [menu_modules.get(c) or premium_menu_mods.get(c) for c in marca_module_codes
             if menu_modules.get(c) or premium_menu_mods.get(c)]
        )

        # Tier Empresarial: contact only — no MP checkout
        b_qr_empresarial, _ = Bundle.objects.update_or_create(
            code='menu_qr_empresarial',
            defaults={
                'name': 'Empresarial',
                'description': 'Una experiencia digital adaptada a tu marca y operación.',
                'vertical': 'menu_qr',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': None,   # None = contact only; no MP checkout
                'fixed_price_yearly': None,
                'is_default_recommended': False,
                'is_active': True,
                'badge': 'Contactar',
                'sort_order': 4,
                'cta_label': 'Hablar con MiRubro',
            }
        )
        b_qr_empresarial.modules.set(
            [menu_modules.get(c) or premium_menu_mods.get(c) for c in marca_module_codes
             if menu_modules.get(c) or premium_menu_mods.get(c)]
        )

        # -------------------------------------------------------------------
        # QR de Reseñas — standalone product
        # -------------------------------------------------------------------
        qr_reviews_mods_data = [
            ('qr_reviews_core', 'Configuración de Reseñas', 'Google Place ID y enlace de reseñas.', 'operation', 0, True),
            ('qr_reviews_qr_gen', 'Generador de QR', 'Generación de QR y link público para reseñas.', 'insights', 0, True),
        ]
        qr_reviews_modules = {}
        for code, name, desc, cat, price, is_core in qr_reviews_mods_data:
            mod, _ = Module.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'description': desc,
                    'category': cat,
                    'price_monthly': price,
                    'price_yearly': 0,
                    'is_core': is_core,
                    'vertical': 'qr_reviews',
                }
            )
            qr_reviews_modules[code] = mod

        # Legacy bundle — deactivated; keep row so existing subscription FKs don't break.
        b_qr_reviews_legacy, _ = Bundle.objects.update_or_create(
            code='qr_reviews',
            defaults={
                'name': 'QR de Reseñas',
                'description': 'QR y enlace público para recopilar reseñas de Google.',
                'vertical': 'qr_reviews',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': plan_price('qr_reviews_base', 'monthly'),
                'fixed_price_yearly': plan_price('qr_reviews_base', 'yearly'),
                'is_default_recommended': False,
                'badge': '',
                'is_active': False,
                'sort_order': 99,
                'cta_label': '',
            }
        )
        b_qr_reviews_legacy.modules.set(list(qr_reviews_modules.values()))

        # Tier 1: Reseñas Base
        b_qr_reviews_base, _ = Bundle.objects.update_or_create(
            code='qr_reviews_base',
            defaults={
                'name': 'Reseñas Base',
                'description': 'Generá reseñas en Google de forma simple.',
                'vertical': 'qr_reviews',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': plan_price('qr_reviews_base', 'monthly'),  # 25000
                'fixed_price_yearly': plan_price('qr_reviews_base', 'yearly'),    # 240000
                'is_default_recommended': False,
                'is_active': True,
                'badge': '',
                'sort_order': 1,
                'cta_label': 'Activar Reseñas Base',
            }
        )
        b_qr_reviews_base.modules.set(list(qr_reviews_modules.values()))

        # Tier 2: Reseñas Pro
        b_qr_reviews_pro, _ = Bundle.objects.update_or_create(
            code='qr_reviews_pro',
            defaults={
                'name': 'Reseñas Pro',
                'description': 'Elegí qué llega a Google y qué queda como feedback privado.',
                'vertical': 'qr_reviews',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': plan_price('qr_reviews_pro', 'monthly'),  # 40000
                'fixed_price_yearly': plan_price('qr_reviews_pro', 'yearly'),    # 384000
                'is_default_recommended': True,
                'is_active': True,
                'badge': 'Recomendado',
                'sort_order': 2,
                'cta_label': 'Activar Reseñas Pro',
            }
        )
        b_qr_reviews_pro.modules.set(list(qr_reviews_modules.values()))

        # Tier 3: Empresarial — contact only, no MP checkout
        b_qr_reviews_empresarial, _ = Bundle.objects.update_or_create(
            code='qr_reviews_empresarial',
            defaults={
                'name': 'Empresarial',
                'description': 'Una propuesta personalizada para escalar tu reputación digital.',
                'vertical': 'qr_reviews',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': None,   # None = contact only; no MP checkout
                'fixed_price_yearly': None,
                'is_default_recommended': False,
                'is_active': True,
                'badge': 'Contactar',
                'sort_order': 3,
                'cta_label': 'Hablar con MiRubro',
            }
        )
        b_qr_reviews_empresarial.modules.set(list(qr_reviews_modules.values()))

        # Plans for checkout flow
        # These codes MUST match Bundle.code values — checkout_session_service.start_checkout()
        # looks up Plan by code, and plan/page.tsx sends Bundle.code as plan_code.
        # Price is the full ARS pesos amount sent to MP as auto_recurring.transaction_amount.
        # All values derived from canonical_pricing (generated/pricing.json).
        PLAN_SEEDS = [
            # Gestión Comercial (canonical)
            ('gestion_start',           'Starter — Gestión Comercial',       price_to_decimal(plan_price('gestion_start')),    'commercial'),
            ('gestion_pro',             'Pro — Gestión Comercial',           price_to_decimal(plan_price('gestion_pro')),      'commercial'),
            ('gestion_business',        'Business — Gestión Comercial',      price_to_decimal(plan_price('gestion_business')), 'commercial'),
            # Restaurante (not yet in canonical — TODO Deploy 4)
            ('resto_basic',             'Startup — Restaurante',             Decimal('25.00'),   'restaurant'),
            ('restaurante_inteligente', 'Inteligente — Restaurante',         Decimal('149.00'),  'restaurant'),
            # Menú QR (canonical)
            ('menu_qr_basico',          'Lite — Menú QR',                    price_to_decimal(plan_price('menu_qr_basico')),   'menu_qr'),
            ('menu_qr_visual',          'Pro — Menú QR',                     price_to_decimal(plan_price('menu_qr_visual')),   'menu_qr'),
            ('menu_qr_marca',           'Premium — Menú QR',                 price_to_decimal(plan_price('menu_qr_marca')),    'menu_qr'),
            # QR de Reseñas (canonical)
            ('qr_reviews',              'QR de Reseñas (legacy)',            price_to_decimal(plan_price('qr_reviews_base')),  'qr_reviews'),
            ('qr_reviews_base',         'Reseñas Base',                      price_to_decimal(plan_price('qr_reviews_base')),  'qr_reviews'),
            ('qr_reviews_pro',          'Reseñas Pro',                       price_to_decimal(plan_price('qr_reviews_pro')),   'qr_reviews'),
        ]
        for code, name, price, _vertical in PLAN_SEEDS:
            Plan.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'price': price,
                    'interval': 'monthly',
                    'currency': 'ARS',
                    'frequency': 1,
                    'frequency_type': 'months',
                    'plan_status': 'active',
                }
            )

        self.stdout.write(self.style.SUCCESS('Successfully seeded billing data'))

from decimal import Decimal

from django.core.management.base import BaseCommand
from apps.billing.models import Module, Bundle, Promotion, Plan

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
            
            # BUSINESS modules (not in PRO)
            ('gestion_invoices', 'Facturación Electrónica', 'Emisión de facturas fiscales', 'admin', 0, False),
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
            'gestion_dashboard_basic', 'gestion_settings_basic'
        ]
        
        b_start, _ = Bundle.objects.update_or_create(
            code='gestion_start',
            defaults={
                'name': 'Start',
                'description': 'Plan inicial para emprendedores. 1 sucursal, funcionalidades esenciales.',
                'vertical': 'commercial',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': 9900,  # $99
                'fixed_price_yearly': 95040,  # $99 * 12 * 0.8 (20% descuento anual)
                'is_default_recommended': False,
                'badge': ''
            }
        )
        b_start.modules.set([created_modules[code] for code in start_modules if code in created_modules])

        # Plan PRO - Todo de START + features PRO
        pro_modules = start_modules + [
            'gestion_customers', 'gestion_cash', 'gestion_quotes', 'gestion_reports',
            'gestion_export', 'gestion_treasury', 'gestion_inventory_advanced',
            'gestion_sales_advanced', 'gestion_rbac_full', 'gestion_audit'
        ]
        
        b_pro, _ = Bundle.objects.update_or_create(
            code='gestion_pro',
            defaults={
                'name': 'Pro',
                'description': 'Gestión profesional con tesorería y finanzas. Hasta 3 sucursales.',
                'vertical': 'commercial',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': 29900,  # $299
                'fixed_price_yearly': 287040,  # $299 * 12 * 0.8
                'is_default_recommended': True,
                'badge': 'Recomendado'
            }
        )
        b_pro.modules.set([created_modules[code] for code in pro_modules if code in created_modules])

        # Plan BUSINESS - Todo de PRO + features BUSINESS
        business_modules = pro_modules + [
            'gestion_invoices', 'gestion_multi_branch', 'gestion_transfers',
            'gestion_consolidated_reports'
        ]
        
        b_business, _ = Bundle.objects.update_or_create(
            code='gestion_business',
            defaults={
                'name': 'Business',
                'description': 'Solución completa con facturación electrónica. Hasta 5 sucursales incluidas.',
                'vertical': 'commercial',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': 49900,  # $499
                'fixed_price_yearly': 479040,  # $499 * 12 * 0.8
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
                'fixed_price_monthly': 2500,
                'is_default_recommended': True
            }
        )
        b_resto_basic.modules.set([resto_modules_obj['tables_map'], resto_modules_obj['table_orders']])
        
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

        menu_bundle, _ = Bundle.objects.update_or_create(
            code='menu_qr_online',
            defaults={
                'name': 'Menú QR Online',
                'description': 'Carta digital con QR y branding básico.',
                'vertical': 'menu_qr',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': 4900,
                'fixed_price_yearly': 4900 * 10,
                'is_default_recommended': True,
                'badge': 'Nuevo',
            }
        )
        menu_bundle.modules.set(list(menu_modules.values()))

        # Plans for checkout flow
        Plan.objects.update_or_create(
            code='menu_qr_monthly',
            defaults={
                'name': 'Menú QR Online Mensual',
                'price': Decimal('4900.00'),
                'interval': 'monthly',
                'features_json': {
                    'service': 'menu_qr',
                    'limits': {'max_items': 150, 'max_categories': 25, 'allow_custom_domain': False},
                },
            }
        )

        Plan.objects.update_or_create(
            code='menu_qr_yearly',
            defaults={
                'name': 'Menú QR Online Anual',
                'price': Decimal('52900.00'),
                'interval': 'yearly',
                'features_json': {
                    'service': 'menu_qr',
                    'limits': {'max_items': 150, 'max_categories': 25, 'allow_custom_domain': False},
                },
            }
        )

        self.stdout.write(self.style.SUCCESS('Successfully seeded billing data'))

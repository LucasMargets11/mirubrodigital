from django.core.management.base import BaseCommand
from apps.billing.models import Module, Bundle, Promotion

class Command(BaseCommand):
    help = 'Seeds billing modules and bundles'

    def handle(self, *args, **kwargs):
        # Commercial Modules
        comm_mods = [
            ('stock', 'Stock', 'Inventory management', 'operation', 1000, True),
            ('orders_sales', 'Orders & Sales', 'Sales processing', 'operation', 1500, True),
            ('cash_register', 'Cash Register', 'Cash management', 'operation', 800, False), # requires sales
            ('invoicing', 'Invoicing', 'Fiscal invoicing', 'admin', 1200, False),
            ('customers', 'Customers', 'CRM', 'operation', 500, False),
            ('reports_basic', 'Basic Reports', 'Daily stats', 'insights', 0, True),
            ('reports_advanced', 'Advanced Reports', 'Deep analytics', 'insights', 2000, False),
            ('users_roles', 'Users & Roles', 'Team management', 'admin', 800, False),
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
                    'price_yearly': price * 10, # discount
                    'is_core': is_core,
                    'vertical': 'commercial'
                }
            )
            created_modules[code] = m
            
        # Dependencies
        if 'cash_register' in created_modules and 'orders_sales' in created_modules:
            created_modules['cash_register'].requires.add(created_modules['orders_sales'])

        # Bundles
        b_initial, _ = Bundle.objects.update_or_create(
            code='comm_initial',
            defaults={
                'name': 'Pack Inicial',
                'vertical': 'commercial',
                'pricing_mode': 'fixed_price',
                'fixed_price_monthly': 2000,
                'is_default_recommended': True,
                'badge': 'Recomendado'
            }
        )
        b_initial.modules.set([
            created_modules['stock'], created_modules['orders_sales'], 
            created_modules['reports_basic']
        ])

        b_full, _ = Bundle.objects.update_or_create(
            code='comm_full',
            defaults={
                'name': 'Pack Full',
                'vertical': 'commercial',
                'pricing_mode': 'discount_percent',
                'discount_percent': 20.00,
            }
        )
        b_full.modules.set(list(created_modules.values()))

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
        
        self.stdout.write(self.style.SUCCESS('Successfully seeded billing data'))

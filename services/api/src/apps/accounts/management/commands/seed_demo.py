from __future__ import annotations

import datetime
import random
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.utils import timezone

from apps.accounts.models import Membership
from apps.business.models import Business, BusinessPlan, Subscription
from apps.cash.models import CashRegister, CashSession
from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.inventory.models import ProductStock, StockMovement
from apps.menu.models import MenuCategory, MenuItem, ensure_menu_branding, ensure_public_menu_config
from apps.orders.models import Order, OrderItem
from apps.resto.models import Table, TableLayout
from apps.sales.models import Sale, SaleItem
from apps.treasury.models import Account, TransactionCategory, Transaction, ExpenseTemplate, Expense, Employee, PayrollPayment, TreasurySettings

User = get_user_model()
DEFAULT_PASSWORD = 'mirubro123'

class Command(BaseCommand):
    help = "Seed demo data for development (Manzana & La Pizza)"

    def add_arguments(self, parser):
        parser.add_argument('--flush', action='store_true', help='Clean database before seeding')
        parser.add_argument('--only', type=str, help='Seed only specific tenant (manzana|lapizza|all)')
        parser.add_argument('--no-input', action='store_true', help='Do not prompt for input')

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Starting Seed Demo..."))

        if options['flush']:
            if options['no_input'] or input("Are you sure you want to flush the database? This will DELETE ALL DATA. (y/N): ").lower() == 'y':
                self.stdout.write("Flushing database (ORM cascade)...")
                # Using ORM delete instead of call_command('flush') to avoid transaction/connection state issues in same process
                self.flush_all_data()
                self.stdout.write("Flush complete.")
            else:
                self.stdout.write("Flush cancelled. Proceeding with existing data...")

        # If we didn't flush, we might want to clean up specific demo tenants to ensure idempotency
        if not options['flush']:
             self.cleanup_demo_data()

        target = options.get('only') or 'all'

        if target in ['manzana', 'all']:
            self.seed_manzana()
        
        if target in ['lapizza', 'all']:
            self.seed_lapizza()

        if target in ['menuqr', 'all']:
            self.seed_menu_qr()

        self.stdout.write(self.style.SUCCESS('Successfully seeded demo data.'))
        self.print_summary()

    def cleanup_demo_data(self):
        self.stdout.write("Cleaning up existing demo tenants/users for idempotency...")
        # Delete tenants by name/slug logic
        targets = ["Manzana", "Manzana HQ", "La Pizza", "Demo QR"]
        # Delete children first
        Business.objects.filter(parent__name__in=targets).delete()
        Business.objects.filter(name__in=targets).delete()
        # Delete specific users
        User.objects.filter(email__endswith="@mirubro.local").delete()

    def flush_all_data(self):
        # Delete transactional data first (reverse dependency order)
        self.stdout.write("  Deleting transactional data...")
        
        # Inventory / Sales / Orders
        try:
            StockMovement.objects.all().delete()
        except Exception:
            pass # Ignore if model doesn't exist or table missing
            
        SaleItem.objects.all().delete()
        Sale.objects.all().delete()
        
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        
        # Cash
        CashSession.objects.all().delete()
        CashRegister.objects.all().delete()

        self.stdout.write("  Deleting master data...")
        # Resto
        MenuItem.objects.all().delete()
        MenuCategory.objects.all().delete()
        Table.objects.all().delete()
        try:
            TableLayout.objects.all().delete()
        except:
            pass
            
        # Catalog / Customers
        ProductStock.objects.all().delete()
        Product.objects.all().delete()
        Customer.objects.all().delete()

        # Cascade delete Business and Users clears almost everything in SaaS
        self.stdout.write("  Deleting business & users...")
        # Delete branches first (PROTECT constraint)
        Business.objects.filter(parent__isnull=False).delete()
        count_b, _ = Business.objects.all().delete()
        self.stdout.write(f"  Deleted {count_b} businesses (and related objects).")
        count_u, _ = User.objects.all().delete()
        self.stdout.write(f"  Deleted {count_u} users.")


    def get_or_create_user(self, email, role, business):
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_active': True,
            }
        )
        if created:
            user.set_password(DEFAULT_PASSWORD)
            name_part = email.split('@')[0].split('.')[0] if '.' in email.split('@')[0] else 'User'
            user.first_name = name_part.capitalize()
            user.save()
            self.stdout.write(f"  Created user {email}")
        
        Membership.objects.get_or_create(
            user=user,
            business=business,
            defaults={'role': role}
        )
        return user

    def seed_manzana(self):
        self.stdout.write(self.style.MIGRATE_HEADING("--- Seeding Tenant 1: Manzana (Gestión Comercial) ---"))
        
        # 1. Tenant & Plan
        business, _ = Business.objects.get_or_create(
            name="Manzana HQ",
            defaults={'default_service': 'gestion'}
        )
        Subscription.objects.update_or_create(
            business=business,
            defaults={
                'plan': BusinessPlan.PRO,
                'status': 'active',
                'max_branches': 3,
                'max_seats': 20,
                'renews_at': timezone.now() + datetime.timedelta(days=365)
            }
        )

        # 2. Users
        users = {
            'owner': self.get_or_create_user('manzana.owner@mirubro.local', 'owner', business),
            'manager': self.get_or_create_user('manzana.manager@mirubro.local', 'manager', business),
            'cashier': self.get_or_create_user('manzana.cashier@mirubro.local', 'cashier', business),
            'staff': self.get_or_create_user('manzana.staff@mirubro.local', 'staff', business),
            'viewer': self.get_or_create_user('manzana.viewer@mirubro.local', 'viewer', business),
        }
        owner = users['owner']

        # 3. Cash Registers & Sessions
        register, _ = CashRegister.objects.get_or_create(business=business, name="Caja Principal")
        sessions = []
        
        # 2 Closed sessions
        for i in range(2):
            s_date = timezone.now() - datetime.timedelta(days=2-i)
            s, _ = CashSession.objects.get_or_create(
                business=business,
                register=register,
                closed_at__date=s_date.date(),
                defaults={
                    'opened_by': owner,
                    'opened_by_name': 'Owner',
                    'closed_by': owner,
                    'opening_cash_amount': 10000,
                    'closing_cash_counted': 55000,
                    'expected_cash_total': 55000,
                    'status': CashSession.Status.CLOSED,
                    'opened_at': s_date,
                    'closed_at': s_date + datetime.timedelta(hours=8)
                }
            )
            sessions.append(s)

        # 1 Open session
        current_session, _ = CashSession.objects.get_or_create(
            business=business,
            register=register,
            status=CashSession.Status.OPEN,
            defaults={
                'opened_by': users['cashier'],
                'opened_by_name': 'Cashier',
                'opening_cash_amount': 15000,
                'opened_at': timezone.now(),
            }
        )
        sessions.append(current_session)

        # 4. Customers
        customers = []
        for i in range(15):
             c, _ = Customer.objects.update_or_create(
                 business=business,
                 email=f"cliente{i}@manzana.local",
                 defaults={
                     'name': f"Cliente {i}",
                     'type': Customer.CustomerType.INDIVIDUAL,
                     'doc_number': f"30{i:08d}",
                     'is_active': True
                 }
             )
             customers.append(c)

        # 5. Products & Stock (20 products)
        products = []
        for i in range(20):
            price = Decimal(random.randint(500, 5000))
            p, _ = Product.objects.update_or_create(
                business=business,
                sku=f"MZN-{100+i}",
                defaults={
                    'name': f"Producto Manzana {i+1}",
                    'price': price,
                    'cost': price * Decimal('0.6'),
                    'stock_min': 10,
                    'is_active': True
                }
            )
            
            # Stock init
            ProductStock.objects.update_or_create(
                business=business,
                product=p,
                defaults={'quantity': 100}
            )
            # Create a movement if none exists to show history
            if not StockMovement.objects.filter(business=business, product=p).exists():
                StockMovement.objects.create(
                    business=business,
                    product=p,
                    movement_type=StockMovement.MovementType.IN,
                    quantity=100,
                    reason="Stock Inicial",
                    created_by=owner
                )
            products.append(p)

        # 6. Sales (30 sales)
        # Distribute over last 14 days
        sales_count = 0
        for i in range(30):
            sale_date = timezone.now() - datetime.timedelta(days=random.randint(0, 14))
            sale_num = 1000 + i
            
            if Sale.objects.filter(business=business, number=sale_num).exists():
                continue

            # Pick customer sometimes
            cust = random.choice(customers) if random.random() > 0.3 else None
            
            sale = Sale.objects.create(
                business=business,
                number=sale_num,
                customer=cust,
                status=Sale.Status.COMPLETED,
                payment_method=random.choice(Sale.PaymentMethod.values),
                cash_session=current_session, # Assign to active for simplicity
                created_by=users['cashier'],
                created_at=sale_date
            )
            
            total = Decimal(0)
            # 1-5 items per sale
            for _ in range(random.randint(1, 5)):
                prod = random.choice(products)
                qty = Decimal(random.randint(1, 3))
                line_total = qty * prod.price
                
                SaleItem.objects.create(
                    sale=sale,
                    product=prod,
                    product_name_snapshot=prod.name,
                    quantity=qty,
                    unit_price=prod.price,
                    line_total=line_total
                )
                
                # Impact stock
                ProductStock.objects.filter(business=business, product=prod).update(
                    quantity=models.F('quantity') - qty
                )
                StockMovement.objects.create(
                    business=business,
                    product=prod,
                    movement_type=StockMovement.MovementType.OUT,
                    quantity=qty,
                    reason=f"Venta #{sale.number}",
                    created_by=users['cashier']
                )
                total += line_total
            
            sale.subtotal = total
            sale.total = total
            sale.save()
            sales_count += 1
            
        self.stdout.write(f"  Created {len(products)} products, {sales_count} sales, {len(customers)} customers.")

        # 7. Treasury
        self.stdout.write("  Seeding Treasury...")
        
        # Accounts
        acc_cash, _ = Account.objects.get_or_create(
            business=business, name="Caja Efectivo", defaults={'type': Account.Type.CASH, 'opening_balance': 50000}
        )
        acc_bank, _ = Account.objects.get_or_create(
            business=business, name="Banco Santander", defaults={'type': Account.Type.BANK, 'opening_balance': 100000}
        )
        acc_mp, _ = Account.objects.get_or_create(
            business=business, name="MercadoPago", defaults={'type': Account.Type.MERCADOPAGO, 'opening_balance': 2500}
        )

        # Settings
        TreasurySettings.objects.update_or_create(
            business=business,
            defaults={
                'default_cash_account': acc_cash,
                'default_bank_account': acc_bank,
                'default_mercadopago_account': acc_mp,
            }
        )

        # Categories
        cat_serv, _ = TransactionCategory.objects.get_or_create(
            business=business, name="Servicios", direction=TransactionCategory.Direction.EXPENSE
        )
        cat_payroll, _ = TransactionCategory.objects.get_or_create(
            business=business, name="Sueldos", direction=TransactionCategory.Direction.EXPENSE
        )
        cat_prov, _ = TransactionCategory.objects.get_or_create(
            business=business, name="Proveedores", direction=TransactionCategory.Direction.EXPENSE
        )
        cat_other, _ = TransactionCategory.objects.get_or_create(
            business=business, name="Otros", direction=TransactionCategory.Direction.EXPENSE
        )
        
        # Templates
        ExpenseTemplate.objects.get_or_create(
            business=business, name="Internet Fibra", 
            defaults={'category': cat_serv, 'amount': 15000, 'frequency': ExpenseTemplate.Frequency.MONTHLY, 'due_day': 10, 'start_date': timezone.now().date()}
        )
        ExpenseTemplate.objects.get_or_create(
            business=business, name="Luz", 
            defaults={'category': cat_serv, 'amount': 45000, 'frequency': ExpenseTemplate.Frequency.MONTHLY, 'due_day': 15, 'start_date': timezone.now().date()}
        )
        
        # Employees
        emp1, _ = Employee.objects.get_or_create(
            business=business, full_name="Juan Perez",
            defaults={'base_salary': 350000, 'pay_frequency': Employee.PayFrequency.MONTHLY}
        )
        
        # Payroll Payment (1 month ago)
        pay_date = timezone.now() - datetime.timedelta(days=30)
        
        if not PayrollPayment.objects.filter(business=business, employee=emp1, paid_at=pay_date).exists():
            trx_pay = Transaction.objects.create(
                business=business, account=acc_bank, direction=Transaction.Direction.OUT, amount=350000,
                occurred_at=pay_date, category=cat_payroll, description=f"Sueldo {emp1.full_name}",
                reference_type='payroll', created_by=owner
            )
            PayrollPayment.objects.create(
                business=business, employee=emp1, amount=350000, paid_at=pay_date,
                account=acc_bank, transaction=trx_pay
            )
            
        # Expenses
        # 1 Paid
        exp_paid, _ = Expense.objects.get_or_create(
            business=business, name="Compra Insumos Libreria",
            defaults={
                'category': cat_other, 'amount': 5000, 'due_date': timezone.now() - datetime.timedelta(days=5),
                'status': Expense.Status.PAID, 'paid_at': timezone.now() - datetime.timedelta(days=5),
                'paid_account': acc_cash
            }
        )
        if exp_paid.status == Expense.Status.PAID and not exp_paid.payment_transaction:
            trx_exp = Transaction.objects.create(
                business=business, account=acc_cash, direction=Transaction.Direction.OUT, amount=5000,
                occurred_at=exp_paid.paid_at, category=cat_other, description=f"Pago gasto: {exp_paid.name}",
                reference_type='expense', reference_id=str(exp_paid.id), created_by=owner
            )
            exp_paid.payment_transaction = trx_exp
            exp_paid.save()
            
        # 1 Pending
        Expense.objects.get_or_create(
            business=business, name="Mantenimiento Aire Acondicionado",
            defaults={
                'category': cat_serv, 'amount': 25000, 'due_date': timezone.now() + datetime.timedelta(days=2),
                'status': Expense.Status.PENDING
            }
        )

        # BRANCHES SEED
        self.stdout.write("  Seeding branches for Manzana HQ...")
        branches_data = [
            {'name': 'Manzana Centro', 'suffix': 'centro'},
            {'name': 'Manzana Norte', 'suffix': 'norte'},
        ]
        
        for b_data in branches_data:
            branch_name = b_data['name']
            
            branch, _ = Business.objects.get_or_create(
                parent=business, # HQ
                name=branch_name,
                defaults={
                 'default_service': 'gestion', 
                 'status': 'active'
                }
            )
            Subscription.objects.update_or_create(
                business=branch,
                defaults={'plan': BusinessPlan.STARTER, 'status': 'active'}
            )
            
            # Users
            self.get_or_create_user(f"manzana.{b_data['suffix']}.manager@mirubro.local", 'manager', branch)
            self.get_or_create_user(f"manzana.{b_data['suffix']}.cashier@mirubro.local", 'cashier', branch)
            
            # Owner access
            Membership.objects.get_or_create(user=users['owner'], business=branch, defaults={'role': 'owner'})
            
            # Minimal products for aggregation test (Copy first 5)
            for p in products[:5]:
                 bp, _ = Product.objects.get_or_create(
                     business=branch, sku=p.sku, 
                     defaults={'name': p.name, 'price': p.price, 'stock_min': 5, 'is_active': True}
                 )
                 ProductStock.objects.update_or_create(business=branch, product=bp, defaults={'quantity': 50})
        
        self.stdout.write("  Branches seeded.")

    def seed_lapizza(self):
        self.stdout.write(self.style.MIGRATE_HEADING("--- Seeding Tenant 2: La Pizza (Restaurante) ---"))
        
        # 1. Tenant
        business, _ = Business.objects.get_or_create(
            name="La Pizza",
            defaults={'default_service': 'restaurante'}
        )
        Subscription.objects.update_or_create(
            business=business,
            defaults={
                'plan': BusinessPlan.PLUS,
                'status': 'active',
                'max_seats': 50,
                'renews_at': timezone.now() + datetime.timedelta(days=365)
            }
        )

        # 2. Users
        users = {
            'owner': self.get_or_create_user('lapizza.owner@mirubro.local', 'owner', business),
            'manager': self.get_or_create_user('lapizza.manager@mirubro.local', 'manager', business),
            'cashier': self.get_or_create_user('lapizza.cashier@mirubro.local', 'cashier', business),
            'kitchen': self.get_or_create_user('lapizza.kitchen@mirubro.local', 'kitchen', business),
            'salon': self.get_or_create_user('lapizza.salon@mirubro.local', 'salon', business),
            'viewer': self.get_or_create_user('lapizza.viewer@mirubro.local', 'viewer', business),
        }
        owner = users['owner']

        # 3. Menu (6 categories, 30 items)
        categories = ["Pizzas", "Empanadas", "Bebidas", "Postres", "Promos", "Extras"]
        menu_items = []
        for idx, cat_name in enumerate(categories):
            cat, _ = MenuCategory.objects.get_or_create(
                business=business,
                name=cat_name,
                defaults={'position': idx}
            )
            for j in range(5):
                item_name = f"{cat_name} {j+1}"
                item, _ = MenuItem.objects.get_or_create(
                    business=business,
                    name=item_name,
                    category=cat,
                    defaults={
                        'price': Decimal(random.randint(1000, 15000)),
                        'is_available': True,
                        'position': j,
                        'sku': f"PZ-{idx}-{j}"
                    }
                )
                menu_items.append(item)
                # Ensure product existence for catalog consistency (optional but good)
                Product.objects.get_or_create(
                    business=business,
                    sku=item.sku,
                    defaults={'name': item.name, 'price': item.price}
                )

        # 4. Tables (12 tables)
        TableLayout.objects.get_or_create(business=business)
        tables = []
        for i in range(12):
            t, _ = Table.objects.get_or_create(
                business=business,
                code=f"M{i+1}",
                defaults={
                    'name': f"Mesa {i+1}",
                    'capacity': 4,
                }
            )
            tables.append(t)

        # 5. Orders (20 total: 10 paid, 10 open)
        orders_count = 0
        
        # 10 Paid
        for i in range(10):
            if Order.objects.filter(business=business, number=100+i).exists(): continue
            
            order = Order.objects.create(
                business=business,
                number=100+i,
                status=Order.Status.PAID,
                channel=Order.Channel.DINE_IN,
                table=random.choice(tables),
                created_by=users['salon'],
                opened_at=timezone.now() - datetime.timedelta(hours=random.randint(1, 24)),
                closed_at=timezone.now()
            )
            self._add_order_items(order, menu_items, OrderItem.KitchenStatus.DONE)
            orders_count += 1

        # 10 Open
        for i in range(10):
            if Order.objects.filter(business=business, number=200+i).exists(): continue
            
            order = Order.objects.create(
                business=business,
                number=200+i,
                status=Order.Status.OPEN,
                channel=Order.Channel.DINE_IN,
                table=random.choice(tables),
                created_by=users['salon'],
                opened_at=timezone.now() - datetime.timedelta(minutes=random.randint(5, 60))
            )
            # Random kitchen status
            k_status = random.choice([OrderItem.KitchenStatus.PENDING, OrderItem.KitchenStatus.IN_PROGRESS])
            self._add_order_items(order, menu_items, k_status)
            orders_count += 1

        self.stdout.write(f"  Created {len(menu_items)} menu items, {orders_count} orders, {len(tables)} tables.")

    def _add_order_items(self, order, menu_items, kitchen_status):
        total = Decimal(0)
        for _ in range(random.randint(1, 4)):
            item = random.choice(menu_items)
            qty = Decimal(random.randint(1, 2))
            line_total = qty * item.price
            
            OrderItem.objects.create(
                order=order,
                name=item.name,
                quantity=qty,
                unit_price=item.price,
                total_price=line_total,
                kitchen_status=kitchen_status
            )
            total += line_total
        
        order.total_amount = total
        order.save()

    def print_summary(self):
        self.stdout.write("\n" + "="*50)
        self.stdout.write("SEED DEMO COMPLETE")
        self.stdout.write("="*50)
        self.stdout.write("Tenant 1: Manzana HQ (Gestión Comercial - Pro + Sucursales)")
        self.stdout.write("  Users: manzana.{owner|manager|cashier|staff|viewer}@mirubro.local")
        self.stdout.write("  Branches: Manzana Centro, Manzana Norte (with local managers/cashiers)")
        self.stdout.write("  Pass:  mirubro123")
        self.stdout.write("-" * 30)
        self.stdout.write("Tenant 2: La Pizza (Restaurantes - Plus)")
        self.stdout.write("  Users: lapizza.{owner|manager|cashier|kitchen|salon|viewer}@mirubro.local")
        self.stdout.write("  Pass:  mirubro123")
        self.stdout.write("-" * 30)
        self.stdout.write("Tenant 3: Demo QR (Menú QR Online)")
        self.stdout.write("  Users: menuqr.owner@mirubro.local")
        self.stdout.write("  Pass:  mirubro123")
        self.stdout.write("="*50 + "\n")

    def seed_menu_qr(self):
        self.stdout.write(self.style.MIGRATE_HEADING("--- Seeding Tenant 3: Demo QR (Menú QR Online) ---"))

        business, _ = Business.objects.get_or_create(
            name="Demo QR",
            defaults={'default_service': 'menu_qr'}
        )
        Subscription.objects.update_or_create(
            business=business,
            defaults={
                'plan': BusinessPlan.MENU_QR,
                'status': 'active',
                'service': 'menu_qr',
            }
        )

        owner = self.get_or_create_user('menuqr.owner@mirubro.local', 'owner', business)

        categories_payload = [
            ('Bebidas de Autor', [
                ('Limonada con menta y maracuyá', 3200, True),
                ('Té frío de frutos rojos', 2800, True),
            ]),
            ('Tapas', [
                ('Bruschettas mediterráneas', 5400, True),
                ('Tartar de remolacha y cítricos', 6100, True),
                ('Croquetas de hongos ahumados', 6900, False),
            ]),
            ('Platos Principales', [
                ('Risotto de calabaza asada', 9800, True),
                ('Pesca blanca con manteca de hierbas', 11800, True),
                ('Gnocchi de ricota y pistachos', 10500, True),
            ]),
        ]

        MenuItem.objects.filter(business=business).delete()
        MenuCategory.objects.filter(business=business).delete()

        for position, (category_name, items) in enumerate(categories_payload, start=1):
            category = MenuCategory.objects.create(
                business=business,
                name=category_name,
                position=position,
                is_active=True,
            )
            for idx, (item_name, price, available) in enumerate(items, start=1):
                MenuItem.objects.create(
                    business=business,
                    category=category,
                    name=item_name,
                    price=price,
                    position=idx,
                    is_available=available,
                )

        branding = ensure_menu_branding(business)
        branding.display_name = "Demo QR"
        branding.palette_primary = '#F97316'
        branding.palette_secondary = '#FFE0B2'
        branding.palette_background = '#0F172A'
        branding.palette_text = '#F8FAFC'
        branding.font_heading = 'playfair_display'
        branding.font_body = 'inter'
        branding.font_scale_heading = 1.35
        branding.font_scale_body = 1.00
        branding.save()

        config = ensure_public_menu_config(business)
        config.enabled = True
        config.brand_name = branding.display_name
        config.save(update_fields=['enabled', 'brand_name'])

        self.stdout.write("  Demo QR menu and branding ready.")

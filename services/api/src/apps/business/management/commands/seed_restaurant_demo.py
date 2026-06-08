"""
Management command para crear una cuenta demo de Restaurante Inteligente en entorno local.

Crea un usuario demo completo con negocio, suscripción, configuración operativa,
productos, carta online, reseñas, empleados POS y sesión de caja abierta.

Es idempotente: puede ejecutarse múltiples veces sin duplicar datos.

Uso:
    python manage.py seed_restaurant_demo
    python manage.py seed_restaurant_demo --reset
    python manage.py seed_restaurant_demo --email demo@mi.local --password MiDemo123!
    python manage.py seed_restaurant_demo --force   # salta verificación de entorno
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AccountProfile, EmployeeProfile, Membership
from apps.business.models import (
    Business,
    CommercialSettings,
    Subscription,
)
from apps.cash.models import CashRegister, CashSession
from apps.catalog.models import Product, ProductCategory
from apps.inventory.models import ProductStock
from apps.menu.models import MenuCategory, MenuItem, PublicMenuConfig
from apps.resto.models import RestaurantOperationSettings
from apps.reviews.models import ReviewConfig

User = get_user_model()

# ── Configuración del demo ────────────────────────────────────────────────────

DEMO_EMAIL = 'demo.restaurante@mirubro.local'
DEMO_PASSWORD = 'DemoM1Rubro!2026'
DEMO_BUSINESS_NAME = 'Demo Fast Food'
DEMO_SLUG = 'demo-fast-food'
DEMO_PLAN = 'plus'

DEMO_CATEGORIES = [
    {'name': 'Hamburguesas', 'pos': 1},
    {'name': 'Papas y acompañamientos', 'pos': 2},
    {'name': 'Bebidas', 'pos': 3},
]

DEMO_PRODUCTS = [
    {
        'name': 'Hamburguesa Clásica',
        'sku': 'DEMO-HAMB-CLASICA',
        'price': Decimal('6500.00'),
        'cost': Decimal('2500.00'),
        'category': 'Hamburguesas',
        'stock_qty': 50,
    },
    {
        'name': 'Hamburguesa Doble',
        'sku': 'DEMO-HAMB-DOBLE',
        'price': Decimal('8500.00'),
        'cost': Decimal('3500.00'),
        'category': 'Hamburguesas',
        'stock_qty': 50,
    },
    {
        'name': 'Papas Fritas',
        'sku': 'DEMO-PAPAS',
        'price': Decimal('3500.00'),
        'cost': Decimal('1000.00'),
        'category': 'Papas y acompañamientos',
        'stock_qty': 80,
    },
    {
        'name': 'Gaseosa',
        'sku': 'DEMO-GASEOSA',
        'price': Decimal('2500.00'),
        'cost': Decimal('800.00'),
        'category': 'Bebidas',
        'stock_qty': 100,
    },
    {
        'name': 'Agua',
        'sku': 'DEMO-AGUA',
        'price': Decimal('1800.00'),
        'cost': Decimal('500.00'),
        'category': 'Bebidas',
        'stock_qty': 100,
    },
]

# MenuCategory name → ProductCategory name mapping
DEMO_MENU_CATEGORIES = [
    {'name': 'Hamburguesas', 'product_category': 'Hamburguesas', 'pos': 1},
    {'name': 'Acompañamientos', 'product_category': 'Papas y acompañamientos', 'pos': 2},
    {'name': 'Bebidas', 'product_category': 'Bebidas', 'pos': 3},
]

DEMO_EMPLOYEES = [
    {
        'first_name': 'Cajero',
        'last_name': 'Demo',
        'alias': 'Cajero Demo',
        'employee_code': 'EMP-CAJA-01',
        'role_type': EmployeeProfile.RoleType.CASHIER,
        'pin': '1234',
    },
    {
        'first_name': 'Cocina',
        'last_name': 'Demo',
        'alias': 'Cocina Demo',
        'employee_code': 'EMP-COCINA-01',
        'role_type': EmployeeProfile.RoleType.KITCHEN,
        'pin': '2222',
    },
]


class Command(BaseCommand):
    help = 'Crea cuenta demo de Restaurante Inteligente para revisión local'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            default=False,
            help='Elimina y recrea la sesión de caja y reinicia el progreso del demo.',
        )
        parser.add_argument(
            '--email',
            default=DEMO_EMAIL,
            help=f'Email del usuario demo (default: {DEMO_EMAIL})',
        )
        parser.add_argument(
            '--password',
            default=DEMO_PASSWORD,
            help=f'Contraseña del usuario demo (default: {DEMO_PASSWORD})',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            default=False,
            help='Fuerza la ejecución incluso si DEBUG=False (NO usar en producción).',
        )

    def handle(self, *args, **options):
        self._check_environment(options['force'])

        email = options['email']
        password = options['password']
        do_reset = options['reset']

        self.stdout.write(
            self.style.MIGRATE_HEADING('\n═══ seed_restaurant_demo ═══\n')
        )

        with transaction.atomic():
            result = self._seed(email, password, do_reset)

        self._print_summary(result)

    # ── Verificación de entorno ───────────────────────────────────────────────

    def _check_environment(self, force: bool):
        if not getattr(settings, 'DEBUG', False) and not force:
            raise CommandError(
                'Este comando está pensado solo para entornos de desarrollo '
                '(DEBUG=True). Si realmente querés ejecutarlo, usá --force.'
            )

    # ── Seed principal ────────────────────────────────────────────────────────

    def _seed(self, email: str, password: str, do_reset: bool) -> dict:
        # 1. Usuario
        user, user_created = User.objects.update_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': 'Demo',
                'last_name': 'Restaurante',
                'is_active': True,
            },
        )
        user.set_password(password)
        user.save(update_fields=['password'])
        self._log('Usuario', email, user_created)

        # Perfil: verificar email y activar cuenta
        profile, _ = AccountProfile.objects.get_or_create(user=user)
        profile.email_verified = True
        profile.account_status = AccountProfile.AccountStatus.ACTIVE
        profile.save(update_fields=['email_verified', 'account_status', 'updated_at'])

        # 2. Business
        business, biz_created = Business.objects.get_or_create(
            slug=DEMO_SLUG,
            defaults={
                'name': DEMO_BUSINESS_NAME,
                'service_type': Business.ServiceType.RESTAURANTE,
                'default_service': 'restaurante',
                'country': 'AR',
                'currency': 'ARS',
                'timezone': 'America/Argentina/Buenos_Aires',
                'status': 'active',
            },
        )
        if not biz_created:
            # Asegurar que los campos clave estén actualizados
            Business.objects.filter(pk=business.pk).update(
                name=DEMO_BUSINESS_NAME,
                default_service='restaurante',
                status='active',
            )
        self._log('Business', DEMO_BUSINESS_NAME, biz_created)

        # 3. Suscripción (legacy) — plan 'plus' habilita Restaurante Inteligente
        subscription, sub_created = Subscription.objects.get_or_create(
            business=business,
            defaults={
                'plan': DEMO_PLAN,
                'service': 'restaurante',
                'status': 'active',
                'max_branches': 1,
                'max_seats': 5,
            },
        )
        if not sub_created and subscription.plan != DEMO_PLAN:
            subscription.plan = DEMO_PLAN
            subscription.service = 'restaurante'
            subscription.status = 'active'
            subscription.save(update_fields=['plan', 'service', 'status', 'updated_at'])
        self._log('Subscription', f'plan={DEMO_PLAN}', sub_created)

        # 4. Membership (owner)
        membership, mem_created = Membership.objects.get_or_create(
            user=user,
            business=business,
            defaults={'role': 'owner'},
        )
        self._log('Membership', 'owner', mem_created)

        # 5. CommercialSettings
        cs = CommercialSettings.objects.for_business(business)
        cs.block_sales_if_no_open_cash_session = False
        cs.require_customer_for_sales = False
        cs.allow_sell_without_stock = True
        cs.save(update_fields=[
            'block_sales_if_no_open_cash_session',
            'require_customer_for_sales',
            'allow_sell_without_stock',
            'updated_at',
        ])
        self._log('CommercialSettings', 'block_sales=False, require_customer=False', False)

        # 6. RestaurantOperationSettings
        op_settings, op_created = RestaurantOperationSettings.objects.update_or_create(
            business=business,
            defaults={
                'tables_enabled': False,
                'kitchen_enabled': True,
                'counter_orders_enabled': True,
                'pos_quick_sale_enabled': True,
                'allow_pickup_orders': True,
                'allow_dine_in_orders': False,
                'allow_delivery_orders': False,
                'default_pos_mode': RestaurantOperationSettings.DefaultPosMode.QUICK_SALE,
            },
        )
        self._log('RestaurantOperationSettings', 'tables=False, kitchen=True', op_created)

        # 7. Categorías y productos
        category_map = self._seed_categories(business)
        product_map = self._seed_products(business, category_map)

        # 8. Stock
        self._seed_stock(business, product_map)

        # 9. Carta Online
        self._seed_public_menu(business, category_map, product_map)

        # 10. QR de Reseñas
        self._seed_reviews(business)

        # 11. Empleados POS
        self._seed_employees(business)

        # 12. Caja y sesión
        cash_register = self._seed_cash_register(business)
        self._seed_cash_session(business, cash_register, user, do_reset)

        return {
            'email': email,
            'password': password,
            'business_name': DEMO_BUSINESS_NAME,
            'slug': DEMO_SLUG,
            'employees': DEMO_EMPLOYEES,
        }

    # ── Categorías ────────────────────────────────────────────────────────────

    def _seed_categories(self, business) -> dict:
        cat_map = {}
        for cat_def in DEMO_CATEGORIES:
            cat, created = ProductCategory.objects.get_or_create(
                business=business,
                name=cat_def['name'],
                defaults={'is_active': True},
            )
            cat_map[cat_def['name']] = cat
            self._log('ProductCategory', cat_def['name'], created)
        return cat_map

    # ── Productos ─────────────────────────────────────────────────────────────

    def _seed_products(self, business, category_map: dict) -> dict:
        product_map = {}
        for prod_def in DEMO_PRODUCTS:
            category = category_map.get(prod_def['category'])
            prod, created = Product.objects.update_or_create(
                business=business,
                sku=prod_def['sku'],
                defaults={
                    'name': prod_def['name'],
                    'price': prod_def['price'],
                    'cost': prod_def['cost'],
                    'category': category,
                    'is_active': True,
                },
            )
            product_map[prod_def['sku']] = prod
            self._log('Product', prod_def['name'], created)
        return product_map

    # ── Stock ─────────────────────────────────────────────────────────────────

    def _seed_stock(self, business, product_map: dict):
        stock_qty_map = {p['sku']: p['stock_qty'] for p in DEMO_PRODUCTS}
        for sku, product in product_map.items():
            qty = stock_qty_map.get(sku, 0)
            stock, created = ProductStock.objects.get_or_create(
                business=business,
                product=product,
                defaults={'quantity': Decimal(str(qty))},
            )
            if not created and stock.quantity != Decimal(str(qty)):
                stock.quantity = Decimal(str(qty))
                stock.save(update_fields=['quantity', 'updated_at'])
            self._log('ProductStock', f'{product.name} → {qty}', created)

    # ── Carta Online ──────────────────────────────────────────────────────────

    def _seed_public_menu(self, business, category_map: dict, product_map: dict):
        # Config principal
        menu_config, mc_created = PublicMenuConfig.objects.get_or_create(
            business=business,
            defaults={
                'slug': DEMO_SLUG,
                'brand_name': DEMO_BUSINESS_NAME,
                'enabled': True,
            },
        )
        if not mc_created:
            # Asegurar enabled y slug
            updated = False
            if not menu_config.enabled:
                menu_config.enabled = True
                updated = True
            if menu_config.slug != DEMO_SLUG:
                menu_config.slug = DEMO_SLUG
                updated = True
            if updated:
                menu_config.save(update_fields=['enabled', 'slug', 'updated_at'])
        self._log('PublicMenuConfig', f'slug={DEMO_SLUG}', mc_created)

        # MenuCategories
        menu_cat_map = {}
        for mc_def in DEMO_MENU_CATEGORIES:
            product_cat = category_map.get(mc_def['product_category'])
            menu_cat, mcat_created = MenuCategory.objects.get_or_create(
                business=business,
                name=mc_def['name'],
                defaults={
                    'product_category': product_cat,
                    'position': mc_def['pos'],
                    'is_active': True,
                },
            )
            menu_cat_map[mc_def['name']] = menu_cat
            self._log('MenuCategory', mc_def['name'], mcat_created)

        # MenuItems — vincular a Product
        # Mapeo ProductCategory.name → MenuCategory
        prod_cat_to_menu_cat = {}
        for mc_def in DEMO_MENU_CATEGORIES:
            menu_cat = menu_cat_map.get(mc_def['name'])
            prod_cat_to_menu_cat[mc_def['product_category']] = menu_cat

        for prod_def in DEMO_PRODUCTS:
            product = product_map.get(prod_def['sku'])
            if not product:
                continue
            menu_cat = prod_cat_to_menu_cat.get(prod_def['category'])
            item, item_created = MenuItem.objects.get_or_create(
                business=business,
                product=product,
                defaults={
                    'name': prod_def['name'],
                    'price': prod_def['price'],
                    'category': menu_cat,
                    'is_available': True,
                    'sku': prod_def['sku'],
                },
            )
            self._log('MenuItem', prod_def['name'], item_created)

    # ── QR de Reseñas ─────────────────────────────────────────────────────────

    def _seed_reviews(self, business):
        review_config, rc_created = ReviewConfig.objects.get_or_create(
            business=business,
            defaults={
                'enabled': True,
                'google_place_id': '',
                'google_review_url': '',
                'public_display_name': DEMO_BUSINESS_NAME,
                'public_subtitle': 'Hamburguesas y más',
                'public_question': '¿Cómo fue tu experiencia?',
                'thank_you_message': '¡Gracias por tu opinión!',
                'mode': 'direct',
                'redirect_threshold': 4,
                'collect_contact': False,
            },
        )
        if not rc_created and not review_config.enabled:
            review_config.enabled = True
            review_config.save(update_fields=['enabled', 'updated_at'])
        self._log('ReviewConfig', f'enabled={review_config.enabled}', rc_created)

    # ── Empleados POS ─────────────────────────────────────────────────────────

    def _seed_employees(self, business):
        for emp_def in DEMO_EMPLOYEES:
            pin_hash = make_password(emp_def['pin'])
            emp, emp_created = EmployeeProfile.objects.get_or_create(
                business=business,
                employee_code=emp_def['employee_code'],
                defaults={
                    'first_name': emp_def['first_name'],
                    'last_name': emp_def['last_name'],
                    'alias': emp_def['alias'],
                    'role_type': emp_def['role_type'],
                    'credential_type': EmployeeProfile.CredentialType.PIN,
                    'login_code_hash': pin_hash,
                    'status': EmployeeProfile.Status.ACTIVE,
                },
            )
            if not emp_created:
                # Actualizar PIN y estado por si acaso
                emp.login_code_hash = pin_hash
                emp.status = EmployeeProfile.Status.ACTIVE
                emp.save(update_fields=['login_code_hash', 'status', 'updated_at'])
            self._log(
                'EmployeeProfile',
                f'{emp_def["alias"]} (PIN: {emp_def["pin"]})',
                emp_created,
            )

    # ── Caja ──────────────────────────────────────────────────────────────────

    def _seed_cash_register(self, business) -> CashRegister:
        register, created = CashRegister.objects.get_or_create(
            business=business,
            name='Caja Demo',
            defaults={'is_active': True},
        )
        self._log('CashRegister', 'Caja Demo', created)
        return register

    def _seed_cash_session(self, business, register, user, do_reset: bool):
        # Si --reset, cerrar sesión abierta existente
        if do_reset:
            CashSession.objects.filter(
                business=business,
                register=register,
                status=CashSession.Status.OPEN,
            ).update(
                status=CashSession.Status.CLOSED,
                closed_at=timezone.now(),
                closing_note='Cerrada por seed_restaurant_demo --reset',
            )

        # Crear sesión abierta si no existe
        open_session = CashSession.objects.filter(
            business=business,
            register=register,
            status=CashSession.Status.OPEN,
        ).first()

        if not open_session:
            CashSession.objects.create(
                business=business,
                register=register,
                opened_by=user,
                opened_by_name='Demo Restaurante',
                opening_cash_amount=Decimal('5000.00'),
                status=CashSession.Status.OPEN,
            )
            self._log('CashSession', 'abierta ($ 5.000 iniciales)', True)
        else:
            self._log('CashSession', 'ya existe sesión abierta', False)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, model: str, label: str, created: bool):
        action = self.style.SUCCESS('creado') if created else 'ya existe'
        self.stdout.write(f'  {model:<28} {label:<40} [{action}]')

    # ── Resumen final ─────────────────────────────────────────────────────────

    def _print_summary(self, result: dict):
        sep = '─' * 60
        self.stdout.write('\n')
        self.stdout.write(self.style.MIGRATE_HEADING('═══ DEMO RESTAURANTE INTELIGENTE ═══\n'))

        self.stdout.write(self.style.SUCCESS('Backoffice:'))
        self.stdout.write(f'  Email    : {result["email"]}')
        self.stdout.write(f'  Password : {result["password"]}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('POS — Empleados:'))
        for emp in result['employees']:
            self.stdout.write(f'  {emp["alias"]:<20} PIN: {emp["pin"]}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('URLs:'))
        self.stdout.write('  Backoffice : http://localhost:3000/app')
        self.stdout.write('  POS        : http://localhost:3000/pos/login')
        self.stdout.write(f'  Carta      : http://localhost:3000/m/{result["slug"]}')
        self.stdout.write(f'  Reseñas    : http://localhost:3000/r/{result["slug"]}')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Configuración operativa:'))
        self.stdout.write('  tables_enabled   : False  → Mesas ocultas en UI')
        self.stdout.write('  kitchen_enabled  : True   → Cocina/KDS visible')
        self.stdout.write('  default_pos_mode : quick_sale')
        self.stdout.write('  Sesión de caja   : abierta (sin bloqueo de ventas)')

        self.stdout.write('\n' + sep)
        self.stdout.write(
            self.style.SUCCESS(
                '✅ Seed completado. '
                'Iniciá el stack con docker compose y visitá http://localhost:3000/app\n'
            )
        )

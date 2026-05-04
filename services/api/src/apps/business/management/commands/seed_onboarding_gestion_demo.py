"""
Management command para crear escenarios de QA del onboarding de Gestión Comercial.

Crea 4 usuarios demo con sus respectivos negocios, suscripciones y datos de prueba.
Es idempotente: puede ejecutarse múltiples veces sin duplicar datos.

Escenarios:
  A — starter / sin productos / sin progreso  (pantalla inicial del wizard)
  B — starter / 1 producto / sin ventas       (wizard muestra first_product completado)
  C — starter / 1 producto / 1 venta          (wizard en sales_setup)
  D — pro / 1 producto / block_sales=True     (sales_setup emite warning)

Uso:
    python manage.py seed_onboarding_gestion_demo
    python manage.py seed_onboarding_gestion_demo --reset-progress
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Membership
from apps.business.models import (
    Business,
    BusinessOnboardingProgress,
    CommercialSettings,
    Subscription,
)
from apps.catalog.models import Product, ProductCategory
from apps.sales.models import Sale

User = get_user_model()

# ── Escenarios ────────────────────────────────────────────────────────────────

SCENARIOS = [
    {
        'label': 'A',
        'email': 'onboarding.start.clean@demo.local',
        'password': 'Demo12345!',
        'business_name': 'Onboarding START Clean',
        'plan': 'starter',
        'with_product': False,
        'with_sale': False,
        'block_sales': False,
        'description': 'starter / sin productos / pantalla inicial del wizard',
    },
    {
        'label': 'B',
        'email': 'onboarding.start.product@demo.local',
        'password': 'Demo12345!',
        'business_name': 'Onboarding START Product',
        'plan': 'starter',
        'with_product': True,
        'with_sale': False,
        'block_sales': False,
        'description': 'starter / 1 producto / wizard muestra first_product completado',
    },
    {
        'label': 'C',
        'email': 'onboarding.start.sold@demo.local',
        'password': 'Demo12345!',
        'business_name': 'Onboarding START Sold',
        'plan': 'starter',
        'with_product': True,
        'with_sale': True,
        'block_sales': False,
        'description': 'starter / 1 producto / 1 venta / wizard en sales_setup',
    },
    {
        'label': 'D',
        'email': 'onboarding.pro.warning@demo.local',
        'password': 'Demo12345!',
        'business_name': 'Onboarding PRO Warning',
        'plan': 'pro',
        'with_product': True,
        'with_sale': False,
        'block_sales': True,
        'description': 'pro / 1 producto / block_sales=True / warning en sales_setup',
    },
]


class Command(BaseCommand):
    help = 'Crea escenarios de QA para el onboarding de Gestión Comercial'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-progress',
            action='store_true',
            default=False,
            help='Resetea BusinessOnboardingProgress aunque ya exista (por defecto: siempre resetea)',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.MIGRATE_HEADING('\n═══ seed_onboarding_gestion_demo ═══\n')
        )

        results = []

        for scenario in SCENARIOS:
            with transaction.atomic():
                row = self._seed_scenario(scenario)
                results.append(row)

        self._print_table(results)

    # ── Seed de un escenario ──────────────────────────────────────────────────

    def _seed_scenario(self, sc):
        label = sc['label']
        self.stdout.write(f'  → Escenario {label}: {sc["description"]}')

        # 1. Usuario
        user, user_created = User.objects.update_or_create(
            email=sc['email'],
            defaults={
                'username': sc['email'],
                'is_active': True,
            },
        )
        user.set_password(sc['password'])
        user.save(update_fields=['password'])

        # 2. Business
        business, biz_created = Business.objects.get_or_create(
            name=sc['business_name'],
            defaults={
                'service_type': Business.ServiceType.GESTION,
                'default_service': 'gestion',
                'country': 'AR',
                'currency': 'ARS',
                'timezone': 'America/Argentina/Buenos_Aires',
                'status': 'active',
            },
        )

        # 3. Subscription
        subscription, _ = Subscription.objects.get_or_create(
            business=business,
            defaults={
                'plan': sc['plan'],
                'service': 'gestion',
                'status': 'active',
                'max_branches': 1,
                'max_seats': 2,
            },
        )
        # Si ya existía, actualizar plan
        if subscription.plan != sc['plan']:
            subscription.plan = sc['plan']
            subscription.save(update_fields=['plan'])

        # 4. Membership (owner)
        Membership.objects.get_or_create(
            user=user,
            business=business,
            defaults={'role': 'owner'},
        )

        # 5. CommercialSettings
        cs = CommercialSettings.objects.for_business(business)
        cs.block_sales_if_no_open_cash_session = sc['block_sales']
        cs.save(update_fields=['block_sales_if_no_open_cash_session', 'updated_at'])

        # 6. Catálogo (product + category) si aplica
        if sc['with_product']:
            category, _ = ProductCategory.objects.get_or_create(
                business=business,
                name='Demo',
            )
            Product.objects.get_or_create(
                business=business,
                name='Producto Demo',
                defaults={
                    'category': category,
                    'price': Decimal('100.00'),
                    'cost': Decimal('50.00'),
                    'is_active': True,
                },
            )

        # 7. Venta si aplica
        if sc['with_sale']:
            existing_sale = Sale.objects.filter(business=business).first()
            if not existing_sale:
                from django.db.models import Max
                max_number = Sale.objects.filter(business=business).aggregate(
                    max_number=Max('number')
                )['max_number'] or 0
                Sale.objects.create(
                    business=business,
                    number=max_number + 1,
                    status='completed',
                    payment_method='cash',
                    subtotal=Decimal('500.00'),
                    discount=Decimal('0.00'),
                    total=Decimal('500.00'),
                )

        # 8. Reset BusinessOnboardingProgress (siempre: QA necesita estado limpio)
        BusinessOnboardingProgress.objects.filter(
            business=business,
            product_type='gestion',
            version='v1',
        ).delete()
        BusinessOnboardingProgress.objects.create(
            business=business,
            product_type='gestion',
            version='v1',
            current_step='',
            skipped_steps=[],
            completed_at=None,
            dismissed_at=None,
        )

        action = 'creado' if biz_created else 'actualizado'
        self.stdout.write(
            self.style.SUCCESS(f'    ✓ Business "{sc["business_name"]}" {action}')
        )

        return {
            'label': label,
            'email': sc['email'],
            'password': sc['password'],
            'plan': sc['plan'],
            'business': sc['business_name'],
            'description': sc['description'],
        }

    # ── Tabla de credenciales ─────────────────────────────────────────────────

    def _print_table(self, results):
        self.stdout.write('\n')
        self.stdout.write(
            self.style.MIGRATE_HEADING('═══ CREDENCIALES DE DEMO ═══\n')
        )
        self.stdout.write(
            f'  {"Esc":<4} {"Email":<42} {"Password":<14} {"Plan":<10} {"Descripción"}'
        )
        self.stdout.write('  ' + '─' * 100)
        for r in results:
            self.stdout.write(
                f'  {r["label"]:<4} {r["email"]:<42} {r["password"]:<14} '
                f'{r["plan"]:<10} {r["description"]}'
            )
        self.stdout.write('\n')
        self.stdout.write(
            self.style.SUCCESS(
                '✅ Seed completado. '
                'Activa el flag ROLLOUT_NEW_ONBOARDING=true en services/api/.env '
                'para habilitar el onboarding en el backend.\n'
            )
        )

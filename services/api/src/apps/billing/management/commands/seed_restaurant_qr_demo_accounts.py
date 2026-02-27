"""
Management command to seed demo accounts for Restaurante Inteligente and Menú QR Online testing.

Creates 2 demo users, businesses and subscriptions:
  - restaurant.demo@demo.local  → Restaurante Inteligente (bundle: restaurante_inteligente)
  - qr.demo@demo.local          → Menú QR Online standalone (bundle: menu_qr_online)

This command is idempotent and only runs in DEBUG mode or local/dev environment.

Usage:
    python manage.py seed_restaurant_qr_demo_accounts
    docker compose exec api python manage.py seed_restaurant_qr_demo_accounts

Prerequisites:
    python manage.py seed_billing   (creates bundles/modules)
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.billing.models import Bundle, Subscription as BillingSubscription
from apps.business.models import Business, Subscription as BusinessSubscription, BusinessPlan
from apps.accounts.models import Membership


User = get_user_model()

PASSWORD = 'Demo12345!'

DEMO_ACCOUNTS = [
    {
        'email': 'restaurant.demo@demo.local',
        'username': 'restaurant_demo',
        'business_name': 'Restaurante Demo',
        'default_service': 'restaurante',
        'bundle_code': 'restaurante_inteligente',
        'legacy_plan': BusinessPlan.PLUS,
        'max_branches': 1,
        'max_seats': 10,
    },
    {
        'email': 'qr.demo@demo.local',
        'username': 'qr_demo',
        'business_name': 'Carta QR Demo',
        'default_service': 'menu_qr',
        'bundle_code': 'menu_qr_online',
        'legacy_plan': BusinessPlan.MENU_QR,
        'max_branches': 1,
        'max_seats': 2,
    },
]


class Command(BaseCommand):
    help = 'Seeds demo accounts for Restaurante Inteligente and Menú QR Online (idempotent, DEBUG only)'

    def handle(self, *args, **kwargs):
        if not settings.DEBUG:
            raise CommandError(
                "❌ Este comando solo se puede ejecutar en DEBUG=True o entorno local/dev. "
                "Rechazado por seguridad."
            )

        self.stdout.write(self.style.WARNING(
            "🔍 Iniciando seed de cuentas demo de Restaurante y Menú QR..."
        ))

        try:
            with transaction.atomic():
                bundles = self._load_bundles()
                accounts = self._create_demo_accounts(bundles)
                self._verify_accounts(accounts)
                self._print_summary(accounts)

            self.stdout.write(self.style.SUCCESS("\n✅ Seed completado exitosamente."))

        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"\n❌ Error durante el seed: {exc}"))
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_bundles(self):
        """Load the required bundles, raising a clear error if seed_billing hasn't been run."""
        self.stdout.write("🔍 Verificando bundles disponibles...")
        codes = [d['bundle_code'] for d in DEMO_ACCOUNTS]
        bundles = {b.code: b for b in Bundle.objects.filter(code__in=codes, is_active=True)}

        missing = [c for c in codes if c not in bundles]
        if missing:
            raise CommandError(
                f"❌ Los siguientes bundles no existen: {missing}\n"
                "   Ejecuta primero: python manage.py seed_billing"
            )

        for code, bundle in bundles.items():
            price = (bundle.fixed_price_monthly or 0) / 100
            self.stdout.write(f"   ✓ {bundle.name} ({code}) – ${price:.2f}/mes")

        return bundles

    def _create_demo_accounts(self, bundles):
        accounts = []
        for data in DEMO_ACCOUNTS:
            self.stdout.write(f"\n📦 Procesando: {data['email']}...")
            bundle = bundles[data['bundle_code']]

            # 1. User
            user, u_created = User.objects.get_or_create(
                email=data['email'],
                defaults={'username': data['username'], 'is_active': True, 'is_staff': False},
            )
            user.set_password(PASSWORD)
            user.save()
            action = "✅ creado" if u_created else "♻️  ya existía (password actualizado)"
            self.stdout.write(f"   {action}: {user.email}")

            # 2. Business
            business, b_created = Business.objects.get_or_create(
                name=data['business_name'],
                defaults={
                    'default_service': data['default_service'],
                    'status': 'active',
                    'parent': None,
                },
            )
            if not b_created:
                # Sync the service in case it drifted
                if business.default_service != data['default_service']:
                    business.default_service = data['default_service']
                    business.save(update_fields=['default_service'])
            action = "✅ creado" if b_created else "♻️  ya existía"
            self.stdout.write(f"   {action}: {business.name} (service={business.default_service})")

            # 3. Membership
            membership, m_created = Membership.objects.get_or_create(
                user=user, business=business, defaults={'role': 'owner'}
            )
            if not m_created and membership.role != 'owner':
                membership.role = 'owner'
                membership.save(update_fields=['role'])
            action = "✅ creado" if m_created else "♻️  ya existía"
            self.stdout.write(f"   {action}: membership owner")

            # 4. Business (legacy) Subscription
            biz_sub, bs_created = BusinessSubscription.objects.update_or_create(
                business=business,
                defaults={
                    'plan': data['legacy_plan'],
                    'service': data['default_service'],
                    'status': 'active',
                    'max_branches': data['max_branches'],
                    'max_seats': data['max_seats'],
                    'renews_at': None,
                },
            )
            action = "✅ creada" if bs_created else "♻️  actualizada"
            self.stdout.write(f"   {action}: suscripción legacy plan={data['legacy_plan']}")

            # 5. Billing Subscription
            billing_sub, s_created = BillingSubscription.objects.update_or_create(
                business=business,
                defaults={
                    'plan_type': 'bundle',
                    'bundle': bundle,
                    'billing_period': 'monthly',
                    'currency': 'ARS',
                    'status': 'active',
                    'price_snapshot': {
                        'bundle_code': bundle.code,
                        'bundle_name': bundle.name,
                        'price_monthly': str(bundle.fixed_price_monthly),
                        'created_at': timezone.now().isoformat(),
                    },
                    'current_period_end': None,
                    'next_billing_date': None,
                },
            )
            if bundle.modules.exists():
                billing_sub.selected_modules.set(bundle.modules.all())

            action = "✅ creada" if s_created else "♻️  actualizada"
            self.stdout.write(
                f"   {action}: suscripción billing bundle={bundle.name} "
                f"({billing_sub.selected_modules.count()} módulos)"
            )

            accounts.append({
                'email': data['email'],
                'password': PASSWORD,
                'business_name': data['business_name'],
                'bundle_name': bundle.name,
                'bundle_code': bundle.code,
                'default_service': data['default_service'],
                'legacy_plan': data['legacy_plan'],
                'user': user,
                'business': business,
                'subscription': billing_sub,
            })

        return accounts

    def _verify_accounts(self, accounts):
        """Verify enabled_services resolver returns the expected service."""
        from apps.business.context import build_business_context

        self.stdout.write("\n🔍 Verificando servicios habilitados con el resolver...")
        all_ok = True
        for account in accounts:
            ctx = build_business_context(account['business'])
            enabled = ctx['enabled_services']
            expected_service = account['default_service']

            if expected_service in enabled:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"   ✅ {account['email']}: enabled_services={enabled}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"   ❌ {account['email']}: enabled_services={enabled} "
                        f"(esperaba '{expected_service}')"
                    )
                )
                all_ok = False

        if not all_ok:
            raise CommandError(
                "\n❌ Verificación fallida: algunas cuentas no tienen el servicio habilitado. "
                "Revisá features.py y service_catalog.py."
            )

    def _print_summary(self, accounts):
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("✅ CUENTAS DEMO CREADAS / ACTUALIZADAS"))
        self.stdout.write("=" * 80)

        for idx, account in enumerate(accounts, 1):
            price = (
                account['subscription'].bundle.fixed_price_monthly / 100
                if account['subscription'].bundle and account['subscription'].bundle.fixed_price_monthly
                else 0
            )
            self.stdout.write(f"\n{idx}. Plan: {account['bundle_name']} ({account['bundle_code']})")
            self.stdout.write(f"   📧 Email:     {account['email']}")
            self.stdout.write(f"   🔑 Password:  {account['password']}")
            self.stdout.write(f"   🏢 Negocio:   {account['business_name']}")
            self.stdout.write(f"   🗂️  Servicio:  {account['default_service']}")
            self.stdout.write(f"   📋 Legacy:    {account['legacy_plan']}")
            self.stdout.write(f"   💰 Precio:    ${price:.2f}/mes")
            self.stdout.write(f"   📦 Módulos:   {account['subscription'].selected_modules.count()} incluidos")

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("🔗 Acceso:")
        self.stdout.write("   Frontend:  http://localhost:3000/entrar")
        self.stdout.write("   Admin:     http://localhost:8000/admin")
        self.stdout.write("=" * 80 + "\n")

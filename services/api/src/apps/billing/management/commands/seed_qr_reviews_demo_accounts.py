"""
Management command to seed TWO demo accounts for QR de Reseñas QA.

Creates (idempotent, DEBUG only):

  Cuenta 1 — QR Reseñas básico
    email:    qr.basic@demo.local
    password: Demo12345!
    plan:     qr_reviews  (PLAN_ENTITLEMENTS: config, qr, dashboard)
    NO entitlement: qr_reviews.print_posters

  Cuenta 2 — Reseñas PRO
    email:    qr.pro@demo.local
    password: Demo12345!
    plan:     qr_reviews_pro  (PLAN_ENTITLEMENTS: +print_posters)
    HAS entitlement: qr_reviews.print_posters

Usage:
    python manage.py seed_qr_reviews_demo_accounts
    docker compose exec api python manage.py seed_qr_reviews_demo_accounts

Prerequisites:
    python manage.py seed_billing   (creates bundles/modules)
"""

import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.billing.models import Bundle, Subscription as BillingSubscription
from apps.business.models import Business, BusinessPlan, Subscription as BusinessSubscription
from apps.accounts.models import Membership
from apps.menu.models import MenuEngagementSettings

User = get_user_model()

PASSWORD = 'Demo12345!'
SERVICE = 'qr_reviews'

# Google Place ID for the Obelisco de Buenos Aires — stable public landmark.
DEMO_PLACE_ID = 'ChIJYYBCryHKvJURGnvIRqKJFPU'

DEMO_ACCOUNTS = [
    {
        'label':         'QR Reseñas Básico',
        'email':         'qr.basic@demo.local',
        'username':      'qr_basic_demo',
        'business_name': 'Demo QR Reseñas Básico',
        'slug':          'demo-qr-resenas-basico',
        'bundle_code':   'qr_reviews_base',
        'legacy_plan':   BusinessPlan.QR_REVIEWS_BASE,   # 'qr_reviews_base'
        'service':       SERVICE,
        'max_branches':  1,
        'max_seats':     2,
        # Entitlement gating (for verification only)
        'must_have':     {'qr_reviews.config', 'qr_reviews.qr', 'qr_reviews.dashboard'},
        'must_not_have': {'qr_reviews.print_posters'},
    },
    {
        'label':         'Reseñas PRO',
        'email':         'qr.pro@demo.local',
        'username':      'qr_pro_demo',
        'business_name': 'Demo Reseñas PRO',
        'slug':          'demo-resenas-pro',
        'bundle_code':   'qr_reviews_pro',
        'legacy_plan':   BusinessPlan.QR_REVIEWS_PRO,   # 'qr_reviews_pro'
        'service':       SERVICE,
        'max_branches':  1,
        'max_seats':     2,
        'must_have':     {
            'qr_reviews.config', 'qr_reviews.qr',
            'qr_reviews.dashboard', 'qr_reviews.print_posters',
        },
        'must_not_have': set(),
    },
]


class Command(BaseCommand):
    help = (
        'Seeds TWO demo accounts for QR de Reseñas QA: '
        'qr.basic@demo.local (base) and qr.pro@demo.local (PRO). '
        'Idempotent. DEBUG by default. In production requires --allow-production.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--allow-production',
            action='store_true',
            help='Permite ejecutar este seed con DEBUG=False de forma explícita.',
        )

    def handle(self, *args, **kwargs):
        allow_production = kwargs.get('allow_production', False)

        if not settings.DEBUG and not allow_production:
            raise CommandError(
                "❌ Este comando solo se puede ejecutar en DEBUG=True. "
                "En producción usá explícitamente: --allow-production"
            )

        if not settings.DEBUG and allow_production:
            self.stdout.write(self.style.WARNING(
                "\n⚠️ Ejecutando seed de cuentas demo QR de Reseñas en producción "
                "por uso explícito de --allow-production.\n"
            ))

        self.stdout.write(self.style.WARNING(
            "\n🔍 Iniciando seed de cuentas demo QR de Reseñas (básico + PRO)...\n"
        ))

        try:
            with transaction.atomic():
                bundles = self._load_bundles()
                accounts = [self._create_account(data, bundles) for data in DEMO_ACCOUNTS]
                self._verify_accounts(accounts, DEMO_ACCOUNTS)
                self._print_summary(accounts, DEMO_ACCOUNTS)

            self.stdout.write(self.style.SUCCESS("\n✅ Seed completado exitosamente.\n"))

        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"\n❌ Error durante el seed: {exc}"))
            raise

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _load_bundles(self) -> dict:
        codes = [d['bundle_code'] for d in DEMO_ACCOUNTS]
        self.stdout.write("🔍 Verificando bundles...")
        found = {b.code: b for b in Bundle.objects.filter(code__in=codes, is_active=True)}
        missing = [c for c in codes if c not in found]
        if missing:
            raise CommandError(
                f"❌ Bundles faltantes: {missing}\n"
                "   Ejecuta primero: python manage.py seed_billing"
            )
        for code, bundle in found.items():
            price = bundle.fixed_price_monthly or 0
            self.stdout.write(f"   ✓ {bundle.name} ({code}) – ${price:,.0f}/mes")
        return found

    def _create_account(self, data: dict, bundles: dict) -> dict:
        bundle = bundles[data['bundle_code']]
        self.stdout.write(f"\n📦 Procesando: {data['email']}  [{data['label']}]")

        # 1. User
        user, u_created = User.objects.get_or_create(
            email=data['email'],
            defaults={
                'username': data['username'],
                'is_active': True,
                'is_staff': False,
            },
        )
        user.set_password(PASSWORD)
        user.save()
        action = "✅ creado" if u_created else "♻️  ya existía (password actualizado)"
        self.stdout.write(f"   {action}: {user.email}")

        # 2. Business
        business, b_created = Business.objects.get_or_create(
            name=data['business_name'],
            defaults={
                'default_service': data['service'],
                'slug': data['slug'],
                'status': 'active',
            },
        )
        if not b_created:
            changed = []
            if business.default_service != data['service']:
                business.default_service = data['service']
                changed.append('default_service')
            if business.slug != data['slug']:
                business.slug = data['slug']
                changed.append('slug')
            if business.status != 'active':
                business.status = 'active'
                changed.append('status')
            if changed:
                business.save(update_fields=changed)
        action = "✅ creado" if b_created else "♻️  ya existía"
        self.stdout.write(f"   {action}: {business.name} (slug={business.slug})")

        # 3. Membership
        membership, m_created = Membership.objects.get_or_create(
            user=user, business=business, defaults={'role': 'owner'}
        )
        if not m_created and membership.role != 'owner':
            membership.role = 'owner'
            membership.save(update_fields=['role'])
        action = "✅ creada" if m_created else "♻️  ya existía"
        self.stdout.write(f"   {action}: membership owner")

        # 4. Legacy Subscription (business.Subscription)
        biz_sub, bs_created = BusinessSubscription.objects.update_or_create(
            business=business,
            defaults={
                'plan':         data['legacy_plan'],
                'service':      data['service'],
                'status':       'active',
                'max_branches': data['max_branches'],
                'max_seats':    data['max_seats'],
                'renews_at':    None,
            },
        )
        action = "✅ creada" if bs_created else "♻️  actualizada"
        self.stdout.write(f"   {action}: suscripción legacy plan={data['legacy_plan']}")

        # 5. Billing Subscription (billing.Subscription / bundle-based)
        billing_sub, s_created = BillingSubscription.objects.update_or_create(
            business=business,
            defaults={
                'plan_type':      'bundle',
                'bundle':         bundle,
                'billing_period': 'monthly',
                'currency':       'ARS',
                'status':         'active',
                'price_snapshot': {
                    'bundle_code':    bundle.code,
                    'bundle_name':    bundle.name,
                    'price_monthly':  str(bundle.fixed_price_monthly),
                    'created_at':     timezone.now().isoformat(),
                },
                'current_period_end': None,
                'next_billing_date':  None,
            },
        )
        if bundle.modules.exists():
            billing_sub.selected_modules.set(bundle.modules.all())
        action = "✅ creada" if s_created else "♻️  actualizada"
        self.stdout.write(
            f"   {action}: billing bundle={bundle.name} "
            f"({billing_sub.selected_modules.count()} módulos)"
        )

        # 6. MenuEngagementSettings (review config)
        eng, e_created = MenuEngagementSettings.objects.update_or_create(
            business=business,
            defaults={
                'reviews_enabled': True,
                'google_place_id': DEMO_PLACE_ID,
            },
        )
        action = "✅ creado" if e_created else "♻️  actualizado"
        self.stdout.write(
            f"   {action}: MenuEngagementSettings  "
            f"(place_id={DEMO_PLACE_ID}, reviews_enabled=True)"
        )

        return {
            'data':         data,
            'user':         user,
            'business':     business,
            'biz_sub':      biz_sub,
            'billing_sub':  billing_sub,
            'engagement':   eng,
        }

    def _verify_accounts(self, accounts: list, configs: list) -> None:
        from apps.business.entitlements import has_entitlement

        self.stdout.write("\n🔍 Verificando entitlements...")
        all_ok = True

        for account, cfg in zip(accounts, configs):
            business = account['business']
            label = cfg['label']

            for ent in sorted(cfg['must_have']):
                ok = has_entitlement(business, ent)
                icon = "✅" if ok else "❌"
                self.stdout.write(f"   {icon} [{label}] DEBE tener:    {ent}")
                if not ok:
                    all_ok = False

            for ent in sorted(cfg['must_not_have']):
                ok = not has_entitlement(business, ent)
                icon = "✅" if ok else "❌"
                self.stdout.write(f"   {icon} [{label}] NO debe tener: {ent}")
                if not ok:
                    all_ok = False

        if not all_ok:
            raise CommandError(
                "\n❌ Verificación de entitlements fallida. "
                "Revisá PLAN_ENTITLEMENTS en entitlements.py."
            )

    def _print_summary(self, accounts: list, configs: list) -> None:
        self.stdout.write("\n" + "=" * 72)
        self.stdout.write(self.style.SUCCESS("✅ CUENTAS DEMO QR RESEÑAS — LISTAS"))
        self.stdout.write("=" * 72)

        for account, cfg in zip(accounts, configs):
            biz = account['business']
            self.stdout.write(f"\n{cfg['label']}:")
            self.stdout.write(f"   📧 email:    {cfg['email']}")
            self.stdout.write(f"   🔑 password: {PASSWORD}")
            self.stdout.write(f"   🏢 negocio:  {biz.name}")
            self.stdout.write(f"   🔗 slug:     {biz.slug}")
            self.stdout.write(f"   📋 plan:     {cfg['legacy_plan']}")
            self.stdout.write(f"   📦 bundle:   {cfg['bundle_code']}")
            if cfg['must_not_have']:
                self.stdout.write(f"   🚫 sin:      {', '.join(sorted(cfg['must_not_have']))}")
            if 'qr_reviews.print_posters' in cfg['must_have']:
                self.stdout.write(f"   ✅ con:      qr_reviews.print_posters")

        self.stdout.write("\n" + "─" * 72)
        self.stdout.write("🔗 URLs para probar:")
        self.stdout.write("   Login:      http://localhost:3000/entrar")
        self.stdout.write("")

        for account, cfg in zip(accounts, configs):
            biz = account['business']
            self.stdout.write(f"   [{cfg['label']}]")
            self.stdout.write(f"   Dashboard:  http://localhost:3000/app/resenas")
            self.stdout.write(f"   Mi QR:      http://localhost:3000/app/resenas/qr")
            if 'qr_reviews.print_posters' in cfg['must_have']:
                self.stdout.write(f"   Carteles:   http://localhost:3000/app/resenas/carteles")
            self.stdout.write(f"   Landing:    http://localhost:3000/r/{biz.slug}/")
            self.stdout.write("")

        self.stdout.write("📋 Checklist QA rápido:")
        self.stdout.write(
            "   Básico  → ve QR, NO ve tab Carteles, /app/resenas/carteles redirige"
        )
        self.stdout.write(
            "   PRO     → ve QR + tab Carteles, puede crear/guardar/descargar cartel"
        )
        self.stdout.write("=" * 72 + "\n")

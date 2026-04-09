"""
Management command to seed a demo account for QR de Reseñas.

Creates 1 demo user + business with everything needed to test the full flow:
  - Login
  - Dashboard /app/resenas
  - Configuración (Google Place ID)
  - QR generation
  - Public landing /r/demo-qr-reviews/

Credentials:
  - email:    qr.reviews@demo.local
  - password: Demo12345!

This command is idempotent and only runs in DEBUG mode.

Usage:
    python manage.py seed_qr_reviews_demo
    docker compose exec api python manage.py seed_qr_reviews_demo

Prerequisites:
    python manage.py seed_billing   (creates bundles/modules)
"""

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

EMAIL = 'qr.reviews@demo.local'
USERNAME = 'qr_reviews_demo'
PASSWORD = 'Demo12345!'
BUSINESS_NAME = 'Demo QR Reviews'
SLUG = 'demo-qr-reviews'
BUNDLE_CODE = 'qr_reviews'
LEGACY_PLAN = BusinessPlan.QR_REVIEWS
SERVICE = 'qr_reviews'

# Google Place ID for the Obelisco de Buenos Aires — a well-known, stable landmark.
DEMO_PLACE_ID = 'ChIJYYBCryHKvJURGnvIRqKJFPU'


class Command(BaseCommand):
    help = 'Seeds a demo account for QR de Reseñas (idempotent, DEBUG only)'

    def handle(self, *args, **kwargs):
        if not settings.DEBUG:
            raise CommandError(
                "❌ Este comando solo se puede ejecutar en DEBUG=True. "
                "Rechazado por seguridad."
            )

        self.stdout.write(self.style.WARNING(
            "🔍 Iniciando seed de cuenta demo QR de Reseñas..."
        ))

        try:
            with transaction.atomic():
                bundle = self._load_bundle()
                account = self._create_account(bundle)
                self._create_engagement(account['business'])
                self._verify(account)
                self._print_summary(account)

            self.stdout.write(self.style.SUCCESS("\n✅ Seed completado exitosamente."))

        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"\n❌ Error durante el seed: {exc}"))
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_bundle(self):
        self.stdout.write("🔍 Verificando bundle qr_reviews...")
        try:
            bundle = Bundle.objects.get(code=BUNDLE_CODE, is_active=True)
        except Bundle.DoesNotExist:
            raise CommandError(
                f"❌ Bundle '{BUNDLE_CODE}' no existe.\n"
                "   Ejecuta primero: python manage.py seed_billing"
            )
        price = bundle.fixed_price_monthly or 0
        mods = bundle.modules.count()
        self.stdout.write(f"   ✓ {bundle.name} ({BUNDLE_CODE}) – ${price:.0f}/mes – {mods} módulos")
        return bundle

    def _create_account(self, bundle):
        # 1. User
        user, u_created = User.objects.get_or_create(
            email=EMAIL,
            defaults={'username': USERNAME, 'is_active': True, 'is_staff': False},
        )
        user.set_password(PASSWORD)
        user.save()
        action = "✅ creado" if u_created else "♻️  ya existía (password actualizado)"
        self.stdout.write(f"   {action}: {user.email}")

        # 2. Business
        business, b_created = Business.objects.get_or_create(
            name=BUSINESS_NAME,
            defaults={
                'default_service': SERVICE,
                'slug': SLUG,
                'status': 'active',
            },
        )
        if not b_created:
            changed = []
            if business.default_service != SERVICE:
                business.default_service = SERVICE
                changed.append('default_service')
            if business.slug != SLUG:
                business.slug = SLUG
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
                'plan': LEGACY_PLAN,
                'service': SERVICE,
                'status': 'active',
                'max_branches': 1,
                'max_seats': 2,
                'renews_at': None,
            },
        )
        action = "✅ creada" if bs_created else "♻️  actualizada"
        self.stdout.write(f"   {action}: suscripción legacy plan={LEGACY_PLAN}")

        # 5. Billing Subscription (billing.Subscription / SubscriptionV2)
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

        return {
            'user': user,
            'business': business,
            'subscription': billing_sub,
        }

    def _create_engagement(self, business):
        """Create MenuEngagementSettings with a working Google Place ID."""
        eng, created = MenuEngagementSettings.objects.update_or_create(
            business=business,
            defaults={
                'reviews_enabled': True,
                'google_place_id': DEMO_PLACE_ID,
            },
        )
        action = "✅ creado" if created else "♻️  actualizado"
        review_url = eng.google_write_review_url or '(sin URL)'
        self.stdout.write(f"   {action}: MenuEngagementSettings")
        self.stdout.write(f"   ✓ reviews_enabled=True, place_id={DEMO_PLACE_ID}")
        self.stdout.write(f"   ✓ review_url={review_url}")

    def _verify(self, account):
        from apps.business.context import build_business_context

        self.stdout.write("\n🔍 Verificando contexto de sesión...")
        ctx = build_business_context(account['business'])
        features = ctx['features']
        services = ctx['enabled_services']
        active = ctx['service']

        ok = True
        checks = [
            ('qr_reviews_core en features', features.get('qr_reviews_core', False)),
            ('service activo = qr_reviews', active == 'qr_reviews'),
            ('qr_reviews en enabled_services', 'qr_reviews' in services),
            ('menu_qr NO en enabled_services', 'menu_qr' not in services),
        ]

        for label, passed in checks:
            icon = "✅" if passed else "❌"
            self.stdout.write(f"   {icon} {label}")
            if not passed:
                ok = False

        if not ok:
            raise CommandError(
                "❌ Verificación fallida. Revisá features.py y service_catalog.py."
            )

    def _print_summary(self, account):
        business = account['business']
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("✅ CUENTA DEMO QR DE RESEÑAS — LISTA"))
        self.stdout.write("=" * 70)
        self.stdout.write(f"   📧 Email:       {EMAIL}")
        self.stdout.write(f"   🔑 Password:    {PASSWORD}")
        self.stdout.write(f"   🏢 Negocio:     {business.name}")
        self.stdout.write(f"   🔗 Slug:        {business.slug}")
        self.stdout.write(f"   🗂️  Plan:        {LEGACY_PLAN}")
        self.stdout.write(f"   📦 Service:     {SERVICE}")
        self.stdout.write("")
        self.stdout.write("🔗 URLs para probar:")
        self.stdout.write("   Login:          http://localhost:3000/entrar")
        self.stdout.write("   Dashboard:      http://localhost:3000/app/resenas")
        self.stdout.write("   Configuración:  http://localhost:3000/app/resenas/configuracion")
        self.stdout.write("   Mi QR:          http://localhost:3000/app/resenas/qr")
        self.stdout.write(f"   Landing pública: http://localhost:3000/r/{business.slug}/")
        self.stdout.write("")
        self.stdout.write("📋 Checklist QA:")
        self.stdout.write("   1. Login con qr.reviews@demo.local / Demo12345!")
        self.stdout.write("   2. Dashboard muestra cards Configuración + Mi QR")
        self.stdout.write("   3. Configuración muestra Place ID pre-cargado")
        self.stdout.write("   4. Mi QR genera código QR descargable")
        self.stdout.write(f"   5. /r/{business.slug}/ redirige a Google Reviews")
        self.stdout.write("=" * 70 + "\n")

"""
Management command: create_checkout_test_user
=============================================
Creates (or resets) a local/staging test user ready to go through the
onboarding checkout flow with promo codes, WITHOUT touching MercadoPago.

SAFETY RULES
------------
- Aborts if settings.DEBUG is False unless --force is supplied.
- Must NEVER be used on production data.
- Does not modify .env, credentials, or MercadoPago configuration.

What it creates / resets
-------------------------
1. Django User (email as username, is_active=True, password set).
2. AccountProfile  → account_status=ACTIVE, email_verified=True.
3. Business        → status='onboarding', service_type=<service>.
4. Membership      → role='owner', status=ACTIVE.
5. Legacy business.Subscription → CANCELED (so no legacy active sub exists).
6. Any open MpCheckoutSession for that business → status='expired'.
7. Any non-canceled SubscriptionV2 for that business → status='canceled'.
8. PromoCode LANZAMIENTO50 → created if not present (idempotent).

Usage
-----
    docker compose run --rm api python manage.py create_checkout_test_user \
        --email testpromo@mirubro.local \
        --password Test1234! \
        --business-name "Negocio Promo Test"
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AccountProfile, Membership
from apps.billing.models import (
    MpCheckoutSession,
    Plan,
    PromoCode,
    PromoCodeRedemption,
    SubscriptionV2,
)
from apps.business.models import Business, Subscription as BusinessSubscription

User = get_user_model()

# ── PromoCode seed defaults ───────────────────────────────────────────────────
PROMO_CODE           = "LANZAMIENTO50"
PROMO_NAME           = "Lanzamiento 50%"
PROMO_DISCOUNT_TYPE  = PromoCode.DiscountType.PERCENT
PROMO_DISCOUNT_VALUE = Decimal("50.00")
PROMO_DURATION       = 3          # billing cycles
PROMO_MAX_GLOBAL     = 20
PROMO_MAX_PER_BIZ    = 1
PROMO_PLAN_CODES     = ["gestion_pro"]
PROMO_SERVICE        = "gestion"
PROMO_PERIODS        = ["monthly"]


class Command(BaseCommand):
    help = (
        "Creates / resets a test user for the onboarding checkout + promo-code flow. "
        "Idempotent, DEBUG-only by default."
    )

    # ── Argument declaration ──────────────────────────────────────────────────

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            required=True,
            help="Email address (used as username too).",
        )
        parser.add_argument(
            "--password",
            required=True,
            help="Password for the test user.",
        )
        parser.add_argument(
            "--business-name",
            default="Negocio Promo Test",
            help="Display name for the test business. Default: 'Negocio Promo Test'.",
        )
        parser.add_argument(
            "--service",
            default="gestion",
            choices=["gestion", "restaurante", "menu_qr", "qr_reviews"],
            help="Service type for the business. Default: gestion.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Allow running outside DEBUG mode (use with extreme caution).",
        )

    # ── Entry point ───────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "\n❌  settings.DEBUG is False and --force was not passed.\n"
                "    This command MUST NOT be run against production data.\n"
                "    If you are on a non-production environment with DEBUG=False,\n"
                "    add --force to override this guard."
            )

        self.stdout.write(
            self.style.WARNING(
                "⚠️  create_checkout_test_user — FOR LOCAL/STAGING USE ONLY. "
                "NEVER run on production."
            )
        )

        email        = options["email"].strip().lower()
        password     = options["password"]
        business_name = options["business_name"]
        service      = options["service"]

        try:
            with transaction.atomic():
                user     = self._upsert_user(email, password)
                profile  = self._upsert_profile(user)
                business = self._upsert_business(user, business_name, service)
                self._upsert_membership(user, business)
                self._cancel_legacy_subscription(business)
                self._expire_open_checkout_sessions(business)
                self._cancel_active_subscriptions_v2(business, service)
                promo    = self._upsert_promo_code()

        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"\n❌  Error: {exc}"))
            raise

        self._print_summary(user, password, business, promo)

    # ── Step helpers ──────────────────────────────────────────────────────────

    def _upsert_user(self, email: str, password: str) -> "User":
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": email, "is_active": True},
        )
        if not created:
            # Reset state
            user.username  = email
            user.is_active = True
        user.set_password(password)
        user.save()

        label = "Creado" if created else "Actualizado"
        self.stdout.write(f"  👤 Usuario {label}: {email}  (pk={user.pk})")
        return user

    def _upsert_profile(self, user) -> AccountProfile:
        profile, created = AccountProfile.objects.get_or_create(
            user=user,
            defaults={
                "account_status": AccountProfile.AccountStatus.ACTIVE,
                "email_verified": True,
                "auth_provider":  AccountProfile.AuthProvider.EMAIL,
                "account_mode":   AccountProfile.AccountMode.OWNER_MANAGED,
            },
        )
        if not created:
            profile.account_status = AccountProfile.AccountStatus.ACTIVE
            profile.email_verified = True
            # Clear any pending token hashes
            profile.email_verification_token_hash    = None
            profile.email_verification_token_created_at = None
            profile.password_reset_token_hash        = None
            profile.password_reset_token_created_at  = None
            profile.must_change_password             = False
            profile.save()

        label = "Creado" if created else "Actualizado"
        self.stdout.write(f"  📋 AccountProfile {label}: status=ACTIVE, email_verified=True")
        return profile

    def _upsert_business(self, user, name: str, service: str) -> Business:
        """
        Look for an existing HQ business owned by this user with the same name.
        If found, reset it to 'onboarding'.  Otherwise create a new one.
        """
        # Find existing owned business with same name
        existing_biz_id = (
            Membership.objects
            .filter(user=user, role="owner", status=Membership.Status.ACTIVE)
            .values_list("business_id", flat=True)
        )
        business = (
            Business.objects
            .filter(pk__in=existing_biz_id, name=name, parent__isnull=True)
            .first()
        )

        if business:
            business.status       = "onboarding"
            business.service_type = service
            business.default_service = service
            business.trial_starts_at = None
            business.trial_ends_at   = None
            business.activated_at    = None
            business.suspended_at    = None
            business.save()
            self.stdout.write(f"  🏢 Business actualizado: \"{name}\" (pk={business.pk})")
        else:
            business = Business.objects.create(
                name=name,
                status="onboarding",
                service_type=service,
                default_service=service,
                country="AR",
                currency="ARS",
                timezone="America/Argentina/Buenos_Aires",
            )
            self.stdout.write(f"  🏢 Business creado: \"{name}\" (pk={business.pk})")

        return business

    def _upsert_membership(self, user, business: Business) -> Membership:
        membership, created = Membership.objects.get_or_create(
            user=user,
            business=business,
            defaults={"role": "owner", "status": Membership.Status.ACTIVE},
        )
        if not created:
            membership.role   = "owner"
            membership.status = Membership.Status.ACTIVE
            membership.save()

        label = "Creada" if created else "Actualizada"
        self.stdout.write(f"  🔑 Membership {label}: role=owner, status=ACTIVE")
        return membership

    def _cancel_legacy_subscription(self, business: Business) -> None:
        """
        Marks any legacy business.Subscription as 'canceled'.
        This prevents the frontend from treating the user as already subscribed
        via the old subscription model.
        """
        updated = (
            BusinessSubscription.objects
            .filter(business=business)
            .exclude(status="canceled")
            .update(status="canceled")
        )
        if updated:
            self.stdout.write(
                f"  🗑️  Legacy Subscription: {updated} registro(s) marcado(s) canceled"
            )
        else:
            self.stdout.write("  ✅ Legacy Subscription: sin suscripción activa (ok)")

    def _expire_open_checkout_sessions(self, business: Business) -> None:
        """
        Transitions all open MpCheckoutSessions for this business to 'expired'.
        This prevents the idempotency gate from reusing a stale session and
        skipping the checkout UI.
        """
        open_sessions = MpCheckoutSession.objects.filter(
            tenant=business,
            status__in=MpCheckoutSession.OPEN_STATUSES,
        )
        count = open_sessions.count()
        if count:
            # Also cancel any pending PromoCodeRedemptions attached to them
            session_ids = list(open_sessions.values_list("id", flat=True))
            PromoCodeRedemption.objects.filter(
                checkout_session_id__in=session_ids,
                status__in=[PromoCodeRedemption.Status.PENDING],
            ).update(status=PromoCodeRedemption.Status.CANCELLED, updated_at=timezone.now())

            open_sessions.update(
                status=MpCheckoutSession.Status.EXPIRED,
                updated_at=timezone.now(),
            )
            self.stdout.write(
                f"  🗑️  MpCheckoutSessions: {count} sesión(es) expirada(s)"
            )
        else:
            self.stdout.write("  ✅ MpCheckoutSessions: ninguna sesión abierta (ok)")

    def _cancel_active_subscriptions_v2(self, business: Business, service: str) -> None:
        """
        Cancels any non-terminal SubscriptionV2 for this business (all service types).
        Ensures the business is seen as having no active subscription.
        """
        non_terminal = (
            SubscriptionV2.objects
            .filter(business=business)
            .exclude(status__in=SubscriptionV2.TERMINAL_STATUSES)
        )
        count = non_terminal.count()
        if count:
            non_terminal.update(
                status=SubscriptionV2.Status.CANCELED,
                canceled_at=timezone.now(),
                updated_at=timezone.now(),
            )
            self.stdout.write(
                f"  🗑️  SubscriptionV2: {count} suscripción(es) cancelada(s)"
            )
        else:
            self.stdout.write("  ✅ SubscriptionV2: ninguna suscripción activa (ok)")

    def _upsert_promo_code(self) -> PromoCode:
        """
        Creates LANZAMIENTO50 if it does not exist, or updates its key fields
        to match the spec if it does.
        """
        # Validate that the target plan code actually exists in the DB
        existing_plan_codes = set(
            Plan.objects.filter(code__in=PROMO_PLAN_CODES).values_list("code", flat=True)
        )
        if not existing_plan_codes:
            self.stdout.write(
                self.style.WARNING(
                    f"  ⚠️  Ningún Plan con code en {PROMO_PLAN_CODES} encontrado en la BD. "
                    f"El PromoCode se creará igualmente pero no pasará la validación del servicio. "
                    f"Ejecuta primero: python manage.py seed_billing"
                )
            )

        promo, created = PromoCode.objects.get_or_create(
            code=PROMO_CODE,
            defaults={
                "name":                        PROMO_NAME,
                "discount_type":               PROMO_DISCOUNT_TYPE,
                "discount_value":              PROMO_DISCOUNT_VALUE,
                "duration_cycles":             PROMO_DURATION,
                "max_redemptions":             PROMO_MAX_GLOBAL,
                "max_redemptions_per_business": PROMO_MAX_PER_BIZ,
                "active":                      True,
                "applies_to_plan_codes":       PROMO_PLAN_CODES,
                "applies_to_service":          PROMO_SERVICE,
                "applies_to_billing_periods":  PROMO_PERIODS,
            },
        )
        if not created:
            # Ensure it's active and its key fields match the spec
            promo.name                        = PROMO_NAME
            promo.discount_type               = PROMO_DISCOUNT_TYPE
            promo.discount_value              = PROMO_DISCOUNT_VALUE
            promo.duration_cycles             = PROMO_DURATION
            promo.max_redemptions             = PROMO_MAX_GLOBAL
            promo.max_redemptions_per_business = PROMO_MAX_PER_BIZ
            promo.active                      = True
            promo.applies_to_plan_codes       = PROMO_PLAN_CODES
            promo.applies_to_service          = PROMO_SERVICE
            promo.applies_to_billing_periods  = PROMO_PERIODS
            promo.save()

        label = "Creado" if created else "Actualizado"
        self.stdout.write(
            f"  🎟️  PromoCode {label}: {PROMO_CODE} "
            f"({PROMO_DISCOUNT_VALUE}% × {PROMO_DURATION} ciclos, plans={PROMO_PLAN_CODES})"
        )
        return promo

    # ── Summary ───────────────────────────────────────────────────────────────

    def _print_summary(self, user, password: str, business: Business, promo: PromoCode) -> None:
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("✅  Usuario de prueba listo"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Email       : {user.email}")
        self.stdout.write(f"  Password    : {password}")
        self.stdout.write(f"  Business ID : {business.pk}")
        self.stdout.write(f"  Business    : {business.name}")
        self.stdout.write(f"  Status Biz  : {business.status}  (sin suscripción activa)")
        self.stdout.write(f"  Promo code  : {promo.code}  ({promo.discount_value}% × {promo.duration_cycles} ciclos)")
        self.stdout.write("")
        self.stdout.write("  ── Próximos pasos ──────────────────────────────────")
        self.stdout.write("  1. Iniciá sesión en:  http://localhost:3000/entrar")
        self.stdout.write(f"     Email:    {user.email}")
        self.stdout.write(f"     Password: {password}")
        self.stdout.write("  2. El sistema te va a llevar al onboarding.")
        self.stdout.write("     Elegí Gestión Comercial → Plan Pro.")
        self.stdout.write("  3. En el paso de pago ingresá el código:")
        self.stdout.write(f"     ➤  {promo.code}")
        self.stdout.write("  4. Verificá el descuento antes de hacer clic en")
        self.stdout.write("     'Suscribirme' (que llama a MercadoPago).")
        self.stdout.write(self.style.SUCCESS("=" * 60))

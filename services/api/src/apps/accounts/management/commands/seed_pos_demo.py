"""
Management command: seed_pos_demo
==================================
Seeds a minimal but complete demo dataset for manually validating the full system
with the new Phase 2A operational architecture.

Creates (idempotently):
  - Business "Demo Comercial" (Gestión Comercial, PRO plan)
  - Owner user  → owner.demo@mirubro.local / Demo12345!
  - Branch      → Sucursal Centro
  - CashRegister + Terminal → Caja 1 / CAJA-01
  - EmployeeProfile cashier → CAJA001 / PIN 123456
  - EmployeeProfile (optional second) → CAJA002 / PIN 999999 (must_change_pin=True)
  - ProductCategory × 2
  - Product × 6 (with initial stock)

Safety:
  - Blocked in production (DJANGO_DEBUG=False) unless --allow-prod is passed explicitly.
  - Fully idempotent: running it twice produces no duplicates.

Usage (dev / docker):
  python manage.py seed_pos_demo
  docker compose exec api python manage.py seed_pos_demo

  # Force run in non-DEBUG environment (e.g. staging with explicit intent):
  python manage.py seed_pos_demo --allow-prod
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import EmployeeProfile, Membership
from apps.business.models import Business, BusinessPlan, Subscription
from apps.cash.models import CashRegister, Terminal
from apps.catalog.models import Product, ProductCategory
from apps.inventory.models import ProductStock

User = get_user_model()

# ── Demo Credentials (non-sensitive — intended for dev/staging only) ─────────
OWNER_EMAIL    = "owner.demo@mirubro.local"
OWNER_PASSWORD = "Demo12345!"

CASHIER_CODE   = "CAJA001"
CASHIER_PIN    = "123456"

CASHIER2_CODE  = "CAJA002"
CASHIER2_PIN   = "999999"

# ── Catalogue ─────────────────────────────────────────────────────────────────
DEMO_CATEGORIES = [
    "Bebidas",
    "Comidas",
]

DEMO_PRODUCTS: list[dict] = [
    # name, sku, category_name, cost, price
    {"name": "Café",        "sku": "DEMO-001", "category": "Bebidas",  "cost": Decimal("80"),   "price": Decimal("250")},
    {"name": "Agua",        "sku": "DEMO-002", "category": "Bebidas",  "cost": Decimal("50"),   "price": Decimal("150")},
    {"name": "Gaseosa",     "sku": "DEMO-003", "category": "Bebidas",  "cost": Decimal("120"),  "price": Decimal("350")},
    {"name": "Sandwich",    "sku": "DEMO-004", "category": "Comidas",  "cost": Decimal("400"),  "price": Decimal("900")},
    {"name": "Tostado",     "sku": "DEMO-005", "category": "Comidas",  "cost": Decimal("350"),  "price": Decimal("800")},
    {"name": "Medialuna",   "sku": "DEMO-006", "category": "Comidas",  "cost": Decimal("80"),   "price": Decimal("200")},
]

INITIAL_STOCK = 100


class Command(BaseCommand):
    help = (
        "Seeds a complete demo dataset for POS + Gestión Comercial validation "
        "(idempotent, DEBUG-only by default)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-prod",
            action="store_true",
            default=False,
            help=(
                "Allow execution outside DEBUG mode. "
                "USE WITH EXTREME CAUTION on shared environments."
            ),
        )
        parser.add_argument(
            "--no-second-employee",
            action="store_true",
            default=False,
            help="Skip creation of the second employee (CAJA002 / must_change_pin).",
        )

    # ── Entry point ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self._guard_production(options["allow_prod"])

        self.stdout.write(self.style.WARNING(
            "\n⚡ seed_pos_demo — iniciando seed de datos de demostración...\n"
        ))

        with transaction.atomic():
            business  = self._seed_business()
            owner     = self._seed_owner(business)
            branch    = self._seed_branch(business)
            register, terminal = self._seed_register(business, branch)
            cashier   = self._seed_cashier(business, branch)
            cashier2  = None
            if not options["no_second_employee"]:
                cashier2 = self._seed_cashier2(business, branch)
            categories = self._seed_categories(business)
            products   = self._seed_products(business, categories)

        self._print_summary(business, owner, branch, register, terminal, cashier, cashier2, products)

    # ── Guards ────────────────────────────────────────────────────────────────

    def _guard_production(self, allow_prod: bool) -> None:
        if settings.DEBUG or allow_prod:
            return
        raise CommandError(
            "\n❌  BLOQUEADO: Este comando solo puede ejecutarse en entornos DEBUG=True.\n"
            "    Si realmente querés ejecutarlo en staging/prod, pasá --allow-prod EXPLÍCITAMENTE.\n"
            "    \n"
            "    ADVERTENCIA: correlo solo en ambientes aislados de producción real.\n"
        )

    # ── Business / Tenant ────────────────────────────────────────────────────

    def _seed_business(self) -> Business:
        self.stdout.write("  [1/7] Business...")

        business, created = Business.objects.get_or_create(
            slug="demo-comercial",
            defaults={
                "name": "Demo Comercial",
                "default_service": "gestion",
                "service_type": Business.ServiceType.GESTION,
                "status": "active",
                "country": "AR",
                "currency": "ARS",
                "timezone": "America/Argentina/Buenos_Aires",
                "activated_at": timezone.now(),
            },
        )
        if not created:
            # Keep slug canonical; update name if it drifted
            Business.objects.filter(pk=business.pk).update(
                name="Demo Comercial",
                service_type=Business.ServiceType.GESTION,
                status="active",
            )
            business.refresh_from_db()

        Subscription.objects.update_or_create(
            business=business,
            defaults={
                "plan": BusinessPlan.PRO,
                "status": "active",
                "max_branches": 2,
                "max_seats": 10,
                "renews_at": timezone.now() + datetime.timedelta(days=365),
            },
        )

        label = "creado" if created else "reutilizado"
        self.stdout.write(f"     ✓ Business «{business.name}» (id={business.pk}) [{label}]")
        return business

    # ── Owner User ────────────────────────────────────────────────────────────

    def _seed_owner(self, business: Business) -> User:
        self.stdout.write("  [2/7] Owner...")

        user, created = User.objects.get_or_create(
            email=OWNER_EMAIL,
            defaults={
                "username": OWNER_EMAIL,
                "first_name": "Owner",
                "last_name": "Demo",
                "is_active": True,
            },
        )
        # Always reset to the known demo password so credentials stay reliable
        # regardless of whether the user pre-existed.
        user.set_password(OWNER_PASSWORD)
        user.is_active = True
        user.save(update_fields=["password", "is_active"])

        # Clean up ghost HQ businesses created by _ensure_membership when someone
        # tried to log in before the seed ran (they land in status='onboarding').
        # These stale memberships would cause login to return onboarding=True
        # and redirect the user to /app/planes instead of /app/dashboard.
        ghost_businesses = (
            Business.objects.filter(
                memberships__user=user,
                status="onboarding",
            )
            .exclude(pk=business.pk)
        )
        if ghost_businesses.exists():
            ghost_names = list(ghost_businesses.values_list("name", flat=True))
            from apps.accounts.models import Membership as _Membership
            _Membership.objects.filter(user=user, business__in=ghost_businesses).delete()
            ghost_businesses.delete()
            self.stdout.write(f"     ⚠ Eliminados ghost onboarding businesses: {ghost_names}")

        Membership.objects.get_or_create(
            user=user,
            business=business,
            defaults={"role": "owner", "status": "active"},
        )

        label = "creado" if created else "reutilizado"
        self.stdout.write(f"     ✓ Owner {OWNER_EMAIL} [{label}]")
        return user

    # ── Branch ────────────────────────────────────────────────────────────────

    def _seed_branch(self, business: Business) -> Business:
        self.stdout.write("  [3/7] Branch...")

        branch, created = Business.objects.get_or_create(
            parent=business,
            name="Sucursal Centro",
            defaults={
                "default_service": "gestion",
                "service_type": Business.ServiceType.GESTION,
                "status": "active",
                "country": business.country,
                "currency": business.currency,
                "timezone": business.timezone,
            },
        )
        label = "creada" if created else "reutilizada"
        self.stdout.write(f"     ✓ Branch «{branch.name}» (id={branch.pk}) [{label}]")
        return branch

    # ── CashRegister + Terminal ───────────────────────────────────────────────

    def _seed_register(self, business: Business, branch: Business) -> tuple[CashRegister, Terminal]:
        self.stdout.write("  [4/7] CashRegister + Terminal...")

        register, r_created = CashRegister.objects.get_or_create(
            business=business,
            name="Caja 1",
            defaults={"is_active": True},
        )

        terminal, t_created = Terminal.objects.get_or_create(
            business=business,
            code="CAJA-01",
            defaults={
                "name": "Caja 1",
                "branch": branch,
                "cash_register": register,
                "terminal_type": Terminal.TerminalType.CASHIER,
                "is_active": True,
                "shared_mode_enabled": False,
                "requires_operator_selection": False,
            },
        )
        # Ensure the transition FK is set if the terminal pre-existed without it
        if not t_created and terminal.cash_register_id is None:
            Terminal.objects.filter(pk=terminal.pk).update(cash_register=register)
            terminal.refresh_from_db()

        r_label = "creada" if r_created else "reutilizada"
        t_label = "creado" if t_created else "reutilizado"
        self.stdout.write(
            f"     ✓ CashRegister «{register.name}» [{r_label}] | "
            f"Terminal «{terminal.code}» [{t_label}]"
        )
        return register, terminal

    # ── Primary Cashier ───────────────────────────────────────────────────────

    def _seed_cashier(self, business: Business, branch: Business) -> EmployeeProfile:
        self.stdout.write("  [5/7] Cashier principal (CAJA001)...")

        employee, created = EmployeeProfile.objects.get_or_create(
            business=business,
            employee_code=CASHIER_CODE,
            defaults={
                "first_name": "Caja",
                "last_name": "Demo",
                "alias": "Caja Principal",
                "branch": branch,
                "role_type": EmployeeProfile.RoleType.CASHIER,
                "credential_type": EmployeeProfile.CredentialType.PIN,
                "login_code_hash": make_password(CASHIER_PIN),
                "must_change_pin": False,
                "status": EmployeeProfile.Status.ACTIVE,
            },
        )
        if not created:
            # Re-hash in case the PIN changed or the hash is stale
            EmployeeProfile.objects.filter(pk=employee.pk).update(
                login_code_hash=make_password(CASHIER_PIN),
                status=EmployeeProfile.Status.ACTIVE,
                must_change_pin=False,
            )
            employee.refresh_from_db()

        label = "creado" if created else "reutilizado"
        self.stdout.write(f"     ✓ Employee {CASHIER_CODE} [{label}]")
        return employee

    # ── Second Cashier (must_change_pin=True) ────────────────────────────────

    def _seed_cashier2(self, business: Business, branch: Business) -> EmployeeProfile:
        self.stdout.write("  [5b] Cashier secundario (CAJA002, must_change_pin=True)...")

        employee, created = EmployeeProfile.objects.get_or_create(
            business=business,
            employee_code=CASHIER2_CODE,
            defaults={
                "first_name": "Caja",
                "last_name": "Secundaria",
                "alias": "Caja 2",
                "branch": branch,
                "role_type": EmployeeProfile.RoleType.CASHIER,
                "credential_type": EmployeeProfile.CredentialType.PIN,
                "login_code_hash": make_password(CASHIER2_PIN),
                "must_change_pin": True,
                "status": EmployeeProfile.Status.ACTIVE,
            },
        )

        label = "creado" if created else "reutilizado"
        self.stdout.write(f"     ✓ Employee {CASHIER2_CODE} [{label}]")
        return employee

    # ── Categories ────────────────────────────────────────────────────────────

    def _seed_categories(self, business: Business) -> dict[str, ProductCategory]:
        self.stdout.write("  [6/7] Categorias...")
        cats: dict[str, ProductCategory] = {}
        for name in DEMO_CATEGORIES:
            cat, created = ProductCategory.objects.get_or_create(
                business=business,
                name=name,
                defaults={"is_active": True},
            )
            cats[name] = cat
        self.stdout.write(f"     ✓ {len(cats)} categorías: {', '.join(cats)}")
        return cats

    # ── Products + Stock ──────────────────────────────────────────────────────

    def _seed_products(
        self, business: Business, categories: dict[str, ProductCategory]
    ) -> list[Product]:
        self.stdout.write("  [7/7] Productos + stock...")

        products: list[Product] = []
        for spec in DEMO_PRODUCTS:
            cat = categories.get(spec["category"])
            product, p_created = Product.objects.get_or_create(
                business=business,
                sku=spec["sku"],
                defaults={
                    "name": spec["name"],
                    "category": cat,
                    "cost": spec["cost"],
                    "price": spec["price"],
                    "is_active": True,
                },
            )
            if not p_created:
                # Keep price/cost current without clobbering other fields
                Product.objects.filter(pk=product.pk).update(
                    name=spec["name"],
                    category=cat,
                    cost=spec["cost"],
                    price=spec["price"],
                    is_active=True,
                )
                product.refresh_from_db()

            ProductStock.objects.get_or_create(
                product=product,
                defaults={"business": business, "quantity": INITIAL_STOCK},
            )

            products.append(product)

        names = [p.name for p in products]
        self.stdout.write(f"     ✓ {len(products)} productos: {', '.join(names)}")
        return products

    # ── Summary ───────────────────────────────────────────────────────────────

    def _print_summary(
        self,
        business: Business,
        owner: User,
        branch: Business,
        register: CashRegister,
        terminal: Terminal,
        cashier: EmployeeProfile,
        cashier2: EmployeeProfile | None,
        products: list[Product],
    ) -> None:
        sep = "─" * 60
        self.stdout.write(f"\n{sep}")
        self.stdout.write(self.style.SUCCESS("✅  seed_pos_demo completado exitosamente"))
        self.stdout.write(sep)

        self.stdout.write(self.style.MIGRATE_HEADING("\n📦  BUSINESS / TENANT"))
        self.stdout.write(f"     name           : {business.name}")
        self.stdout.write(f"     id             : {business.pk}")
        self.stdout.write(f"     slug           : {business.slug}")
        self.stdout.write(f"     service_type   : {business.service_type}")
        self.stdout.write(f"     plan           : {business.subscription.plan}")

        self.stdout.write(self.style.MIGRATE_HEADING("\n👤  OWNER (login en backoffice / gestión comercial)"))
        self.stdout.write(f"     email          : {OWNER_EMAIL}")
        self.stdout.write(f"     password       : {OWNER_PASSWORD}")
        self.stdout.write(f"     membership role: owner")

        self.stdout.write(self.style.MIGRATE_HEADING("\n🏢  BRANCH"))
        self.stdout.write(f"     name           : {branch.name}")
        self.stdout.write(f"     id             : {branch.pk}")

        self.stdout.write(self.style.MIGRATE_HEADING("\n🖥️   TERMINAL / CAJA"))
        self.stdout.write(f"     CashRegister   : {register.name} (id={register.pk})")
        self.stdout.write(f"     Terminal code  : {terminal.code}")
        self.stdout.write(f"     Terminal name  : {terminal.name}")
        self.stdout.write(f"     Terminal id    : {terminal.pk}")

        self.stdout.write(self.style.MIGRATE_HEADING("\n👷  CASHIER — login POS operativo"))
        self.stdout.write(f"     endpoint       : POST /api/v1/auth/employee-login/")
        self.stdout.write(f"     business_id    : {business.pk}")
        self.stdout.write(f"     employee_code  : {CASHIER_CODE}")
        self.stdout.write(f"     pin            : {CASHIER_PIN}")
        self.stdout.write(f"     role_type      : {cashier.role_type}")
        self.stdout.write(f"     must_change_pin: {cashier.must_change_pin}")
        self.stdout.write(f"     employee uuid  : {cashier.pk}")

        if cashier2:
            self.stdout.write(self.style.MIGRATE_HEADING("\n👷  CASHIER 2 (must_change_pin=True)"))
            self.stdout.write(f"     business_id    : {business.pk}")
            self.stdout.write(f"     employee_code  : {CASHIER2_CODE}")
            self.stdout.write(f"     pin            : {CASHIER2_PIN}")
            self.stdout.write(f"     must_change_pin: {cashier2.must_change_pin}")

        self.stdout.write(self.style.MIGRATE_HEADING("\n🛒  CATÁLOGO PRODUCTOS"))
        for p in products:
            self.stdout.write(f"     [{p.sku}] {p.name:<15} $ {p.price:>8.2f}  (stock: {INITIAL_STOCK})")

        self.stdout.write(self.style.MIGRATE_HEADING("\n🔑  CURL DE PRUEBA — employee-login"))
        self.stdout.write(
            f"     curl -s -X POST http://localhost:8000/api/v1/auth/employee-login/ \\\n"
            f"          -H 'Content-Type: application/json' \\\n"
            f"          -d '{{\"business_id\": {business.pk}, "
            f"\"employee_code\": \"{CASHIER_CODE}\", "
            f"\"pin\": \"{CASHIER_PIN}\"}}' | python -m json.tool"
        )

        self.stdout.write(f"\n{sep}\n")

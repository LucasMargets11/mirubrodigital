"""
update_mp_preapproval_plans_payment_methods
============================================
Management command to patch ``payment_methods_allowed`` on existing Mercado Pago
preapproval plans that were created *before* this field was introduced.

Why this is needed
------------------
Plans are ephemeral: each checkout session creates its own ``preapproval_plan``.
Going forward every new plan will include ``payment_methods_allowed`` (via the
updated ``MercadoPagoService.create_preapproval_plan()``).  However, plans that
were already created are stored in Mercado Pago with no payment-method config,
and may keep rejecting prepaid/virtual cards (e.g. Tarjeta Mercado Pago, Astro,
Lemon) for currently-active subscribers.

This command updates those plans so their *next* recurring charge uses the correct
payment-method config.  It does NOT recreate plans, change prices, or affect local
database records.

Usage
-----
Dry run (no MP API calls, just lists plan IDs that would be patched)::

    python manage.py update_mp_preapproval_plans_payment_methods --dry-run

Patch all plans linked to active/linked sessions::

    python manage.py update_mp_preapproval_plans_payment_methods

Patch a specific plan ID::

    python manage.py update_mp_preapproval_plans_payment_methods --plan-id <MP_PLAN_ID>

Safety notes
------------
- The command only PATCHes ``payment_methods_allowed``.  It never changes
  ``auto_recurring`` (price/frequency) or ``reason``.
- A dry run MUST be run first to confirm the scope before touching prod.
- Re-running is safe: MP returns 200 even if the field is already set.
- EC2 / .env files are NOT touched by this command.
"""
from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Patch payment_methods_allowed on existing MP preapproval plans so that "
        "prepaid/virtual cards (e.g. Tarjeta MP, Astro, Lemon) are accepted."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="List plan IDs that would be updated without calling the MP API.",
        )
        parser.add_argument(
            "--plan-id",
            type=str,
            default=None,
            help="Update a single specific MP preapproval plan ID instead of all known ones.",
        )

    def handle(self, *args, **options):
        from apps.billing.models import MpCheckoutSession
        from apps.billing.mp_service import (
            MercadoPagoService,
            get_mp_subscription_payment_methods_allowed,
        )

        dry_run: bool = options["dry_run"]
        single_plan_id: str | None = options["plan_id"]

        if dry_run:
            self.stdout.write(self.style.WARNING("--- DRY RUN — no MP API calls will be made ---"))

        # Collect plan IDs to update.
        if single_plan_id:
            plan_ids = [single_plan_id]
            self.stdout.write(f"Single plan mode: {single_plan_id}")
        else:
            # Find all distinct MP preapproval plan IDs stored in checkout sessions
            # that are in a non-failed, non-expired state (i.e. were actually used).
            exclude_statuses = [
                MpCheckoutSession.Status.FAILED,
                MpCheckoutSession.Status.EXPIRED,
            ]
            plan_ids = list(
                MpCheckoutSession.objects
                .exclude(provider_preapproval_plan_id__isnull=True)
                .exclude(provider_preapproval_plan_id="")
                .exclude(status__in=exclude_statuses)
                .values_list("provider_preapproval_plan_id", flat=True)
                .distinct()
            )
            self.stdout.write(
                f"Found {len(plan_ids)} distinct MP plan ID(s) to patch "
                f"(non-failed, non-expired sessions)."
            )

        if not plan_ids:
            self.stdout.write(self.style.SUCCESS("Nothing to update."))
            return

        for plan_id in plan_ids:
            self.stdout.write(f"  Plan: {plan_id}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDry run complete — {len(plan_ids)} plan(s) listed. "
                    "Re-run without --dry-run to apply."
                )
            )
            return

        # Actual update.
        mp = MercadoPagoService()
        payload = {"payment_methods_allowed": get_mp_subscription_payment_methods_allowed()}

        success_count = 0
        error_count = 0

        for plan_id in plan_ids:
            try:
                mp.update_preapproval_plan(plan_id, payload)
                self.stdout.write(self.style.SUCCESS(f"  [OK]    {plan_id}"))
                success_count += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  [FAIL]  {plan_id} — {exc}"))
                logger.error(
                    "[update_mp_preapproval_plans] Failed to update plan %s: %s", plan_id, exc,
                )
                error_count += 1

        self.stdout.write(
            f"\nDone — {success_count} updated, {error_count} failed out of {len(plan_ids)} total."
        )
        if error_count:
            raise CommandError(
                f"{error_count} plan(s) failed to update. Check logs for details."
            )

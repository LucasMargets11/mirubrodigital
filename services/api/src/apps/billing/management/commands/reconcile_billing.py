"""
Management command: reconcile_billing
--------------------------------------
Manually trigger reconciliation for checkout sessions, subscriptions,
preapproval plans, and invoice events using the Phase 3 reconciliation module.

Usage examples:

    # Reconcile a specific checkout session by UUID
    python manage.py reconcile_billing --checkout-session <uuid>

    # Reconcile a MercadoPago subscription (preapproval) by provider ID
    python manage.py reconcile_billing --subscription 1234567890

    # Reconcile by MP preapproval plan ID
    python manage.py reconcile_billing --preapproval-plan PLAN-1234567890

    # Reconcile a specific authorized payment (invoice event)
    python manage.py reconcile_billing --invoice-event 9876543210

    # Run all available reconciliations for a checkout session
    python manage.py reconcile_billing --checkout-session <uuid> --full

Flags:
    --dry-run   Print what would be done without persisting any changes.
"""
from __future__ import annotations

import json
import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Manually reconcile billing objects against MercadoPago."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            '--checkout-session',
            dest='checkout_session_id',
            metavar='UUID',
            help='UUID of the MpCheckoutSession to reconcile.',
        )
        group.add_argument(
            '--subscription',
            dest='provider_subscription_id',
            metavar='MP_PREAPPROVAL_ID',
            help='MercadoPago preapproval ID of the subscription to reconcile.',
        )
        group.add_argument(
            '--preapproval-plan',
            dest='provider_preapproval_plan_id',
            metavar='MP_PLAN_ID',
            help='MercadoPago preapproval plan ID to reconcile (finds session, then subscription).',
        )
        group.add_argument(
            '--invoice-event',
            dest='provider_authorized_payment_id',
            metavar='MP_AUTH_PAYMENT_ID',
            help='MercadoPago authorized_payment ID to reconcile.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Describe what would happen without persisting changes (not yet fully implemented — logs only).',
        )

    def handle(self, *args, **options):
        from apps.billing.reconciliation import (
            reconcile_checkout_session,
            reconcile_subscription,
            reconcile_by_preapproval_plan,
            reconcile_invoice_event,
        )

        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run is set: no changes will be persisted."))

        result: dict | None = None

        if options.get('checkout_session_id'):
            session_id = options['checkout_session_id']
            self.stdout.write(f"Reconciling checkout session: {session_id}")
            if not dry_run:
                result = reconcile_checkout_session(session_id)

        elif options.get('provider_subscription_id'):
            sub_id = options['provider_subscription_id']
            self.stdout.write(f"Reconciling subscription: {sub_id}")
            if not dry_run:
                result = reconcile_subscription(sub_id)

        elif options.get('provider_preapproval_plan_id'):
            plan_id = options['provider_preapproval_plan_id']
            self.stdout.write(f"Reconciling by preapproval plan: {plan_id}")
            if not dry_run:
                result = reconcile_by_preapproval_plan(plan_id)

        elif options.get('provider_authorized_payment_id'):
            payment_id = options['provider_authorized_payment_id']
            self.stdout.write(f"Reconciling invoice event: {payment_id}")
            if not dry_run:
                result = reconcile_invoice_event(payment_id)

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete — no changes made."))
            return

        if result is None:
            raise CommandError("No reconciliation function was called.")

        if result.get('error'):
            self.stderr.write(self.style.ERROR(f"Reconciliation error: {result['error']}"))
            raise CommandError(result['error'])

        self.stdout.write(
            self.style.SUCCESS(
                "Reconciliation complete:\n" + json.dumps(result, indent=2, default=str)
            )
        )

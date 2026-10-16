"""
Slice 5B.4 — manual replay of Mercado Pago webhook deliveries.

Usage:
    python manage.py retry_mp_webhooks                 # same sweep as the Beat task
    python manage.py retry_mp_webhooks --dry-run       # list eligible deliveries only
    python manage.py retry_mp_webhooks --limit 20
    python manage.py retry_mp_webhooks --id <uuid>     # one FAILED / stuck delivery,
                                                       # ignoring its next_retry_at
    python manage.py retry_mp_webhooks --id <uuid> --revive-dead-letter

Never replays PROCESSED, IGNORED or DUPLICATED deliveries. A DEAD_LETTER
delivery is only replayed with --id and --revive-dead-letter (one extra
attempt; if it fails again it returns to DEAD_LETTER).
"""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.billing.models import WebhookDelivery
from apps.billing.webhook_lifecycle import (
    eligible_for_retry_qs,
    process_delivery,
    retry_due_deliveries,
)


class Command(BaseCommand):
    help = 'Retry eligible Mercado Pago webhook deliveries (FAILED past backoff, or stuck).'

    def add_arguments(self, parser):
        parser.add_argument('--id', dest='delivery_id', help='Retry a single delivery by id.')
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--revive-dead-letter', action='store_true',
            help='With --id: allow one more attempt for a DEAD_LETTER delivery.',
        )

    def handle(self, *args, **opts):
        delivery_id = opts['delivery_id']
        if opts['revive_dead_letter'] and not delivery_id:
            raise CommandError('--revive-dead-letter requires --id.')

        if delivery_id:
            return self._single(delivery_id, opts['dry_run'], opts['revive_dead_letter'])

        if opts['dry_run']:
            rows = eligible_for_retry_qs().order_by('next_retry_at', 'received_at')[:opts['limit']]
            for d in rows:
                self.stdout.write(
                    f'{d.pk} topic={d.topic} resource_id={d.resource_id} flow={d.flow or "-"} '
                    f'status={d.processing_status} attempts={d.attempts} '
                    f'category={d.error_category or "-"}'
                )
            self.stdout.write(f'{len(rows)} eligible delivery(ies).')
            return

        counts = retry_due_deliveries(limit=opts['limit'])
        self.stdout.write(self.style.SUCCESS(f'Retry sweep: {counts}'))

    def _single(self, delivery_id, dry_run, revive):
        try:
            delivery = WebhookDelivery.objects.get(pk=delivery_id)
        except (WebhookDelivery.DoesNotExist, ValueError, ValidationError):
            raise CommandError(f'Delivery {delivery_id} not found.')

        S = WebhookDelivery.ProcessingStatus
        if delivery.processing_status in (S.PROCESSED, S.IGNORED, S.DUPLICATED):
            raise CommandError(
                f'Delivery {delivery_id} is {delivery.processing_status}; replay is not allowed.'
            )
        if delivery.processing_status == S.DEAD_LETTER and not revive:
            raise CommandError(
                f'Delivery {delivery_id} is dead_letter; pass --revive-dead-letter to retry it.'
            )
        if dry_run:
            self.stdout.write(f'Would retry {delivery_id} (status={delivery.processing_status}).')
            return

        result = process_delivery(delivery.pk, revive_dead_letter=revive)
        if result is None:
            self.stdout.write(self.style.WARNING(
                f'Delivery {delivery_id} was not claimed (locked by another worker or in progress).'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f'Delivery {delivery_id} → {result}'))

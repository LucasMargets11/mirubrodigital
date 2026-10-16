# Slice 5B.4 — WebhookDelivery retry lifecycle (persisted routing hints,
# attempt counter, backoff schedule, error category, PROCESSING status).

from django.db import migrations, models


# Slice 5B.4.1 — historic RECEIVED audit (see the 5B.4.1 report):
# Before 5B.4 the `payment` path NEVER updated its delivery row, so a
# `payment` RECEIVED row can mean success, a silent fetch failure, a missing
# record, a swallowed apply error, or a legacy/unresolved no-op — the row
# alone cannot tell. `subscription_*` rows were always finalised by
# dispatch_webhook, so RECEIVED there means the process died mid-request.
# Rule: only rows whose effect is PROVEN applied by a local record become
# IGNORED; everything ambiguous goes to DEAD_LETTER (out of auto-retry,
# visible in the admin alerts, replayable only by explicit operator action).
TIP_FINAL_STATUSES = ('approved', 'rejected', 'cancelled')
LEGACY_NOTE = 'Pre-5B.4 delivery left RECEIVED by the legacy handler. '


def classify_pre_lifecycle_received(apps, schema_editor):
    WebhookDelivery = apps.get_model('billing', 'WebhookDelivery')
    PendingSubscriptionChange = apps.get_model('billing', 'PendingSubscriptionChange')
    TipTransaction = apps.get_model('menu', 'TipTransaction')

    for d in WebhookDelivery.objects.filter(processing_status='received').iterator():
        status, category, note = _classify(d, TipTransaction, PendingSubscriptionChange)
        fields = {'processing_status': status, 'error_category': category}
        if not d.error_message:
            fields['error_message'] = LEGACY_NOTE + note
        WebhookDelivery.objects.filter(pk=d.pk, processing_status='received').update(**fields)


def _classify(d, TipTransaction, PendingSubscriptionChange):
    if not d.signature_valid:
        return 'ignored', 'invalid_signature', 'Signature was not valid.'
    if d.topic in ('subscription_preapproval', 'subscription_authorized_payment'):
        return (
            'dead_letter', 'legacy_unverified',
            'Process died before dispatch; verify, then replay with --revive-dead-letter.',
        )
    if d.topic != 'payment':
        return 'ignored', 'unsupported_topic', 'Topic was never processed.'
    rid = d.resource_id
    if not rid:
        return 'ignored', 'missing_resource_id', 'No payment id.'

    # The legacy handler wrote the payment id onto the local record when it
    # applied a payment: TipTransaction.mp_payment_id / PendingSubscriptionChange.mp_payment_id.
    # Payment ids are scoped per MP account, so an id present on BOTH sides
    # proves nothing and stays ambiguous.
    any_tip = TipTransaction.objects.filter(mp_payment_id=rid).exists()
    any_billing = PendingSubscriptionChange.objects.filter(mp_payment_id=rid).exists()
    tip_final = TipTransaction.objects.filter(mp_payment_id=rid, status__in=TIP_FINAL_STATUSES).exists()
    # Only `completed` proves a Billing apply: legacy `failed` covers both a
    # rejected payment and a swallowed apply error.
    billing_done = PendingSubscriptionChange.objects.filter(mp_payment_id=rid, status='completed').exists()

    if tip_final and not any_billing:
        return 'ignored', 'legacy_applied', 'Tip already in a final state for this payment.'
    if billing_done and not any_tip:
        return 'ignored', 'legacy_applied', 'Billing change already completed for this payment.'
    return (
        'dead_letter', 'legacy_unverified',
        'Effect not provable from local records; verify manually in Mercado Pago.',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0022_add_appointments_service_type'),
        ('menu', '0014_remove_mercadopagoconnection_state_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='webhookdelivery',
            name='attempts',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='webhookdelivery',
            name='error_category',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='webhookdelivery',
            name='flow',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='webhookdelivery',
            name='last_attempt_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='webhookdelivery',
            name='next_retry_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='webhookdelivery',
            name='ref',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AlterField(
            model_name='webhookdelivery',
            name='processing_status',
            field=models.CharField(choices=[('received', 'Recibido'), ('processing', 'Procesando'), ('duplicated', 'Duplicado'), ('ignored', 'Ignorado'), ('processed', 'Procesado'), ('failed', 'Fallido'), ('dead_letter', 'Dead Letter')], default='received', max_length=32),
        ),
        migrations.AddIndex(
            model_name='webhookdelivery',
            index=models.Index(fields=['processing_status', 'next_retry_at'], name='wh_delivery_stat_retry_idx'),
        ),
        migrations.RunPython(classify_pre_lifecycle_received, migrations.RunPython.noop),
    ]

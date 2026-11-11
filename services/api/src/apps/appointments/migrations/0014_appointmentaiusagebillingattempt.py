import django.db.models.deletion
from django.db import migrations, models


ATTEMPT_GUARDS = """
CREATE FUNCTION appt_ai_guard_provider_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    i appointments_appointmentaiusagebillingintent%ROWTYPE;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'AI provider attempt history cannot be deleted' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' THEN
        SELECT * INTO i FROM appointments_appointmentaiusagebillingintent
        WHERE id = NEW.intent_id FOR UPDATE;
        IF NOT FOUND OR i.status <> 'processing' OR i.amount <= 0
           OR i.attempt_token IS DISTINCT FROM NEW.attempt_token
           OR NEW.status <> 'outcome_unknown' OR NEW.failure_code <> 'dispatch_incomplete'
           OR NEW.provider_reference IS NOT NULL THEN
            RAISE EXCEPTION 'AI provider dispatch requires current claim' USING ERRCODE = '23514';
        END IF;
    ELSE
        IF (NEW.id, NEW.intent_id, NEW.attempt_token, NEW.provider, NEW.created_at)
           IS DISTINCT FROM
           (OLD.id, OLD.intent_id, OLD.attempt_token, OLD.provider, OLD.created_at)
           OR OLD.status <> 'outcome_unknown' THEN
            RAISE EXCEPTION 'AI provider attempt identity or final result is immutable'
                USING ERRCODE = '23514';
        END IF;
        IF OLD.provider_reference IS NOT NULL
           AND NEW.provider_reference IS DISTINCT FROM OLD.provider_reference THEN
            RAISE EXCEPTION 'AI provider reference is immutable' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF NEW.provider !~ '^[a-z][a-z0-9_]{0,31}$'
       OR (NEW.provider_reference IS NOT NULL
           AND NEW.provider_reference !~ '^[A-Za-z0-9_-]{1,128}$')
       OR (NEW.status = 'failed' AND NEW.failure_code NOT IN ('declined', 'provider_not_enabled'))
    THEN
        RAISE EXCEPTION 'AI provider result must be normalized' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER appt_ai_provider_attempt_guard
BEFORE INSERT OR UPDATE OR DELETE ON appointments_appointmentaiusagebillingattempt
FOR EACH ROW EXECUTE FUNCTION appt_ai_guard_provider_attempt();
"""

DROP_ATTEMPT_GUARDS = """
DROP TRIGGER appt_ai_provider_attempt_guard ON appointments_appointmentaiusagebillingattempt;
DROP FUNCTION appt_ai_guard_provider_attempt();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0013_ai_usage_billing_intent'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppointmentAIUsageBillingAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attempt_token', models.UUIDField(editable=False, unique=True)),
                ('provider', models.CharField(editable=False, max_length=32)),
                ('provider_reference', models.CharField(blank=True, max_length=128, null=True)),
                ('status', models.CharField(choices=[('succeeded', 'Succeeded'), ('failed', 'Failed'), ('outcome_unknown', 'Outcome_Unknown')], default='outcome_unknown', max_length=15)),
                ('failure_code', models.CharField(blank=True, max_length=32, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('intent', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='provider_attempts', to='appointments.appointmentaiusagebillingintent')),
            ],
            options={
                'constraints': [models.CheckConstraint(check=models.Q(models.Q(('failure_code__isnull', True), ('provider_reference__isnull', False), ('status', 'succeeded')), models.Q(('failure_code__in', ['declined', 'provider_not_enabled', 'provider_error', 'timeout', 'dispatch_incomplete']), ('failure_code__isnull', False), ('status__in', ['failed', 'outcome_unknown'])), _connector='OR'), name='appt_ai_provider_result')],
            },
        ),
        migrations.RunSQL(ATTEMPT_GUARDS, DROP_ATTEMPT_GUARDS),
    ]

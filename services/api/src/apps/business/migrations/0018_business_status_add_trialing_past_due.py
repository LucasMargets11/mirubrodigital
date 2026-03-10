# Wave 3 — Expand Business.status choices to include 'trialing' and 'past_due'.
#
# These values are needed so that Business.status faithfully mirrors
# SubscriptionV2.Status at state-transition time:
#   SubscriptionV2.TRIALING → Business.status = 'trialing'  (onboarding trial)
#   SubscriptionV2.PAST_DUE → Business.status = 'past_due'  (grace period after renewal failure)
#
# Only the choices list is altered — no data is changed. Existing rows that
# have status='onboarding', 'active', 'suspended', or 'canceled' are
# completely unaffected.
#
# Rollback safety: removing these choices later requires no data migration
# as long as no rows carry these values yet.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0017_alter_business_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='business',
            name='status',
            field=models.CharField(
                choices=[
                    ('onboarding', 'Onboarding'),
                    ('trialing',   'Trialing'),
                    ('active',     'Active'),
                    ('past_due',   'Past Due'),
                    ('suspended',  'Suspended'),
                    ('canceled',   'Canceled'),
                    ('pending_activation', 'Pending Activation'),
                ],
                default='active',
                max_length=32,
            ),
        ),
    ]

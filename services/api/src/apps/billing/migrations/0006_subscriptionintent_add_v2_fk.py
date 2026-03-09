# Phase 2B – Add SubscriptionV2 FK to SubscriptionIntent
#
# Enables direct traceability from a signup intent to the canonical SubscriptionV2
# record created alongside it. The field is nullable so existing intents are unaffected.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0005_phase2a_subscriptionv2_billing'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionintent',
            name='subscription_v2',
            field=models.ForeignKey(
                to='billing.SubscriptionV2',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='intents',
            ),
        ),
    ]

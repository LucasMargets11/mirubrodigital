"""
Billing migration 0017 — Add canceled_by FK to SubscriptionV2.

Adds an optional foreign key to the User who performed an administrative
cancellation, enabling the admin panel to display the responsible operator.

This is a minimal, append-only migration that does not touch any other model.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0016_seed_menu_qr_qr_reviews_copy_refresh'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionv2',
            name='canceled_by',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='admin_canceled_subscriptions',
                to=settings.AUTH_USER_MODEL,
                help_text='Platform admin user who performed the administrative cancellation.',
            ),
        ),
    ]

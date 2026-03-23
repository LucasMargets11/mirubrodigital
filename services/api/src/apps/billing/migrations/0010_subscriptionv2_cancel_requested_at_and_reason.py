# Generated manually — adds cancellation tracking fields to SubscriptionV2.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0009_alter_billingevent_error_message_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionv2',
            name='cancel_requested_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text='When the OWNER requested cancellation.',
            ),
        ),
        migrations.AddField(
            model_name='subscriptionv2',
            name='cancel_reason',
            field=models.CharField(
                max_length=255,
                null=True,
                blank=True,
                help_text='Optional reason provided by the user when cancelling.',
            ),
        ),
    ]

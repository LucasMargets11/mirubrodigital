from datetime import timedelta

from django.db import migrations, models


def populate_checkout_expiration(apps, schema_editor):
    checkout_model = apps.get_model('billing', 'AppointmentsCheckout')
    batch = []
    for checkout in checkout_model.objects.only('pk', 'created_at').iterator():
        checkout.expires_at = checkout.created_at + timedelta(hours=24)
        batch.append(checkout)
        if len(batch) == 500:
            checkout_model.objects.bulk_update(batch, ['expires_at'])
            batch.clear()
    if batch:
        checkout_model.objects.bulk_update(batch, ['expires_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0026_appointments_lifecycle'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointmentscheckout',
            name='failure_code',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='appointmentscheckout',
            name='expires_at',
            field=models.DateTimeField(null=True),
        ),
        migrations.RunPython(populate_checkout_expiration, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='appointmentscheckout',
            name='expires_at',
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name='appointmentscheckout',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('linked', 'Linked'),
                    ('active', 'Active'),
                    ('failed', 'Failed'),
                    ('expired', 'Expired'),
                ],
                default='pending',
                max_length=16,
            ),
        ),
    ]

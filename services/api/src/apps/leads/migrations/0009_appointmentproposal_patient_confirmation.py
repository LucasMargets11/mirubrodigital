from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0008_appointmentproposal_converted'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointmentproposal',
            name='confirmation_requested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='appointmentproposal',
            name='confirmation_message_id',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]

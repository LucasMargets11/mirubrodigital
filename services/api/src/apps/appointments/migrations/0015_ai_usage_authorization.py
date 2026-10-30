import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('appointments', '0014_appointmentaiusagebillingattempt'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppointmentAIUsageAuthorization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('interaction_id', models.UUIDField()),
                ('occurred_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='business.business')),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='appointments.appointmentaiusagesession')),
            ],
            options={
                'constraints': [
                    models.UniqueConstraint(fields=('business', 'interaction_id'), name='appt_ai_authorization_event_unique'),
                ],
            },
        ),
    ]

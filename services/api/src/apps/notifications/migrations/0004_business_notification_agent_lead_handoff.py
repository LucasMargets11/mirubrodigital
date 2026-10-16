# AGENT 02B: nuevo kind agent_lead_handoff (solo choices, sin cambio de esquema).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_business_notification_metadata'),
    ]

    operations = [
        migrations.AlterField(
            model_name='businessnotification',
            name='kind',
            field=models.CharField(choices=[('appointment_confirmed', 'Reserva confirmada'), ('appointment_payment_review', 'Pago de reserva requiere revisión'), ('customer_reminder_due', 'Recordatorio de cliente vencido'), ('agent_lead_handoff', 'Consulta del agente requiere atención')], max_length=48),
        ),
    ]

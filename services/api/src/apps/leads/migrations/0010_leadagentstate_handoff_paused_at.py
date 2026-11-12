from django.db import migrations, models


class Migration(migrations.Migration):
    """Aditiva y nullable: los estados existentes quedan en NULL (sin derivación informada)."""

    dependencies = [
        ('leads', '0009_appointmentproposal_patient_confirmation'),
    ]

    operations = [
        migrations.AddField(
            model_name='leadagentstate',
            name='handoff_paused_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

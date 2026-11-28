# PROD-10B2: evidencia de verificación en Meta del canal (campo nullable, sin backfill).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0016_receptionist_config_automatic_attention'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentchannel',
            name='meta_verification',
            field=models.JSONField(blank=True, editable=False, null=True),
        ),
    ]

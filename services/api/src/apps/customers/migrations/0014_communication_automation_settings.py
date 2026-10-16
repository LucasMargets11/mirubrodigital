# CUSTOMER 07D.4A — comunicaciones automáticas por email (apagadas por defecto).
# Solo agrega columnas con DEFAULT en la DB: no reescribe ni borra datos.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0013_customer_communication_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='customercommunicationsettings',
            name='appointment_email_enabled',
            field=models.BooleanField(db_default=False, default=False),
        ),
        migrations.AddField(
            model_name='customercommunicationsettings',
            name='no_show_email_enabled',
            field=models.BooleanField(db_default=False, default=False),
        ),
    ]

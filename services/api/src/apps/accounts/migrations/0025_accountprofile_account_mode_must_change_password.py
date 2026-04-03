from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0024_supportticket_origin'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountprofile',
            name='account_mode',
            field=models.CharField(
                choices=[('owner_managed', 'Administrada por el propietario'), ('personal', 'Personal')],
                default='owner_managed',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='accountprofile',
            name='must_change_password',
            field=models.BooleanField(default=False),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_inventoryimportjob'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockmovement',
            name='reason',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

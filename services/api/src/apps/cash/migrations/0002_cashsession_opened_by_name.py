from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cash', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cashsession',
            name='opened_by_name',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
    ]

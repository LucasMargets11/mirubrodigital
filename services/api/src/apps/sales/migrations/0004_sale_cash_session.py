from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cash', '0002_cashsession_opened_by_name'),
        ('sales', '0003_alter_sale_customer'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='cash_session',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sales',
                to='cash.cashsession',
            ),
        ),
    ]

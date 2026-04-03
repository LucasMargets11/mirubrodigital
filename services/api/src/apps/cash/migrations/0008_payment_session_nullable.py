"""
Make Payment.session nullable so payments can be created for sales
even when no cash session is open (split payment support).
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cash', '0007_alter_cashsession_terminal_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='session',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='payments',
                to='cash.cashsession',
            ),
        ),
    ]

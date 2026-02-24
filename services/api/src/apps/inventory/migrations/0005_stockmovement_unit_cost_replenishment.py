import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0004_stockreplenishment'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockmovement',
            name='unit_cost',
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=19, null=True),
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='replenishment',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stock_movements',
                to='inventory.stockreplenishment',
            ),
        ),
        migrations.AddIndex(
            model_name='stockmovement',
            index=models.Index(fields=['business', 'replenishment'], name='inventory_s_busines_rep_idx'),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0007_order_status_overhaul'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='sold_without_stock',
            field=models.BooleanField(default=False),
        ),
    ]

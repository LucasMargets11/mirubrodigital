# Generated manually for status overhaul
from django.db import migrations, models


STATUS_FORWARD_MAP = {
    'pending': 'open',
    'preparing': 'sent',
    'ready': 'sent',
    'delivered': 'sent',
    'charged': 'paid',
    'canceled': 'cancelled',
}

STATUS_BACKWARD_MAP = {
    'open': 'pending',
    'sent': 'preparing',
    'paid': 'charged',
    'cancelled': 'canceled',
    'draft': 'pending',
}


def forwards_status(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    for old_value, new_value in STATUS_FORWARD_MAP.items():
        Order.objects.filter(status=old_value).update(status=new_value)


def backwards_status(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    for new_value, old_value in STATUS_BACKWARD_MAP.items():
        Order.objects.filter(status=new_value).update(status=old_value)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0006_rename_orders_draf_busines_1a2bc8_idx_orders_orde_busines_9b2f40_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='modifiers',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(forwards_status, backwards_status),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Borrador'),
                    ('open', 'Abierta'),
                    ('sent', 'Enviada a cocina'),
                    ('paid', 'Pagada'),
                    ('cancelled', 'Cancelada'),
                ],
                default='draft',
                max_length=24,
            ),
        ),
    ]

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    """
    Slice 5A — state-only removal of MercadoPagoConnection from apps.menu.

    The model itself, and its underlying `menu_mercadopagoconnection` table,
    now live in apps.merchant_payments (see that app's
    `0001_move_mercadopago_connection.py`). This migration only removes the
    model from menu's migration STATE; it performs no database operation, so
    existing rows/table are untouched.
    """

    dependencies = [
        ('menu', '0013_menucategory_product_category'),
        ('merchant_payments', '0001_move_mercadopago_connection'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='MercadoPagoConnection'),
            ],
            database_operations=[],
        ),
    ]

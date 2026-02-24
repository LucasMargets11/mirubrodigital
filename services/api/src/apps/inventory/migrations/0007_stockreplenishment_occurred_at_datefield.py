from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Migra StockReplenishment.occurred_at de DateTimeField a DateField.

    Motivación: "fecha de compra" es un concepto de fecha pura (sin hora).
    Usar DateField elimina todos los posibles corrimientos de día por UTC.

    La conversión automática de PostgreSQL (TIMESTAMP → DATE) trunca a la
    parte de fecha en UTC. Para registros existentes la diferencia es mínima
    (máximo 3h por el offset de Buenos Aires), y el servidor ya almacenaba
    los datetimes como UTC midnight (que en AR = 21:00 del día anterior),
    por lo que la migración los "corrige" al valor de fecha que el usuario
    efectivamente seleccionó.
    """

    dependencies = [
        ("inventory", "0006_rename_inventory_s_busines_rep_idx_inventory_s_busines_605beb_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stockreplenishment",
            name="occurred_at",
            field=models.DateField(),
        ),
    ]

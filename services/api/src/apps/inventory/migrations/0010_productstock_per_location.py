import django.db.models.deletion
from django.db import migrations, models
from django.db.models import F


def assign_primary_locations(apps, schema_editor):
    database = schema_editor.connection.alias
    ProductStock = apps.get_model("inventory", "ProductStock")
    StockLocation = apps.get_model("inventory", "StockLocation")
    Business = apps.get_model("business", "Business")

    product_mismatches = list(
        ProductStock.objects.using(database)
        .exclude(product__business_id=F("business_id"))
        .values_list("pk", "business_id", "product__business_id")[:10]
    )
    location_mismatches = list(
        ProductStock.objects.using(database)
        .filter(location__isnull=False)
        .exclude(location__business_id=F("business_id"))
        .values_list("pk", "business_id", "location__business_id")[:10]
    )
    if product_mismatches or location_mismatches:
        raise RuntimeError(
            "No se puede asignar ubicaciones de stock: hay saldos cuyo negocio "
            "no coincide con el de su producto o ubicación. Corregí manualmente "
            "estos registros y volvé a ejecutar la migración. "
            f"Producto/negocio (saldo, negocio, negocio_producto): {product_mismatches}; "
            f"ubicación/negocio (saldo, negocio, negocio_ubicacion): {location_mismatches}."
        )

    primary_by_business = {}
    for business_id in Business.objects.using(database).values_list("pk", flat=True).iterator():
        location = (
            StockLocation.objects.using(database)
            .filter(business_id=business_id, is_primary=True)
            .first()
        )
        if location is None:
            base_name = "Local principal"
            name = base_name
            suffix = 2
            while StockLocation.objects.using(database).filter(
                business_id=business_id, name=name
            ).exists():
                name = f"{base_name} ({suffix})"
                suffix += 1
            location = StockLocation.objects.using(database).create(
                business_id=business_id,
                name=name,
                is_primary=True,
                is_active=True,
            )
        elif not location.is_active:
            location.is_active = True
            location.save(update_fields=["is_active", "updated_at"])
        primary_by_business[business_id] = location.pk

    for business_id, location_id in primary_by_business.items():
        ProductStock.objects.using(database).filter(
            business_id=business_id,
            location__isnull=True,
        ).update(location_id=location_id)


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0009_stocklocation_productstock_location_and_more"),
    ]

    operations = [
        migrations.RunPython(assign_primary_locations, migrations.RunPython.noop),
    ]

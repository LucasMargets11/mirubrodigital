import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0010_productstock_per_location"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="productstock",
            name="product_stock_business_product",
        ),
        migrations.AlterField(
            model_name="productstock",
            name="product",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="stock_levels",
                to="catalog.product",
            ),
        ),
        migrations.AlterField(
            model_name="productstock",
            name="location",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="product_stocks",
                to="inventory.stocklocation",
            ),
        ),
        migrations.AddConstraint(
            model_name="productstock",
            constraint=models.UniqueConstraint(
                fields=("product", "location"),
                name="product_stock_product_location",
            ),
        ),
    ]

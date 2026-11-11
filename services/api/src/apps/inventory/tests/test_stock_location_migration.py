from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.business.models import Business
from apps.inventory.models import ProductStock, StockLocation


class ProductStockLocationMigrationTests(TransactionTestCase):
    migrate_from = ("inventory", "0009_stocklocation_productstock_location_and_more")
    migrate_to = ("inventory", "0011_productstock_per_location")

    def setUp(self):
        executor = MigrationExecutor(connection)
        other_app_targets = [
            target
            for target in executor.loader.graph.leaf_nodes()
            if target[0] != "inventory"
        ]
        self.targets_0009 = other_app_targets + [self.migrate_from]
        self.targets_0010 = other_app_targets + [self.migrate_to]
        executor.migrate(self.targets_0009)

        old_apps = executor.loader.project_state(self.targets_0009).apps
        Business = old_apps.get_model("business", "Business")
        Product = old_apps.get_model("catalog", "Product")
        ProductStock = old_apps.get_model("inventory", "ProductStock")
        StockLocation = old_apps.get_model("inventory", "StockLocation")

        self.business_with_stock = Business.objects.create(name="Migración con stock")
        self.business_without_stock = Business.objects.create(name="Migración sin stock")
        self.physical_product = Product.objects.create(
            business=self.business_with_stock,
            name="Pintura ficticia",
        )
        self.zero_product = Product.objects.create(
            business=self.business_with_stock,
            name="Rodillo ficticio",
        )
        self.assigned_product = Product.objects.create(
            business=self.business_with_stock,
            name="Cinta ficticia",
        )
        self.unrelated_business_product = Product.objects.create(
            business=self.business_without_stock,
            name="Producto inconsistente ficticio",
        )

        self.name_collision = StockLocation.objects.create(
            business=self.business_with_stock,
            name="Local principal",
            is_primary=False,
            is_active=True,
        )
        self.assigned_location = StockLocation.objects.create(
            business=self.business_with_stock,
            name="Depósito existente",
            is_primary=False,
            is_active=True,
        )
        self.physical_stock = ProductStock.objects.create(
            business=self.business_with_stock,
            product=self.physical_product,
            quantity=Decimal("13"),
            reserved_quantity=Decimal("2"),
        )
        self.zero_stock = ProductStock.objects.create(
            business=self.business_with_stock,
            product=self.zero_product,
            quantity=Decimal("0"),
            reserved_quantity=Decimal("0"),
        )
        self.assigned_stock = ProductStock.objects.create(
            business=self.business_with_stock,
            product=self.assigned_product,
            location=self.assigned_location,
            quantity=Decimal("7"),
            reserved_quantity=Decimal("1"),
        )
        self.inconsistent_stock = ProductStock.objects.create(
            business=self.business_with_stock,
            product=self.unrelated_business_product,
            quantity=Decimal("4"),
        )

    def tearDown(self):
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
        business_ids = [self.business_with_stock.pk, self.business_without_stock.pk]
        ProductStock.objects.filter(business_id__in=business_ids).delete()
        StockLocation.objects.filter(business_id__in=business_ids).delete()
        Business.objects.filter(pk__in=business_ids).delete()
        super().tearDown()

    def _fixture_teardown(self):
        # Django's TRUNCATE flush omits unmanaged treasury tables that reference businesses.
        pass

    def test_backfills_each_business_and_rejects_inconsistent_rows(self):
        executor = MigrationExecutor(connection)
        OldProductStock = executor.loader.project_state(self.targets_0009).apps.get_model(
            "inventory", "ProductStock"
        )
        OldStockLocation = executor.loader.project_state(self.targets_0009).apps.get_model(
            "inventory", "StockLocation"
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "Corregí manualmente"):
                executor.migrate(self.targets_0010)
        finally:
            physical_after_failure = OldProductStock.objects.get(pk=self.physical_stock.pk)
            zero_after_failure = OldProductStock.objects.get(pk=self.zero_stock.pk)
            self.assertIsNone(physical_after_failure.location_id)
            self.assertIsNone(zero_after_failure.location_id)
            self.assertEqual(physical_after_failure.quantity, Decimal("13"))
            self.assertEqual(physical_after_failure.reserved_quantity, Decimal("2"))
            self.assertEqual(
                OldStockLocation.objects.filter(
                    business_id__in=[
                        self.business_with_stock.pk,
                        self.business_without_stock.pk,
                    ],
                    is_primary=True,
                ).count(),
                0,
            )
            OldProductStock.objects.filter(pk=self.inconsistent_stock.pk).delete()

        executor = MigrationExecutor(connection)
        executor.migrate(self.targets_0010)

        new_apps = executor.loader.project_state(self.targets_0010).apps
        ProductStock = new_apps.get_model("inventory", "ProductStock")
        StockLocation = new_apps.get_model("inventory", "StockLocation")

        primary_with_stock = StockLocation.objects.get(
            business_id=self.business_with_stock.pk,
            is_primary=True,
        )
        primary_without_stock = StockLocation.objects.get(
            business_id=self.business_without_stock.pk,
            is_primary=True,
        )
        self.assertTrue(primary_with_stock.is_active)
        self.assertEqual(primary_with_stock.name, "Local principal (2)")
        self.assertEqual(primary_without_stock.name, "Local principal")
        self.assertEqual(
            StockLocation.objects.get(pk=self.name_collision.pk).name,
            "Local principal",
        )

        physical = ProductStock.objects.get(pk=self.physical_stock.pk)
        zero = ProductStock.objects.get(pk=self.zero_stock.pk)
        assigned = ProductStock.objects.get(pk=self.assigned_stock.pk)
        self.assertEqual(physical.business_id, self.business_with_stock.pk)
        self.assertEqual(physical.product_id, self.physical_product.pk)
        self.assertEqual(physical.location_id, primary_with_stock.pk)
        self.assertEqual(physical.quantity, Decimal("13"))
        self.assertEqual(physical.reserved_quantity, Decimal("2"))
        self.assertEqual(zero.location_id, primary_with_stock.pk)
        self.assertEqual(zero.quantity, Decimal("0"))
        self.assertEqual(zero.reserved_quantity, Decimal("0"))
        self.assertEqual(assigned.location_id, self.assigned_location.pk)
        self.assertEqual(assigned.quantity, Decimal("7"))
        self.assertEqual(assigned.reserved_quantity, Decimal("1"))

        self.assertFalse(
            ProductStock.objects.filter(
                business_id=self.business_without_stock.pk
            ).exists()
        )
        for stock in ProductStock.objects.select_related("location", "product"):
            self.assertEqual(stock.business_id, stock.location.business_id)
            self.assertEqual(stock.business_id, stock.product.business_id)

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from apps.business.models import Business
from apps.catalog.models import Product
from apps.inventory.models import ProductStock, StockLocation, StockMovement
from apps.inventory.services import (
    ensure_stock_record,
    get_primary_stock_location,
    primary_stock_queryset,
    register_stock_movement,
)


class ProductStockLocationTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(name="Stock por ubicación")
        self.product = Product.objects.create(business=self.business, name="Producto ficticio")
        self.primary = get_primary_stock_location(self.business)
        self.depot = StockLocation.objects.create(
            business=self.business,
            name="Depósito",
            is_active=True,
        )

    def test_product_can_have_one_balance_per_location(self):
        primary_stock = ensure_stock_record(self.business, self.product)
        depot_stock = ensure_stock_record(self.business, self.product, self.depot)
        self.assertNotEqual(primary_stock.pk, depot_stock.pk)
        self.assertEqual(primary_stock.location_id, self.primary.pk)
        self.assertEqual(depot_stock.location_id, self.depot.pk)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductStock.objects.create(
                    business=self.business,
                    product=self.product,
                    location=self.primary,
                )

    def test_operational_service_defaults_to_primary_and_validates_explicit_scope(self):
        primary_stock = ensure_stock_record(self.business, self.product)
        primary_stock.quantity = Decimal("3")
        primary_stock.save(update_fields=["quantity", "updated_at"])
        depot_stock = ensure_stock_record(self.business, self.product, self.depot)
        depot_stock.quantity = Decimal("10")
        depot_stock.save(update_fields=["quantity", "updated_at"])

        register_stock_movement(
            business=self.business,
            product=self.product,
            movement_type=StockMovement.MovementType.OUT,
            quantity=Decimal("2"),
        )

        primary_stock.refresh_from_db()
        depot_stock.refresh_from_db()
        self.assertEqual(primary_stock.quantity, Decimal("1"))
        self.assertEqual(depot_stock.quantity, Decimal("10"))
        self.assertEqual(
            list(primary_stock_queryset(self.business).values_list("pk", flat=True)),
            [primary_stock.pk],
        )

        other_business = Business.objects.create(name="Otro negocio")
        other_location = get_primary_stock_location(other_business)
        with self.assertRaises(ValidationError):
            ensure_stock_record(self.business, self.product, other_location)
        with self.assertRaises(ValidationError):
            ensure_stock_record(other_business, self.product)


class PrimaryLocationConcurrencyTests(TransactionTestCase):
    def _fixture_teardown(self):
        # Django's TRUNCATE flush omits unmanaged treasury tables that reference businesses.
        pass

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_first_writes_create_one_primary_location(self):
        self.business = Business.objects.create(name="Alta concurrente")
        products = [
            Product.objects.create(business=self.business, name=f"Producto {index}")
            for index in range(2)
        ]
        business_id = self.business.pk
        barrier = Barrier(2)

        def create_stock(product_id):
            close_old_connections()
            try:
                business = Business.objects.get(pk=business_id)
                product = Product.objects.get(pk=product_id)
                barrier.wait(timeout=10)
                return ensure_stock_record(business, product)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            stocks = list(executor.map(create_stock, [product.pk for product in products]))

        self.assertEqual(
            StockLocation.objects.filter(business=self.business, is_primary=True).count(),
            1,
        )
        self.assertEqual(
            {stock.location_id for stock in stocks},
            {StockLocation.objects.get(business=self.business, is_primary=True).pk},
        )

    def tearDown(self):
        if hasattr(self, "business"):
            ProductStock.objects.filter(business=self.business).delete()
            StockLocation.objects.filter(business=self.business).delete()
            Business.objects.filter(pk=self.business.pk).delete()
        super().tearDown()

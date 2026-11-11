"""
Stock transfer tests (PR3).
Run with: python manage.py test apps.inventory.tests.test_stock_transfers
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import OperationalError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, CommercialSettings, Subscription
from apps.catalog.models import Product
from apps.inventory import services as inventory_services
from apps.sales import serializers as sales_serializers
from apps.sales.models import Sale, SaleItem
from apps.sales.serializers import SaleCreateSerializer
from apps.inventory.models import (
    ProductStock,
    StockLocation,
    StockMovement,
    StockTransfer,
    StockTransferLine,
)
from apps.inventory.services import (
    StockTransferConflict,
    confirm_stock_transfer,
    ensure_stock_record,
    get_primary_stock_location,
    register_stock_movement,
)


def _create_business(name: str) -> Business:
    business = Business.objects.create(name=name)
    Subscription.objects.create(business=business, plan='starter', status='active')
    return business


def _set_stock(business, product, location, quantity, reserved=Decimal('0')):
    stock = ensure_stock_record(business, product, location=location)
    stock.quantity = quantity
    stock.reserved_quantity = reserved
    stock.save(update_fields=['quantity', 'reserved_quantity', 'updated_at'])
    return stock


class StockTransferConfirmationTests(TestCase):
    """Escenarios 1-3: confirmación básica, rollback total y disponible bajo reserva."""

    def setUp(self):
        self.business = _create_business('Pinturería ficticia')
        self.user = get_user_model().objects.create_user(
            username='transfer-user', email='transfer-user@example.com', password='pass1234',
        )
        self.local = get_primary_stock_location(self.business)
        self.depot = StockLocation.objects.create(
            business=self.business, name='Depósito', is_active=True,
        )

    def test_confirm_transfer_moves_stock_and_records_history(self):
        # Escenario 1: Local 3, Depósito 10. Trasladar 2 de Depósito a Local
        # deja 5 y 8 (total 13), con historial de usuario/origen/destino/cantidades.
        product = Product.objects.create(business=self.business, name='Pintura ficticia')
        _set_stock(self.business, product, self.local, Decimal('3'))
        _set_stock(self.business, product, self.depot, Decimal('10'))

        transfer, created = confirm_stock_transfer(
            business=self.business,
            origin_location=self.depot,
            destination_location=self.local,
            lines=[{'product_id': product.pk, 'quantity': Decimal('2')}],
            idempotency_key='transfer-1',
            created_by=self.user,
        )

        self.assertTrue(created)
        self.assertEqual(transfer.business_id, self.business.pk)
        self.assertEqual(transfer.origin_location_id, self.depot.pk)
        self.assertEqual(transfer.destination_location_id, self.local.pk)
        self.assertEqual(transfer.created_by_id, self.user.pk)

        local_stock = ProductStock.objects.get(product=product, location=self.local)
        depot_stock = ProductStock.objects.get(product=product, location=self.depot)
        self.assertEqual(local_stock.quantity, Decimal('5'))
        self.assertEqual(depot_stock.quantity, Decimal('8'))
        self.assertEqual(local_stock.quantity + depot_stock.quantity, Decimal('13'))

        lines = list(transfer.lines.all())
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line.product_id, product.pk)
        self.assertEqual(line.quantity, Decimal('2'))

        out_movement = line.out_movement
        in_movement = line.in_movement
        self.assertEqual(out_movement.movement_type, StockMovement.MovementType.OUT)
        self.assertEqual(out_movement.quantity, Decimal('2'))
        self.assertEqual(out_movement.location_id, self.depot.pk)
        self.assertEqual(out_movement.transfer_id, transfer.pk)
        self.assertEqual(out_movement.created_by_id, self.user.pk)
        self.assertEqual(in_movement.movement_type, StockMovement.MovementType.IN)
        self.assertEqual(in_movement.quantity, Decimal('2'))
        self.assertEqual(in_movement.location_id, self.local.pk)
        self.assertEqual(in_movement.transfer_id, transfer.pk)
        self.assertEqual(in_movement.created_by_id, self.user.pk)

    def test_second_invalid_line_rolls_back_everything(self):
        # Escenario 2: un segundo renglón inválido (stock insuficiente) revierte
        # todo: ni movimientos, ni saldos nuevos en destino, ni traslado confirmado.
        product_a = Product.objects.create(business=self.business, name='Producto A')
        product_b = Product.objects.create(business=self.business, name='Producto B')
        _set_stock(self.business, product_a, self.depot, Decimal('10'))
        _set_stock(self.business, product_b, self.depot, Decimal('1'))
        # Ninguno de los dos productos tiene saldo en el destino todavía.

        with self.assertRaises(ValidationError):
            confirm_stock_transfer(
                business=self.business,
                origin_location=self.depot,
                destination_location=self.local,
                lines=[
                    {'product_id': product_a.pk, 'quantity': Decimal('3')},
                    {'product_id': product_b.pk, 'quantity': Decimal('5')},
                ],
                idempotency_key='transfer-rollback',
                created_by=self.user,
            )

        self.assertFalse(StockTransfer.objects.filter(business=self.business).exists())
        self.assertFalse(
            StockTransferLine.objects.filter(transfer__business=self.business).exists()
        )
        self.assertFalse(
            StockMovement.objects.filter(business=self.business, reason='transfer').exists()
        )
        self.assertEqual(
            ProductStock.objects.get(product=product_a, location=self.depot).quantity,
            Decimal('10'),
        )
        self.assertEqual(
            ProductStock.objects.get(product=product_b, location=self.depot).quantity,
            Decimal('1'),
        )
        # Ningún saldo de destino quedó creado por el intento fallido.
        self.assertFalse(
            ProductStock.objects.filter(product=product_a, location=self.local).exists()
        )
        self.assertFalse(
            ProductStock.objects.filter(product=product_b, location=self.local).exists()
        )

    def test_available_quantity_accounts_for_reserved_stock(self):
        # Escenario 3: origen con 10 físicas y 9 reservadas. Trasladar 2 falla;
        # trasladar 1 deja 9 físicas y 9 reservadas en origen.
        product = Product.objects.create(business=self.business, name='Producto reservado')
        _set_stock(self.business, product, self.depot, Decimal('10'), reserved=Decimal('9'))

        with self.assertRaises(ValidationError):
            confirm_stock_transfer(
                business=self.business,
                origin_location=self.depot,
                destination_location=self.local,
                lines=[{'product_id': product.pk, 'quantity': Decimal('2')}],
                idempotency_key='transfer-insufficient',
                created_by=self.user,
            )
        origin_stock = ProductStock.objects.get(product=product, location=self.depot)
        self.assertEqual(origin_stock.quantity, Decimal('10'))
        self.assertEqual(origin_stock.reserved_quantity, Decimal('9'))

        transfer, created = confirm_stock_transfer(
            business=self.business,
            origin_location=self.depot,
            destination_location=self.local,
            lines=[{'product_id': product.pk, 'quantity': Decimal('1')}],
            idempotency_key='transfer-exact',
            created_by=self.user,
        )
        self.assertTrue(created)
        origin_stock.refresh_from_db()
        self.assertEqual(origin_stock.quantity, Decimal('9'))
        self.assertEqual(origin_stock.reserved_quantity, Decimal('9'))


class StockTransferValidationTests(TestCase):
    """Rechazos de forma: ubicaciones, productos, renglones y cantidades."""

    def setUp(self):
        self.business = _create_business('Validaciones ficticias')
        self.user = get_user_model().objects.create_user(
            username='validation-user', email='validation-user@example.com', password='pass1234',
        )
        self.local = get_primary_stock_location(self.business)
        self.depot = StockLocation.objects.create(
            business=self.business, name='Depósito', is_active=True,
        )
        self.product = Product.objects.create(business=self.business, name='Producto validado')
        _set_stock(self.business, self.product, self.depot, Decimal('10'))

    def _confirm(self, **overrides):
        params = dict(
            business=self.business,
            origin_location=self.depot,
            destination_location=self.local,
            lines=[{'product_id': self.product.pk, 'quantity': Decimal('1')}],
            idempotency_key='validation-key',
            created_by=self.user,
        )
        params.update(overrides)
        return confirm_stock_transfer(**params)

    def test_rejects_same_origin_and_destination(self):
        with self.assertRaises(ValidationError):
            self._confirm(destination_location=self.depot)

    def test_rejects_inactive_destination(self):
        self.local.is_active = False
        self.local.save(update_fields=['is_active'])
        with self.assertRaises(ValidationError):
            self._confirm()

    def test_rejects_foreign_location(self):
        other_business = _create_business('Otro negocio ubicación')
        foreign_location = get_primary_stock_location(other_business)
        with self.assertRaises(ValidationError):
            self._confirm(destination_location=foreign_location)

    def test_rejects_foreign_product(self):
        other_business = _create_business('Otro negocio producto')
        foreign_product = Product.objects.create(business=other_business, name='Producto ajeno')
        with self.assertRaises(ValidationError):
            self._confirm(lines=[{'product_id': foreign_product.pk, 'quantity': Decimal('1')}])

    def test_rejects_empty_transfer(self):
        with self.assertRaises(ValidationError):
            self._confirm(lines=[])

    def test_rejects_duplicate_product_lines(self):
        with self.assertRaises(ValidationError):
            self._confirm(lines=[
                {'product_id': self.product.pk, 'quantity': Decimal('1')},
                {'product_id': self.product.pk, 'quantity': Decimal('2')},
            ])

    def test_rejects_non_positive_quantity(self):
        with self.assertRaises(ValidationError):
            self._confirm(lines=[{'product_id': self.product.pk, 'quantity': Decimal('0')}])
        with self.assertRaises(ValidationError):
            self._confirm(lines=[{'product_id': self.product.pk, 'quantity': Decimal('-1')}])


class StockTransferIdempotencyTests(TestCase):
    """Escenario 4 (secuencial): misma clave + mismo/ distinto contenido."""

    def setUp(self):
        self.business = _create_business('Idempotencia ficticia')
        self.user = get_user_model().objects.create_user(
            username='idem-user', email='idem-user@example.com', password='pass1234',
        )
        self.local = get_primary_stock_location(self.business)
        self.depot = StockLocation.objects.create(
            business=self.business, name='Depósito', is_active=True,
        )
        self.product = Product.objects.create(business=self.business, name='Producto idempotente')
        _set_stock(self.business, self.product, self.depot, Decimal('10'))

    def _confirm(self, key, quantity=Decimal('2')):
        return confirm_stock_transfer(
            business=self.business,
            origin_location=self.depot,
            destination_location=self.local,
            lines=[{'product_id': self.product.pk, 'quantity': quantity}],
            idempotency_key=key,
            created_by=self.user,
        )

    def test_same_key_same_content_returns_original_transfer(self):
        transfer1, created1 = self._confirm('idem-key-1')
        transfer2, created2 = self._confirm('idem-key-1')

        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(transfer1.pk, transfer2.pk)
        self.assertEqual(StockTransfer.objects.filter(business=self.business).count(), 1)
        self.assertEqual(
            StockMovement.objects.filter(business=self.business, reason='transfer').count(), 2,
        )
        local_stock = ProductStock.objects.get(product=self.product, location=self.local)
        depot_stock = ProductStock.objects.get(product=self.product, location=self.depot)
        self.assertEqual(local_stock.quantity, Decimal('2'))
        self.assertEqual(depot_stock.quantity, Decimal('8'))

    def test_same_key_different_content_raises_conflict(self):
        self._confirm('idem-key-2', quantity=Decimal('2'))

        with self.assertRaises(StockTransferConflict):
            self._confirm('idem-key-2', quantity=Decimal('3'))

        # Solo queda el traslado/movimientos/saldo del primer intento.
        self.assertEqual(StockTransfer.objects.filter(business=self.business).count(), 1)
        self.assertEqual(
            StockMovement.objects.filter(business=self.business, reason='transfer').count(), 2,
        )
        local_stock = ProductStock.objects.get(product=self.product, location=self.local)
        self.assertEqual(local_stock.quantity, Decimal('2'))


class StockTransferConcurrencyTests(TransactionTestCase):
    """Escenario 4 (concurrente) y escenario 5: conexiones separadas por hilo."""

    def _fixture_teardown(self):
        # Mismo workaround que PR2: el flush por TRUNCATE falla contra tablas
        # unmanaged de treasury referenciadas por Business.
        pass

    def setUp(self):
        self.businesses_to_clean = []

    def tearDown(self):
        for business in self.businesses_to_clean:
            # Orden obligatorio: StockMovement.transfer y
            # StockTransferLine.out_movement/in_movement usan PROTECT para
            # blindar el historial. Hay que soltar primero los renglones
            # (referencian movimientos), luego los movimientos (referencian
            # el traslado) y recién entonces el traslado.
            StockTransferLine.objects.filter(transfer__business=business).delete()
            StockMovement.objects.filter(business=business).delete()
            StockTransfer.objects.filter(business=business).delete()
            ProductStock.objects.filter(business=business).delete()
            StockLocation.objects.filter(business=business).delete()
            Product.objects.filter(business=business).delete()
            Business.objects.filter(pk=business.pk).delete()
        # _fixture_teardown no hace flush: borrar también los usuarios
        # ficticios para que la clase sea repetible con --keepdb.
        get_user_model().objects.filter(username__in=[
            'concurrent-user', 'race-user', 'opposite-user', 'dest-race-user',
        ]).delete()
        super().tearDown()

    def _make_business(self, name):
        business = _create_business(name)
        self.businesses_to_clean.append(business)
        return business

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_identical_retries_create_a_single_transfer(self):
        business = self._make_business('Reintento concurrente')
        user = get_user_model().objects.create_user(
            username='concurrent-user', email='concurrent-user@example.com', password='pass1234',
        )
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        product = Product.objects.create(business=business, name='Producto concurrente')
        _set_stock(business, product, depot, Decimal('10'))

        business_id, user_id, local_id, depot_id, product_id = (
            business.pk, user.pk, local.pk, depot.pk, product.pk,
        )
        barrier = Barrier(2)

        def attempt(_):
            close_old_connections()
            try:
                biz = Business.objects.get(pk=business_id)
                usr = get_user_model().objects.get(pk=user_id)
                orig = StockLocation.objects.get(pk=depot_id)
                dest = StockLocation.objects.get(pk=local_id)
                prod = Product.objects.get(pk=product_id)
                barrier.wait(timeout=10)
                return confirm_stock_transfer(
                    business=biz,
                    origin_location=orig,
                    destination_location=dest,
                    lines=[{'product_id': prod.pk, 'quantity': Decimal('2')}],
                    idempotency_key='same-key-concurrent',
                    created_by=usr,
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, range(2)))

        transfer_ids = {result[0].pk for result in results}
        self.assertEqual(len(transfer_ids), 1)
        self.assertEqual(StockTransfer.objects.filter(business_id=business_id).count(), 1)
        self.assertEqual(
            StockMovement.objects.filter(business_id=business_id, reason='transfer').count(), 2,
        )
        local_stock = ProductStock.objects.get(product_id=product_id, location_id=local_id)
        depot_stock = ProductStock.objects.get(product_id=product_id, location_id=depot_id)
        self.assertEqual(local_stock.quantity, Decimal('2'))
        self.assertEqual(depot_stock.quantity, Decimal('8'))

    @skipUnlessDBFeature('has_select_for_update')
    def test_sale_and_transfer_compete_for_last_units_only_one_succeeds(self):
        business = self._make_business('Competencia venta y traslado')
        user = get_user_model().objects.create_user(
            username='race-user', email='race-user@example.com', password='pass1234',
        )
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        product = Product.objects.create(business=business, name='Producto disputado')
        _set_stock(business, product, local, Decimal('1'))  # última unidad en Local
        _set_stock(business, product, depot, Decimal('10'))

        business_id, user_id, local_id, depot_id, product_id = (
            business.pk, user.pk, local.pk, depot.pk, product.pk,
        )
        barrier = Barrier(2)
        results = {}

        def run_sale():
            close_old_connections()
            try:
                biz = Business.objects.get(pk=business_id)
                prod = Product.objects.get(pk=product_id)
                usr = get_user_model().objects.get(pk=user_id)
                barrier.wait(timeout=10)
                try:
                    register_stock_movement(
                        business=biz,
                        product=prod,
                        movement_type=StockMovement.MovementType.OUT,
                        quantity=Decimal('1'),
                        created_by=usr,
                    )
                    results['sale'] = 'ok'
                except ValidationError:
                    results['sale'] = 'blocked'
            finally:
                close_old_connections()

        def run_transfer():
            close_old_connections()
            try:
                biz = Business.objects.get(pk=business_id)
                orig = StockLocation.objects.get(pk=local_id)
                dest = StockLocation.objects.get(pk=depot_id)
                prod = Product.objects.get(pk=product_id)
                usr = get_user_model().objects.get(pk=user_id)
                barrier.wait(timeout=10)
                try:
                    confirm_stock_transfer(
                        business=biz,
                        origin_location=orig,
                        destination_location=dest,
                        lines=[{'product_id': prod.pk, 'quantity': Decimal('1')}],
                        idempotency_key='race-transfer',
                        created_by=usr,
                    )
                    results['transfer'] = 'ok'
                except ValidationError:
                    results['transfer'] = 'blocked'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run_sale), executor.submit(run_transfer)]
            for future in futures:
                future.result(timeout=15)

        self.assertEqual(
            sum(1 for v in (results['sale'], results['transfer']) if v == 'ok'), 1,
        )
        local_stock = ProductStock.objects.get(product_id=product_id, location_id=local_id)
        self.assertEqual(local_stock.quantity, Decimal('0'))
        depot_stock = ProductStock.objects.get(product_id=product_id, location_id=depot_id)
        if results['transfer'] == 'ok':
            self.assertEqual(depot_stock.quantity, Decimal('11'))
        else:
            self.assertEqual(depot_stock.quantity, Decimal('10'))

    @skipUnlessDBFeature('has_select_for_update')
    def test_opposite_direction_transfers_do_not_deadlock(self):
        business = self._make_business('Traslados opuestos')
        user = get_user_model().objects.create_user(
            username='opposite-user', email='opposite-user@example.com', password='pass1234',
        )
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        product = Product.objects.create(business=business, name='Producto bidireccional')
        _set_stock(business, product, local, Decimal('5'))
        _set_stock(business, product, depot, Decimal('5'))

        business_id, user_id, local_id, depot_id, product_id = (
            business.pk, user.pk, local.pk, depot.pk, product.pk,
        )
        barrier = Barrier(2)

        def run(direction):
            close_old_connections()
            try:
                biz = Business.objects.get(pk=business_id)
                usr = get_user_model().objects.get(pk=user_id)
                prod = Product.objects.get(pk=product_id)
                if direction == 'local_to_depot':
                    orig = StockLocation.objects.get(pk=local_id)
                    dest = StockLocation.objects.get(pk=depot_id)
                    key = 'opp-local-to-depot'
                else:
                    orig = StockLocation.objects.get(pk=depot_id)
                    dest = StockLocation.objects.get(pk=local_id)
                    key = 'opp-depot-to-local'
                barrier.wait(timeout=10)
                return confirm_stock_transfer(
                    business=biz,
                    origin_location=orig,
                    destination_location=dest,
                    lines=[{'product_id': prod.pk, 'quantity': Decimal('1')}],
                    idempotency_key=key,
                    created_by=usr,
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(run, 'local_to_depot'),
                executor.submit(run, 'depot_to_local'),
            ]
            results = [future.result(timeout=15) for future in futures]

        self.assertEqual(len(results), 2)
        self.assertEqual(StockTransfer.objects.filter(business_id=business_id).count(), 2)
        local_stock = ProductStock.objects.get(product_id=product_id, location_id=local_id)
        depot_stock = ProductStock.objects.get(product_id=product_id, location_id=depot_id)
        # 5 - 1 (enviada a depósito) + 1 (recibida de depósito) = 5, simétrico.
        self.assertEqual(local_stock.quantity, Decimal('5'))
        self.assertEqual(depot_stock.quantity, Decimal('5'))

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_transfers_create_missing_destination_balance_safely(self):
        business = self._make_business('Creación de saldo destino concurrente')
        user = get_user_model().objects.create_user(
            username='dest-race-user', email='dest-race-user@example.com', password='pass1234',
        )
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        product = Product.objects.create(business=business, name='Producto destino concurrente')
        _set_stock(business, product, local, Decimal('5'))
        # Depósito todavía no tiene fila de ProductStock para este producto.

        business_id, user_id, local_id, depot_id, product_id = (
            business.pk, user.pk, local.pk, depot.pk, product.pk,
        )
        barrier = Barrier(2)

        def run(key_suffix):
            close_old_connections()
            try:
                biz = Business.objects.get(pk=business_id)
                usr = get_user_model().objects.get(pk=user_id)
                orig = StockLocation.objects.get(pk=local_id)
                dest = StockLocation.objects.get(pk=depot_id)
                prod = Product.objects.get(pk=product_id)
                barrier.wait(timeout=10)
                return confirm_stock_transfer(
                    business=biz,
                    origin_location=orig,
                    destination_location=dest,
                    lines=[{'product_id': prod.pk, 'quantity': Decimal('1')}],
                    idempotency_key=f'dest-race-{key_suffix}',
                    created_by=usr,
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run, ['a', 'b']))

        self.assertEqual(len(results), 2)
        self.assertEqual(
            ProductStock.objects.filter(product_id=product_id, location_id=depot_id).count(), 1,
        )
        local_stock = ProductStock.objects.get(product_id=product_id, location_id=local_id)
        depot_stock = ProductStock.objects.get(product_id=product_id, location_id=depot_id)
        self.assertEqual(local_stock.quantity, Decimal('3'))
        self.assertEqual(depot_stock.quantity, Decimal('2'))


@skipUnless(connection.vendor == 'postgresql', 'Requiere PostgreSQL: usa pg_blocking_pids y detección de deadlocks.')
class SaleVersusTransferLockOrderTests(TransactionTestCase):
    """
    Venta y traslado saliente desde Local principal con dos productos en
    orden comercial inverso, en conexiones separadas y transacciones
    solapadas a propósito:

      1. El traslado toma su primer lock de saldo en Local principal y se
         detiene adentro de su transacción.
      2. Recién entonces arranca la venta. La conexión de control verifica
         con pg_blocking_pids que la venta quedó esperando un lock que
         retiene el traslado (solapamiento demostrado, no ejecución en
         secuencia).
      3. El traslado continúa con el segundo producto.

    Si la venta bloqueara sus saldos en orden comercial (B, A) mientras el
    traslado los bloquea por product_id (A, B), el paso 3 cierra un ciclo y
    PostgreSQL aborta una de las dos con deadlock (o vence lock_timeout).
    La prueba falla en ese caso en vez de aceptar que ambas terminen.
    """

    LOCK_TIMEOUT = '8s'
    WAIT_SECONDS = 15

    def _fixture_teardown(self):
        # Mismo workaround que StockTransferConcurrencyTests.
        pass

    def setUp(self):
        self.businesses_to_clean = []

    def tearDown(self):
        for business in self.businesses_to_clean:
            SaleItem.objects.filter(sale__business=business).delete()
            Sale.objects.filter(business=business).delete()
            StockTransferLine.objects.filter(transfer__business=business).delete()
            StockMovement.objects.filter(business=business).delete()
            StockTransfer.objects.filter(business=business).delete()
            ProductStock.objects.filter(business=business).delete()
            StockLocation.objects.filter(business=business).delete()
            Product.objects.filter(business=business).delete()
            Business.objects.filter(pk=business.pk).delete()
        get_user_model().objects.filter(username='lock-order-user').delete()
        super().tearDown()

    def _run_overlapped(self, *, local_qty, sale_qty, transfer_qty):
        business = _create_business('Venta vs traslado ficticio')
        self.businesses_to_clean.append(business)
        commercial = CommercialSettings.objects.for_business(business)
        commercial.block_sales_if_no_open_cash_session = False
        commercial.allow_sell_without_stock = False
        commercial.save()
        user = get_user_model().objects.create_user(
            username='lock-order-user', email='lock-order-user@example.com', password='pass1234',
        )
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        first = Product.objects.create(business=business, name='Producto X', price=Decimal('10'))
        second = Product.objects.create(business=business, name='Producto Y', price=Decimal('10'))
        low, high = sorted([first, second], key=lambda p: str(p.pk))
        for product in (low, high):
            _set_stock(business, product, local, local_qty)
            _set_stock(business, product, depot, Decimal('0'))

        ids = {
            'business': business.pk, 'user': user.pk, 'local': local.pk,
            'depot': depot.pk, 'low': low.pk, 'high': high.pk,
        }
        labels = {str(low.pk): 'A', str(high.pk): 'B', str(local.pk): 'local', str(depot.pk): 'deposito'}

        tag = threading.local()
        lock_log = []
        log_lock = threading.Lock()
        pids = {}
        results = {}
        transfer_holds_first_lock = threading.Event()
        sale_is_blocked = threading.Event()
        overlap = {'proved': False, 'blockers': None}
        original_ensure = inventory_services.ensure_stock_record

        def traced_ensure(biz, product, location=None):
            stock = original_ensure(biz, product, location=location)
            who = getattr(tag, 'name', None)
            if who is None:
                return stock
            entry = (who, labels[str(stock.product_id)], labels[str(stock.location_id)])
            with log_lock:
                if entry not in lock_log:
                    lock_log.append(entry)
            if who == 'transfer' and entry[2] == 'local' and not transfer_holds_first_lock.is_set():
                # Primer saldo de Local principal bloqueado por el traslado
                # (según el orden de UUIDs puede venir después de su saldo
                # en Depósito): retener el lock adentro de la transacción
                # hasta ver a la venta esperándolo.
                transfer_holds_first_lock.set()
                sale_is_blocked.wait(self.WAIT_SECONDS)
            return stock

        def prepare(name):
            close_old_connections()
            tag.name = name
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_backend_pid()')
                pids[name] = cursor.fetchone()[0]
                cursor.execute(f"SET lock_timeout = '{self.LOCK_TIMEOUT}'")

        def classify(exc):
            cause = getattr(exc, '__cause__', None)
            sqlstate = getattr(cause, 'sqlstate', None)
            if sqlstate == '40P01':
                return 'deadlock'
            if sqlstate == '55P03':
                return 'lock_timeout'
            return f'db_error:{sqlstate}'

        def run_transfer():
            prepare('transfer')
            try:
                confirm_stock_transfer(
                    business=Business.objects.get(pk=ids['business']),
                    origin_location=StockLocation.objects.get(pk=ids['local']),
                    destination_location=StockLocation.objects.get(pk=ids['depot']),
                    lines=[
                        {'product_id': ids['low'], 'quantity': transfer_qty},
                        {'product_id': ids['high'], 'quantity': transfer_qty},
                    ],
                    idempotency_key='lock-order-transfer',
                    created_by=get_user_model().objects.get(pk=ids['user']),
                )
                results['transfer'] = 'ok'
            except ValidationError:
                results['transfer'] = 'rejected'
            except OperationalError as exc:
                results['transfer'] = classify(exc)
            finally:
                tag.name = None
                close_old_connections()

        def run_sale():
            prepare('sale')
            try:
                if not transfer_holds_first_lock.wait(self.WAIT_SECONDS):
                    results['sale'] = 'transfer_never_locked'
                    return
                biz = Business.objects.get(pk=ids['business'])
                usr = get_user_model().objects.get(pk=ids['user'])
                serializer = SaleCreateSerializer(
                    data={
                        # Orden comercial inverso al del traslado: B, A.
                        'items': [
                            {'product_id': str(ids['high']), 'quantity': str(sale_qty)},
                            {'product_id': str(ids['low']), 'quantity': str(sale_qty)},
                        ],
                    },
                    context={'business': biz, 'request': SimpleNamespace(user=usr)},
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()
                results['sale'] = 'ok'
            except DRFValidationError as exc:
                results['sale'] = 'rejected'
                results['sale_error'] = exc.detail
            except OperationalError as exc:
                results['sale'] = classify(exc)
            finally:
                tag.name = None
                close_old_connections()

        with patch.object(inventory_services, 'ensure_stock_record', traced_ensure), \
                patch.object(sales_serializers, 'ensure_stock_record', traced_ensure):
            with ThreadPoolExecutor(max_workers=2) as executor:
                transfer_future = executor.submit(run_transfer)
                sale_future = executor.submit(run_sale)
                try:
                    self.assertTrue(
                        transfer_holds_first_lock.wait(self.WAIT_SECONDS),
                        'El traslado nunca tomó su primer lock.',
                    )
                    deadline = time.monotonic() + self.WAIT_SECONDS
                    while time.monotonic() < deadline and not overlap['proved']:
                        sale_pid = pids.get('sale')
                        if sale_pid is not None:
                            with connection.cursor() as cursor:
                                cursor.execute('SELECT pg_blocking_pids(%s)', [sale_pid])
                                blockers = cursor.fetchone()[0] or []
                            if pids['transfer'] in blockers:
                                overlap['proved'] = True
                                overlap['blockers'] = list(blockers)
                                break
                        time.sleep(0.05)
                finally:
                    # Siempre liberar al traslado para no colgar la prueba.
                    sale_is_blocked.set()
                transfer_future.result(timeout=self.WAIT_SECONDS * 2)
                sale_future.result(timeout=self.WAIT_SECONDS * 2)

        return {
            'ids': ids,
            'results': results,
            'lock_log': lock_log,
            'overlap': overlap,
            'pids': pids,
        }

    def _balance(self, product_id, location_id):
        return ProductStock.objects.get(product_id=product_id, location_id=location_id).quantity

    def _assert_overlap_without_cycle(self, run):
        self.assertTrue(
            run['overlap']['proved'],
            f"La venta nunca esperó un lock del traslado: no hubo solapamiento. {run}",
        )
        for name in ('transfer', 'sale'):
            self.assertNotIn(
                run['results'].get(name), ('deadlock', 'lock_timeout'),
                f"{name} abortada por ciclo de locks: {run}",
            )
        transfer_order = [e[1:] for e in run['lock_log'] if e[0] == 'transfer']
        sale_order = [e[1:] for e in run['lock_log'] if e[0] == 'sale']
        self.assertEqual(
            transfer_order,
            [('A', 'deposito'), ('A', 'local'), ('B', 'deposito'), ('B', 'local')]
            if str(run['ids']['depot']) < str(run['ids']['local'])
            else [('A', 'local'), ('A', 'deposito'), ('B', 'local'), ('B', 'deposito')],
        )
        # La venta bloquea sus saldos en el mismo orden global (A antes que B)
        # aunque sus renglones comerciales vengan B, A.
        self.assertEqual(sale_order, [('A', 'local'), ('B', 'local')])

    @skipUnlessDBFeature('has_select_for_update')
    def test_sale_and_transfer_with_inverse_line_order_do_not_deadlock(self):
        run = self._run_overlapped(
            local_qty=Decimal('5'), sale_qty=Decimal('1'), transfer_qty=Decimal('2'),
        )
        self._assert_overlap_without_cycle(run)
        self.assertEqual(run['results'], {'transfer': 'ok', 'sale': 'ok'}, run)

        ids = run['ids']
        for product_id in (ids['low'], ids['high']):
            self.assertEqual(self._balance(product_id, ids['local']), Decimal('2'))
            self.assertEqual(self._balance(product_id, ids['depot']), Decimal('2'))

        sale = Sale.objects.get(business_id=ids['business'])
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertEqual(
            sorted(str(pid) for pid in sale.items.values_list('product_id', flat=True)),
            sorted([str(ids['low']), str(ids['high'])]),
        )
        sale_movements = StockMovement.objects.filter(
            business_id=ids['business'], transfer__isnull=True, note=f'Venta #{sale.number}',
        )
        self.assertEqual(sale_movements.count(), 2)
        self.assertEqual(set(sale_movements.values_list('location_id', flat=True)), {ids['local']})
        transfer = StockTransfer.objects.get(business_id=ids['business'])
        self.assertEqual(transfer.movements.count(), 4)
        self.assertEqual(transfer.lines.count(), 2)

    @skipUnlessDBFeature('has_select_for_update')
    def test_overlapped_sale_rejected_for_stock_has_no_partial_effects(self):
        # Local 3 por producto: el traslado (2 c/u) gana el primer lock y deja
        # 1; la venta (2 c/u) espera, relee el saldo ya confirmado y se
        # rechaza por stock insuficiente sin dejar venta ni movimientos.
        run = self._run_overlapped(
            local_qty=Decimal('3'), sale_qty=Decimal('2'), transfer_qty=Decimal('2'),
        )
        self._assert_overlap_without_cycle(run)
        self.assertEqual(run['results'].get('transfer'), 'ok', run)
        self.assertEqual(run['results'].get('sale'), 'rejected', run)
        self.assertEqual(run['results']['sale_error']['error']['code'], 'OUT_OF_STOCK')

        ids = run['ids']
        for product_id in (ids['low'], ids['high']):
            self.assertEqual(self._balance(product_id, ids['local']), Decimal('1'))
            self.assertEqual(self._balance(product_id, ids['depot']), Decimal('2'))
        self.assertFalse(Sale.objects.filter(business_id=ids['business']).exists())
        self.assertFalse(SaleItem.objects.filter(sale__business_id=ids['business']).exists())
        self.assertEqual(
            StockMovement.objects.filter(business_id=ids['business'], transfer__isnull=True).count(), 0,
        )
        self.assertEqual(
            StockMovement.objects.filter(business_id=ids['business'], transfer__isnull=False).count(), 4,
        )


class StockTransferAPITests(APITestCase):
    """Escenario 6: contrato HTTP, permisos y aislamiento entre negocios."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='transfer-api-user', email='transfer-api-user@example.com', password='pass1234',
        )

    def _authenticate(self, business: Business, role: str):
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)

    def test_confirm_and_list_round_trip(self):
        business = _create_business('API traslados')
        self._authenticate(business, role='manager')
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        product = Product.objects.create(business=business, name='Producto API')
        _set_stock(business, product, depot, Decimal('10'))

        url = reverse('inventory:transfer-list')
        payload = {
            'origin_location_id': str(depot.pk),
            'destination_location_id': str(local.pk),
            'idempotency_key': 'api-key-1',
            'lines': [{'product_id': str(product.pk), 'quantity': '2'}],
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        transfer_id = response.data['id']
        self.assertEqual(response.data['origin_location_id'], str(depot.pk))
        self.assertEqual(response.data['destination_location_id'], str(local.pk))
        self.assertEqual(len(response.data['lines']), 1)
        self.assertEqual(response.data['lines'][0]['quantity'], '2.00')

        # Reintento: misma clave + mismo contenido -> 200, mismo traslado.
        replay = self.client.post(url, payload, format='json')
        self.assertEqual(replay.status_code, status.HTTP_200_OK, replay.data)
        self.assertEqual(replay.data['id'], transfer_id)
        self.assertEqual(
            StockMovement.objects.filter(business=business, reason='transfer').count(), 2,
        )

        # Misma clave, contenido distinto -> conflicto.
        conflicting_payload = dict(
            payload,
            lines=[{'product_id': str(product.pk), 'quantity': '3'}],
        )
        conflict = self.client.post(url, conflicting_payload, format='json')
        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT, conflict.data)
        self.assertEqual(conflict.data['error']['code'], 'IDEMPOTENCY_KEY_CONFLICT')

        history = self.client.get(url)
        self.assertEqual(history.status_code, status.HTTP_200_OK)
        self.assertEqual(len(history.data), 1)
        self.assertEqual(history.data[0]['id'], transfer_id)

        detail = self.client.get(reverse('inventory:transfer-detail', args=[transfer_id]))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['id'], transfer_id)

    def test_rejects_quantity_outside_admitted_precision(self):
        business = _create_business('Precisión ficticia')
        self._authenticate(business, role='manager')
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        product = Product.objects.create(business=business, name='Producto preciso')
        _set_stock(business, product, depot, Decimal('10'))

        url = reverse('inventory:transfer-list')
        payload = {
            'origin_location_id': str(depot.pk),
            'destination_location_id': str(local.pk),
            'idempotency_key': 'precision-key',
            'lines': [{'product_id': str(product.pk), 'quantity': '1.005'}],
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(StockTransfer.objects.filter(business=business).exists())

    def test_confirm_requires_idempotency_key(self):
        business = _create_business('Clave obligatoria ficticia')
        self._authenticate(business, role='manager')
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        product = Product.objects.create(business=business, name='Producto sin clave')
        _set_stock(business, product, depot, Decimal('10'))

        url = reverse('inventory:transfer-list')
        base_payload = {
            'origin_location_id': str(depot.pk),
            'destination_location_id': str(local.pk),
            'lines': [{'product_id': str(product.pk), 'quantity': '2'}],
        }
        variants = {
            'omitida': base_payload,
            'vacía': dict(base_payload, idempotency_key=''),
            'solo espacios': dict(base_payload, idempotency_key='   '),
            'nula': dict(base_payload, idempotency_key=None),
        }
        for label, payload in variants.items():
            with self.subTest(clave=label):
                response = self.client.post(url, payload, format='json')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertIn('idempotency_key', response.data)

        self.assertFalse(StockTransfer.objects.filter(business=business).exists())
        self.assertFalse(StockMovement.objects.filter(business=business).exists())
        self.assertEqual(
            ProductStock.objects.get(product=product, location=depot).quantity, Decimal('10'),
        )
        self.assertFalse(ProductStock.objects.filter(product=product, location=local).exists())

    def test_insufficient_stock_returns_400_detail_without_effects(self):
        business = _create_business('Stock corto ficticio')
        self._authenticate(business, role='manager')
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        ok_product = Product.objects.create(business=business, name='Producto con stock')
        short_product = Product.objects.create(business=business, name='Producto corto')
        _set_stock(business, ok_product, depot, Decimal('10'))
        _set_stock(business, short_product, depot, Decimal('1'))

        response = self.client.post(reverse('inventory:transfer-list'), {
            'origin_location_id': str(depot.pk),
            'destination_location_id': str(local.pk),
            'idempotency_key': 'stock-corto',
            'lines': [
                {'product_id': str(ok_product.pk), 'quantity': '2'},
                {'product_id': str(short_product.pk), 'quantity': '2'},
            ],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn('Stock insuficiente', str(response.data['detail']))
        self.assertFalse(StockTransfer.objects.filter(business=business).exists())
        self.assertFalse(StockMovement.objects.filter(business=business).exists())
        self.assertEqual(ProductStock.objects.get(product=ok_product, location=depot).quantity, Decimal('10'))

        # La clave no quedó consumida por el intento rechazado.
        _set_stock(business, short_product, depot, Decimal('5'))
        retry = self.client.post(reverse('inventory:transfer-list'), {
            'origin_location_id': str(depot.pk),
            'destination_location_id': str(local.pk),
            'idempotency_key': 'stock-corto',
            'lines': [
                {'product_id': str(ok_product.pk), 'quantity': '2'},
                {'product_id': str(short_product.pk), 'quantity': '2'},
            ],
        }, format='json')
        self.assertEqual(retry.status_code, status.HTTP_201_CREATED, retry.data)

    def test_unauthenticated_confirm_returns_401(self):
        business = _create_business('Sin sesión ficticia')
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        product = Product.objects.create(business=business, name='Producto sin sesión')
        _set_stock(business, product, depot, Decimal('10'))
        self.client.cookies['bid'] = str(business.id)

        response = self.client.post(reverse('inventory:transfer-list'), {
            'origin_location_id': str(depot.pk),
            'destination_location_id': str(local.pk),
            'idempotency_key': 'sin-sesion',
            'lines': [{'product_id': str(product.pk), 'quantity': '1'}],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(StockTransfer.objects.filter(business=business).exists())

    def test_user_without_manage_permission_cannot_confirm(self):
        business = _create_business('Sin permiso')
        self._authenticate(business, role='viewer')  # view_stock, sin manage_stock
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        product = Product.objects.create(business=business, name='Producto sin permiso')
        _set_stock(business, product, depot, Decimal('10'))

        url = reverse('inventory:transfer-list')
        payload = {
            'origin_location_id': str(depot.pk),
            'destination_location_id': str(local.pk),
            'idempotency_key': 'no-permission-key',
            'lines': [{'product_id': str(product.pk), 'quantity': '1'}],
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(StockTransfer.objects.filter(business=business).exists())

        # El mismo rol sí puede leer el historial (0 traslados).
        history = self.client.get(url)
        self.assertEqual(history.status_code, status.HTTP_200_OK)
        self.assertEqual(history.data, [])

    def test_cross_tenant_location_and_product_rejected(self):
        business = _create_business('Negocio propio')
        other_business = _create_business('Negocio ajeno')
        self._authenticate(business, role='manager')

        own_depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        own_product = Product.objects.create(business=business, name='Producto propio')
        _set_stock(business, own_product, own_depot, Decimal('10'))
        own_local = get_primary_stock_location(business)

        other_local = get_primary_stock_location(other_business)
        other_depot = StockLocation.objects.create(
            business=other_business, name='Depósito ajeno', is_active=True,
        )
        other_product = Product.objects.create(business=other_business, name='Producto ajeno')
        _set_stock(other_business, other_product, other_depot, Decimal('10'))

        url = reverse('inventory:transfer-list')

        foreign_location_payload = {
            'origin_location_id': str(own_depot.pk),
            'destination_location_id': str(other_local.pk),
            'idempotency_key': 'foreign-location-key',
            'lines': [{'product_id': str(own_product.pk), 'quantity': '1'}],
        }
        response = self.client.post(url, foreign_location_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        foreign_product_payload = {
            'origin_location_id': str(own_depot.pk),
            'destination_location_id': str(own_local.pk),
            'idempotency_key': 'foreign-product-key',
            'lines': [{'product_id': str(other_product.pk), 'quantity': '1'}],
        }
        response = self.client.post(url, foreign_product_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertFalse(StockTransfer.objects.filter(business=business).exists())

    def test_cannot_view_foreign_business_transfer_history_or_detail(self):
        business = _create_business('Historial propio')
        other_business = _create_business('Historial ajeno')

        other_local = get_primary_stock_location(other_business)
        other_depot = StockLocation.objects.create(
            business=other_business, name='Depósito ajeno', is_active=True,
        )
        other_product = Product.objects.create(
            business=other_business, name='Producto ajeno historial',
        )
        _set_stock(other_business, other_product, other_depot, Decimal('10'))
        other_transfer, _ = confirm_stock_transfer(
            business=other_business,
            origin_location=other_depot,
            destination_location=other_local,
            lines=[{'product_id': other_product.pk, 'quantity': Decimal('1')}],
            idempotency_key='other-business-history',
            created_by=self.user,
        )

        self._authenticate(business, role='manager')
        url = reverse('inventory:transfer-list')
        history = self.client.get(url)
        self.assertEqual(history.status_code, status.HTTP_200_OK)
        self.assertEqual(history.data, [])

        detail_url = reverse('inventory:transfer-detail', args=[other_transfer.pk])
        detail = self.client.get(detail_url)
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

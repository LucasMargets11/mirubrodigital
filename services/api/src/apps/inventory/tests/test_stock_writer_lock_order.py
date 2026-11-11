"""
Orden global de bloqueo de saldos en los escritores restantes (PR3.1).

Run with: python manage.py test apps.inventory.tests.test_stock_writer_lock_order

Cada prueba solapa, en conexiones separadas, un traslado de dos productos
(A, B en orden global) con un escritor cuyos renglones vienen en orden
comercial inverso (B, A):

  1. El traslado toma su primer saldo en Local principal y se detiene
     adentro de su transacción.
  2. Arranca el escritor. La conexión de control verifica con
     pg_blocking_pids que el escritor quedó esperando un lock del traslado
     (solapamiento real, no ejecución en secuencia).
  3. El traslado continúa con su segundo producto.

Si el escritor bloqueara sus saldos en orden comercial (B y después A),
el paso 3 cierra un ciclo: PostgreSQL aborta a uno con deadlock (40P01) o
vence lock_timeout (55P03) y la prueba falla. Además se verifica el orden
en que el escritor adquirió sus saldos y el estado final de saldos,
reservas y movimientos.

Datos ficticios. Requiere PostgreSQL.
"""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.business.models import Business, CommercialSettings, Subscription
from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.inventory import importer as inventory_importer
from apps.inventory import services as inventory_services
from apps.inventory.importer import apply_inventory_import
from apps.inventory.models import (
    InventoryImportJob,
    ProductStock,
    StockLocation,
    StockMovement,
    StockReplenishment,
    StockTransfer,
    StockTransferLine,
)
from apps.inventory.services import (
    confirm_stock_transfer,
    create_stock_replenishment,
    ensure_stock_record,
    get_primary_stock_location,
    reserve_stock,
    void_stock_replenishment,
)
from apps.orders import serializers as orders_serializers
from apps.orders.models import Order as RestoOrder, OrderItem as RestoOrderItem
from apps.orders.serializers import OrderCreateSaleSerializer
from apps.sales import serializers as sales_serializers
from apps.sales import views as sales_views
from apps.sales.models import Order as SalesOrder, OrderItem as SalesOrderItem, Sale
from apps.sales.serializers import SaleCancelSerializer, SaleCreateSerializer
from apps.sales.views import OrderViewSet
from apps.treasury.models import Account

LOCK_TIMEOUT = '8s'
WAIT_SECONDS = 15
CYCLE_RESULTS = ('deadlock', 'lock_timeout')

# Módulos que importan ensure_stock_record por nombre: se instrumentan todos
# para registrar en qué orden adquiere sus saldos cada participante.
TRACED_MODULES = (
    inventory_services,
    inventory_importer,
    sales_serializers,
    sales_views,
    orders_serializers,
)


def _sqlstate(exc):
    """Busca el SQLSTATE en la cadena de causas (el importador envuelve errores)."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        state = getattr(exc, 'sqlstate', None) or getattr(getattr(exc, '__cause__', None), 'sqlstate', None)
        if state:
            return state
        exc = exc.__cause__ or exc.__context__
    return None


def _classify(exc):
    state = _sqlstate(exc)
    if state == '40P01':
        return 'deadlock'
    if state == '55P03':
        return 'lock_timeout'
    return f'error:{state}:{type(exc).__name__}:{exc}'


@skipUnless(connection.vendor == 'postgresql', 'Requiere PostgreSQL: pg_blocking_pids y detección de deadlocks.')
class StockWriterLockOrderTests(TransactionTestCase):

    def _fixture_teardown(self):
        # Mismo workaround que PR2/PR3: el flush por TRUNCATE falla contra
        # tablas unmanaged de treasury referenciadas por Business. Cada
        # prueba usa su propio negocio y usuario ficticios.
        pass

    # ------------------------------------------------------------------ #
    # Escenario base
    # ------------------------------------------------------------------ #

    def _scenario(self, *, local_qty=Decimal('5'), depot_qty=Decimal('0'), local_rows=True):
        suffix = uuid.uuid4().hex[:8]
        business = Business.objects.create(name=f'Negocio ficticio {suffix}')
        Subscription.objects.create(business=business, plan='starter', status='active')
        commercial = CommercialSettings.objects.for_business(business)
        commercial.block_sales_if_no_open_cash_session = False
        commercial.allow_sell_without_stock = False
        commercial.require_customer_for_sales = False
        commercial.save()
        user = get_user_model().objects.create_user(
            username=f'lock-writer-{suffix}', email=f'lock-writer-{suffix}@example.com', password='pass1234',
        )
        local = get_primary_stock_location(business)
        depot = StockLocation.objects.create(business=business, name='Depósito', is_active=True)
        first = Product.objects.create(business=business, name='Producto X', price=Decimal('10'))
        second = Product.objects.create(business=business, name='Producto Y', price=Decimal('10'))
        low, high = sorted([first, second], key=lambda p: str(p.pk))
        for product in (low, high):
            if local_rows:
                self._set_stock(business, product, local, local_qty)
            self._set_stock(business, product, depot, depot_qty)
        return SimpleNamespace(
            business=business, user=user, local=local, depot=depot, A=low, B=high,
            labels={str(low.pk): 'A', str(high.pk): 'B', str(local.pk): 'local', str(depot.pk): 'deposito'},
        )

    @staticmethod
    def _set_stock(business, product, location, quantity, reserved=Decimal('0')):
        stock = ensure_stock_record(business, product, location=location)
        stock.quantity = quantity
        stock.reserved_quantity = reserved
        stock.save(update_fields=['quantity', 'reserved_quantity', 'updated_at'])
        return stock

    def _stock(self, s, product, location):
        return ProductStock.objects.get(business=s.business, product=product, location=location)

    # ------------------------------------------------------------------ #
    # Arnés de solapamiento
    # ------------------------------------------------------------------ #

    def _race(self, s, writer, *, origin=None, destination=None, transfer_qty=Decimal('2')):
        """Corre traslado (A, B) y writer() en conexiones separadas y solapadas."""
        origin = origin or s.local
        destination = destination or s.depot
        tag = threading.local()
        lock_log = []
        log_lock = threading.Lock()
        pids = {}
        results = {}
        transfer_holds_first_lock = threading.Event()
        writer_is_blocked = threading.Event()
        overlap = {'proved': False}
        original_ensure = inventory_services.ensure_stock_record

        def traced_ensure(biz, product, location=None):
            stock = original_ensure(biz, product, location=location)
            who = getattr(tag, 'name', None)
            if who is None:
                return stock
            entry = (who, s.labels[str(stock.product_id)], s.labels[str(stock.location_id)])
            with log_lock:
                if entry not in lock_log:
                    lock_log.append(entry)
            if who == 'transfer' and entry[2] == 'local' and not transfer_holds_first_lock.is_set():
                # Primer saldo de Local principal retenido por el traslado
                # adentro de su transacción hasta ver al escritor esperándolo.
                transfer_holds_first_lock.set()
                writer_is_blocked.wait(WAIT_SECONDS)
            return stock

        def prepare(name):
            close_old_connections()
            tag.name = name
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_backend_pid()')
                pids[name] = cursor.fetchone()[0]
                cursor.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")

        def run_transfer():
            prepare('transfer')
            try:
                confirm_stock_transfer(
                    business=Business.objects.get(pk=s.business.pk),
                    origin_location=StockLocation.objects.get(pk=origin.pk),
                    destination_location=StockLocation.objects.get(pk=destination.pk),
                    lines=[
                        {'product_id': s.A.pk, 'quantity': transfer_qty},
                        {'product_id': s.B.pk, 'quantity': transfer_qty},
                    ],
                    idempotency_key=f'lock-writer-{uuid.uuid4().hex}',
                    created_by=get_user_model().objects.get(pk=s.user.pk),
                )
                results['transfer'] = 'ok'
            except ValidationError as exc:
                results['transfer'] = f'rejected:{exc}'
            except Exception as exc:  # noqa: BLE001 - se clasifica y la prueba falla
                results['transfer'] = _classify(exc)
            finally:
                tag.name = None
                close_old_connections()

        def run_writer():
            prepare('writer')
            try:
                if not transfer_holds_first_lock.wait(WAIT_SECONDS):
                    results['writer'] = 'transfer_never_locked'
                    return
                outcome = writer()
                results['writer'] = 'ok' if outcome is None else outcome
            except (ValidationError, DRFValidationError) as exc:
                results['writer'] = f'rejected:{exc}'
            except Exception as exc:  # noqa: BLE001 - se clasifica y la prueba falla
                results['writer'] = _classify(exc)
            finally:
                tag.name = None
                close_old_connections()

        patches = [patch.object(module, 'ensure_stock_record', traced_ensure) for module in TRACED_MODULES]
        for p in patches:
            p.start()
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                transfer_future = executor.submit(run_transfer)
                writer_future = executor.submit(run_writer)
                try:
                    self.assertTrue(transfer_holds_first_lock.wait(WAIT_SECONDS), 'El traslado nunca tomó su primer lock.')
                    deadline = time.monotonic() + WAIT_SECONDS
                    while time.monotonic() < deadline and not overlap['proved']:
                        writer_pid = pids.get('writer')
                        if writer_pid is not None:
                            with connection.cursor() as cursor:
                                cursor.execute('SELECT pg_blocking_pids(%s)', [writer_pid])
                                blockers = cursor.fetchone()[0] or []
                            if pids['transfer'] in blockers:
                                overlap['proved'] = True
                                break
                        time.sleep(0.05)
                finally:
                    # Siempre liberar al traslado para no colgar la prueba.
                    writer_is_blocked.set()
                transfer_future.result(timeout=WAIT_SECONDS * 2)
                writer_future.result(timeout=WAIT_SECONDS * 2)
        finally:
            for p in patches:
                p.stop()

        return SimpleNamespace(
            results=results,
            overlap=overlap['proved'],
            writer_order=[e[1:] for e in lock_log if e[0] == 'writer'],
            transfer_order=[e[1:] for e in lock_log if e[0] == 'transfer'],
        )

    def _assert_no_cycle(self, run):
        self.assertTrue(run.overlap, f'El escritor nunca esperó un lock del traslado: sin solapamiento. {run}')
        for name in ('transfer', 'writer'):
            self.assertNotIn(run.results.get(name), CYCLE_RESULTS, f'{name} abortado por ciclo de locks: {run}')
        self.assertEqual(run.results, {'transfer': 'ok', 'writer': 'ok'}, run)
        # El escritor toma A antes que B aunque sus renglones vengan B, A.
        self.assertEqual(run.writer_order, [('A', 'local'), ('B', 'local')], run)

    def _assert_transfer_effects(self, s, *, qty=Decimal('2'), origin=None, destination=None):
        origin = origin or s.local
        destination = destination or s.depot
        transfer = StockTransfer.objects.get(business=s.business)
        self.assertEqual(transfer.lines.count(), 2)
        self.assertEqual(transfer.movements.count(), 4)
        self.assertEqual(
            set(transfer.movements.filter(movement_type='OUT').values_list('location_id', flat=True)), {origin.pk},
        )
        self.assertEqual(
            set(transfer.movements.filter(movement_type='IN').values_list('location_id', flat=True)), {destination.pk},
        )
        self.assertTrue(all(line.quantity == qty for line in transfer.lines.all()))

    # ------------------------------------------------------------------ #
    # Ventas
    # ------------------------------------------------------------------ #

    @skipUnlessDBFeature('has_select_for_update')
    def test_sale_cancel_vs_transfer(self):
        s = self._scenario()
        create = SaleCreateSerializer(
            data={'items': [
                {'product_id': str(s.B.pk), 'quantity': '1'},
                {'product_id': str(s.A.pk), 'quantity': '1'},
            ]},
            context={'business': s.business, 'request': SimpleNamespace(user=s.user)},
        )
        create.is_valid(raise_exception=True)
        sale = create.save()
        self.assertEqual([i.product_id for i in sale.items.select_related('product')], [s.B.pk, s.A.pk])

        def writer():
            locked_sale = Sale.objects.get(pk=sale.pk)
            serializer = SaleCancelSerializer(
                data={'reason': 'Prueba ficticia'},
                context={'sale': locked_sale, 'user': get_user_model().objects.get(pk=s.user.pk)},
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

        run = self._race(s, writer)
        self._assert_no_cycle(run)
        self._assert_transfer_effects(s)
        for product in (s.A, s.B):
            # 5 - 1 (venta) - 2 (traslado) + 1 (reversa)
            self.assertEqual(self._stock(s, product, s.local).quantity, Decimal('3'))
            self.assertEqual(self._stock(s, product, s.depot).quantity, Decimal('2'))
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CANCELLED)
        reversals = StockMovement.objects.filter(business=s.business, note=f'Reversa venta #{sale.number}')
        self.assertEqual(reversals.count(), 2)
        self.assertEqual(set(reversals.values_list('location_id', flat=True)), {s.local.pk})

    # ------------------------------------------------------------------ #
    # Pedidos comerciales (sales.OrderViewSet)
    # ------------------------------------------------------------------ #

    def _sales_order(self, s, *, status, reserve=False):
        customer = Customer.objects.create(business=s.business, name='Cliente ficticio')
        order = SalesOrder.objects.create(
            business=s.business, number=f'O-{uuid.uuid4().hex[:6]}', customer=customer, status=status,
        )
        base = timezone.now()
        for offset, product in enumerate((s.B, s.A)):
            item = SalesOrderItem.objects.create(
                order=order, product=product, name_snapshot=product.name,
                unit_price=Decimal('10'), quantity=Decimal('1'), subtotal=Decimal('10'),
            )
            SalesOrderItem.objects.filter(pk=item.pk).update(created_at=base.replace(microsecond=offset))
            if reserve:
                reserve_stock(s.business, product, Decimal('1'))
                SalesOrderItem.objects.filter(pk=item.pk).update(reserved_quantity=Decimal('1'))
        self.assertEqual([i.product_id for i in order.items.select_related('product')], [s.B.pk, s.A.pk])
        return order

    def _order_action(self, s, order, action):
        def writer():
            view = OrderViewSet()
            view.get_object = lambda: SalesOrder.objects.get(pk=order.pk)
            request = SimpleNamespace(user=get_user_model().objects.get(pk=s.user.pk))
            response = getattr(OrderViewSet, action)(view, request, pk=str(order.pk))
            if response.status_code != 200:
                return f'http_{response.status_code}:{response.data}'
            return None
        return writer

    @skipUnlessDBFeature('has_select_for_update')
    def test_sales_order_confirm_vs_transfer(self):
        s = self._scenario()
        order = self._sales_order(s, status=SalesOrder.Status.DRAFT)
        run = self._race(s, self._order_action(s, order, 'confirm'))
        self._assert_no_cycle(run)
        self._assert_transfer_effects(s)
        for product in (s.A, s.B):
            stock = self._stock(s, product, s.local)
            self.assertEqual(stock.quantity, Decimal('3'))
            self.assertEqual(stock.reserved_quantity, Decimal('1'))
            self.assertEqual(self._stock(s, product, s.depot).quantity, Decimal('2'))
        order.refresh_from_db()
        self.assertEqual(order.status, SalesOrder.Status.CONFIRMED)
        self.assertEqual(set(order.items.values_list('reserved_quantity', flat=True)), {Decimal('1')})

    @skipUnlessDBFeature('has_select_for_update')
    def test_sales_order_deliver_vs_transfer(self):
        s = self._scenario()
        order = self._sales_order(s, status=SalesOrder.Status.CONFIRMED, reserve=True)
        run = self._race(s, self._order_action(s, order, 'deliver'))
        self._assert_no_cycle(run)
        self._assert_transfer_effects(s)
        for product in (s.A, s.B):
            stock = self._stock(s, product, s.local)
            # 5 - 2 (traslado) - 1 (entrega); la reserva se libera.
            self.assertEqual(stock.quantity, Decimal('2'))
            self.assertEqual(stock.reserved_quantity, Decimal('0'))
        order.refresh_from_db()
        self.assertEqual(order.status, SalesOrder.Status.DELIVERED)
        deliveries = StockMovement.objects.filter(business=s.business, reason='order_delivery')
        self.assertEqual(deliveries.count(), 2)
        self.assertEqual(set(deliveries.values_list('location_id', flat=True)), {s.local.pk})

    @skipUnlessDBFeature('has_select_for_update')
    def test_sales_order_cancel_vs_transfer(self):
        s = self._scenario()
        order = self._sales_order(s, status=SalesOrder.Status.CONFIRMED, reserve=True)
        run = self._race(s, self._order_action(s, order, 'cancel'))
        self._assert_no_cycle(run)
        self._assert_transfer_effects(s)
        for product in (s.A, s.B):
            stock = self._stock(s, product, s.local)
            self.assertEqual(stock.quantity, Decimal('3'))
            self.assertEqual(stock.reserved_quantity, Decimal('0'))
        order.refresh_from_db()
        self.assertEqual(order.status, SalesOrder.Status.CANCELLED)

    # ------------------------------------------------------------------ #
    # Cobro de órdenes de salón/mostrador (orders._register_stock)
    # ------------------------------------------------------------------ #

    @skipUnlessDBFeature('has_select_for_update')
    def test_order_create_sale_vs_transfer(self):
        s = self._scenario()
        order = RestoOrder.objects.create(business=s.business, number=1, status=RestoOrder.Status.OPEN)
        base = timezone.now()
        for offset, product in enumerate((s.B, s.A)):
            item = RestoOrderItem.objects.create(
                order=order, product=product, name=product.name,
                quantity=Decimal('1'), unit_price=Decimal('10'), total_price=Decimal('10'),
            )
            RestoOrderItem.objects.filter(pk=item.pk).update(created_at=base.replace(microsecond=offset))
        self.assertEqual(list(order.items.order_by('created_at').values_list('product_id', flat=True)), [s.B.pk, s.A.pk])

        def writer():
            fresh = RestoOrder.objects.get(pk=order.pk)
            serializer = OrderCreateSaleSerializer(
                data={'payment_method': Sale.PaymentMethod.CASH, 'discount': '0'},
                context={
                    'order': fresh,
                    'business': Business.objects.get(pk=s.business.pk),
                    'request': SimpleNamespace(user=get_user_model().objects.get(pk=s.user.pk)),
                },
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

        run = self._race(s, writer)
        self._assert_no_cycle(run)
        self._assert_transfer_effects(s)
        for product in (s.A, s.B):
            self.assertEqual(self._stock(s, product, s.local).quantity, Decimal('2'))
        order.refresh_from_db()
        self.assertIsNotNone(order.sale_id)
        sale_moves = StockMovement.objects.filter(business=s.business, note=f'Orden #{order.number}')
        self.assertEqual(sale_moves.count(), 2)
        self.assertEqual(set(sale_moves.values_list('location_id', flat=True)), {s.local.pk})

    # ------------------------------------------------------------------ #
    # Reposiciones
    # ------------------------------------------------------------------ #

    def _account(self, s):
        return Account.objects.create(
            business=s.business, name='Caja ficticia', type='cash', currency='ARS', opening_balance=Decimal('100000'),
        )

    @skipUnlessDBFeature('has_select_for_update')
    def test_replenishment_create_vs_transfer(self):
        s = self._scenario()
        account = self._account(s)

        def writer():
            create_stock_replenishment(
                business=Business.objects.get(pk=s.business.pk),
                supplier_name='Proveedor ficticio',
                account=Account.objects.get(pk=account.pk),
                items=[
                    {'product_id': s.B.pk, 'quantity': '1', 'unit_cost': '3'},
                    {'product_id': s.A.pk, 'quantity': '1', 'unit_cost': '3'},
                ],
                created_by=get_user_model().objects.get(pk=s.user.pk),
            )

        run = self._race(s, writer)
        self._assert_no_cycle(run)
        self._assert_transfer_effects(s)
        for product in (s.A, s.B):
            self.assertEqual(self._stock(s, product, s.local).quantity, Decimal('4'))
        replenishment = StockReplenishment.objects.get(business=s.business)
        self.assertEqual(replenishment.stock_movements.count(), 2)
        self.assertEqual(set(replenishment.stock_movements.values_list('location_id', flat=True)), {s.local.pk})

    @skipUnlessDBFeature('has_select_for_update')
    def test_replenishment_create_vs_transfer_creating_missing_balances(self):
        # Camino de creación de saldos faltantes: Local principal no tiene
        # saldo para ninguno de los dos productos. El traslado entrante
        # (Depósito → Local) los inserta en orden global y el escritor debe
        # esperar el insert de A antes de intentar el de B.
        s = self._scenario(local_rows=False, depot_qty=Decimal('5'))
        account = self._account(s)

        def writer():
            create_stock_replenishment(
                business=Business.objects.get(pk=s.business.pk),
                supplier_name='Proveedor ficticio',
                account=Account.objects.get(pk=account.pk),
                items=[
                    {'product_id': s.B.pk, 'quantity': '1', 'unit_cost': '3'},
                    {'product_id': s.A.pk, 'quantity': '1', 'unit_cost': '3'},
                ],
            )

        run = self._race(s, writer, origin=s.depot, destination=s.local)
        self._assert_no_cycle(run)
        self._assert_transfer_effects(s, origin=s.depot, destination=s.local)
        for product in (s.A, s.B):
            self.assertEqual(
                ProductStock.objects.filter(business=s.business, product=product, location=s.local).count(), 1,
            )
            self.assertEqual(self._stock(s, product, s.local).quantity, Decimal('3'))
            self.assertEqual(self._stock(s, product, s.depot).quantity, Decimal('3'))

    @skipUnlessDBFeature('has_select_for_update')
    def test_replenishment_void_vs_transfer(self):
        s = self._scenario()
        account = self._account(s)
        replenishment = create_stock_replenishment(
            business=s.business,
            supplier_name='Proveedor ficticio',
            account=account,
            items=[
                {'product_id': s.A.pk, 'quantity': '1', 'unit_cost': '3'},
                {'product_id': s.B.pk, 'quantity': '1', 'unit_cost': '3'},
            ],
        )
        # void recorre los movimientos IN por -created_at: B, A.
        base = timezone.now()
        StockMovement.objects.filter(replenishment=replenishment, product=s.A).update(created_at=base.replace(microsecond=0))
        StockMovement.objects.filter(replenishment=replenishment, product=s.B).update(created_at=base.replace(microsecond=1))
        self.assertEqual(
            list(StockMovement.objects.filter(replenishment=replenishment, movement_type='IN')
                 .values_list('product_id', flat=True)),
            [s.B.pk, s.A.pk],
        )

        def writer():
            void_stock_replenishment(
                replenishment=StockReplenishment.objects.get(pk=replenishment.pk),
                reason='Prueba ficticia',
            )

        run = self._race(s, writer)
        self._assert_no_cycle(run)
        self._assert_transfer_effects(s)
        for product in (s.A, s.B):
            # 5 + 1 (reposición) - 2 (traslado) - 1 (anulación)
            self.assertEqual(self._stock(s, product, s.local).quantity, Decimal('3'))
        replenishment.refresh_from_db()
        self.assertEqual(replenishment.status, StockReplenishment.Status.VOIDED)
        reversals = StockMovement.objects.filter(replenishment=replenishment, reason='replenishment_void')
        self.assertEqual(reversals.count(), 2)
        self.assertEqual(set(reversals.values_list('location_id', flat=True)), {s.local.pk})

    # ------------------------------------------------------------------ #
    # Importación de inventario
    # ------------------------------------------------------------------ #

    @skipUnlessDBFeature('has_select_for_update')
    def test_inventory_import_vs_transfer(self):
        s = self._scenario()
        job = InventoryImportJob.objects.create(
            business=s.business,
            created_by=s.user,
            filename='inventario-ficticio.xlsx',
            rows=[
                {'line_number': 2, 'status': 'ok', 'product_id': str(s.B.pk), 'payload': {'stock': '10'}},
                {'line_number': 3, 'status': 'ok', 'product_id': str(s.A.pk), 'payload': {'stock': '10'}},
            ],
            summary={'error_count': 0, 'warning_count': 0},
        )

        def writer():
            apply_inventory_import(
                InventoryImportJob.objects.get(pk=job.pk),
                business=Business.objects.get(pk=s.business.pk),
                user=get_user_model().objects.get(pk=s.user.pk),
            )

        run = self._race(s, writer)
        self._assert_no_cycle(run)
        self._assert_transfer_effects(s)
        for product in (s.A, s.B):
            # El ajuste espera al traslado y fija el saldo absoluto.
            self.assertEqual(self._stock(s, product, s.local).quantity, Decimal('10'))
            self.assertEqual(self._stock(s, product, s.depot).quantity, Decimal('2'))
        job.refresh_from_db()
        self.assertEqual(job.status, InventoryImportJob.Status.DONE)
        self.assertEqual(job.adjusted_count, 2)
        self.assertEqual(job.updated_count, 2)
        adjusts = StockMovement.objects.filter(business=s.business, movement_type='ADJUST')
        self.assertEqual(adjusts.count(), 2)
        self.assertEqual(set(adjusts.values_list('location_id', flat=True)), {s.local.pk})


class InventoryImportSequentialContractTests(TestCase):
    """Contrato secuencial del importador tras diferir los ajustes (fase 1 → 3)."""

    def test_rows_apply_in_file_order_and_last_row_wins(self):
        business = Business.objects.create(name='Importación ficticia')
        Subscription.objects.create(business=business, plan='starter', status='active')
        local = get_primary_stock_location(business)
        product = Product.objects.create(business=business, name='Producto X', price=Decimal('10'))
        ensure_stock_record(business, product)
        job = InventoryImportJob.objects.create(
            business=business,
            filename='inventario-ficticio.xlsx',
            rows=[
                {'line_number': 2, 'status': 'ok', 'product_id': str(product.pk),
                 'payload': {'stock': '7', 'note': 'primera'}},
                {'line_number': 3, 'status': 'error', 'payload': {}},
                {'line_number': 4, 'status': 'ok', 'product_id': None,
                 'payload': {'name': 'Producto nuevo', 'stock': '4'}},
                {'line_number': 5, 'status': 'ok', 'product_id': None,
                 'payload': {'name': 'Producto sin stock'}},
                {'line_number': 6, 'status': 'ok', 'product_id': str(product.pk),
                 'payload': {'stock': '3', 'note': 'segunda'}},
            ],
            summary={'error_count': 0, 'warning_count': 0},
        )

        apply_inventory_import(job, business=business, user=None)

        job.refresh_from_db()
        self.assertEqual(job.status, InventoryImportJob.Status.DONE)
        self.assertEqual(
            (job.created_count, job.updated_count, job.adjusted_count, job.skipped_count),
            (2, 2, 3, 1),
        )
        self.assertEqual(ProductStock.objects.get(product=product, location=local).quantity, Decimal('3'))
        created = Product.objects.get(business=business, name='Producto nuevo')
        self.assertEqual(ProductStock.objects.get(product=created, location=local).quantity, Decimal('4'))
        notes = list(
            StockMovement.objects.filter(product=product, movement_type='ADJUST')
            .order_by('created_at').values_list('note', flat=True)
        )
        self.assertEqual(notes, ['primera', 'segunda'])

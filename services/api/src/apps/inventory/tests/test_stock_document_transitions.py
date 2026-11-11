"""
Transiciones concurrentes sobre el mismo documento de stock (PR3.2).

Run with: python manage.py test apps.inventory.tests.test_stock_document_transitions

Coordinación de cada carrera, en conexiones separadas:

  1. El primer participante ejecuta la operación completa y se detiene
     adentro de su transacción, después de escribir todos sus efectos y
     antes del commit (post_save del documento o de su historial).
  2. Recién entonces arranca el segundo participante, que obtiene su
     instancia del documento igual que la vista (sin lock) y llama a la
     misma operación o a una que compite con ella.
  3. La conexión de control verifica con pg_blocking_pids que el segundo
     quedó esperando un lock del primero (solapamiento real) y libera al
     primero.

El segundo debe observar el resultado confirmado del primero: sin repetir
movimientos, reservas, liberaciones, historial ni efectos de tesorería.

Datos ficticios. Requiere PostgreSQL.
"""
import logging
import threading
import time
from contextlib import contextmanager
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import OperationalError, close_old_connections, connection
from django.db.models.signals import post_save
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.business.models import Business, CommercialSettings, Subscription
from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.inventory.models import ProductStock, StockMovement, StockReplenishment
from apps.inventory.services import (
    create_stock_replenishment,
    ensure_stock_record,
    get_primary_stock_location,
    reserve_stock,
    void_stock_replenishment,
)
from apps.sales import views as sales_views
from apps.sales.models import Order, OrderHistory, OrderItem, Sale
from apps.sales.serializers import SaleCancelSerializer, SaleCreateSerializer
from apps.sales.views import OrderViewSet
from apps.treasury.models import Account, Expense, Payment as TreasuryPayment, Transaction

LOCK_TIMEOUT = '8s'
WAIT_SECONDS = 15


@contextmanager
def _quiet_logger(name):
    """Silencia el traceback esperado del logger sin exigir que exista."""
    target = logging.getLogger(name)
    previous, target.disabled = target.disabled, True
    try:
        yield
    finally:
        target.disabled = previous


def _classify(exc):
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        state = getattr(cur, 'sqlstate', None)
        if state == '40P01':
            return 'deadlock'
        if state == '55P03':
            return 'lock_timeout'
        cur = cur.__cause__ or cur.__context__
    return f'error:{type(exc).__name__}:{exc}'


def _scenario():
    suffix = uuid.uuid4().hex[:8]
    business = Business.objects.create(name=f'Negocio ficticio {suffix}')
    Subscription.objects.create(business=business, plan='starter', status='active')
    commercial = CommercialSettings.objects.for_business(business)
    commercial.block_sales_if_no_open_cash_session = False
    commercial.allow_sell_without_stock = False
    commercial.save()
    user = get_user_model().objects.create_user(
        username=f'doc-race-{suffix}', email=f'doc-race-{suffix}@example.com', password='pass1234',
    )
    local = get_primary_stock_location(business)
    first = Product.objects.create(business=business, name='Producto X', price=Decimal('10'))
    second = Product.objects.create(business=business, name='Producto Y', price=Decimal('10'))
    low, high = sorted([first, second], key=lambda p: str(p.pk))
    for product in (low, high):
        stock = ensure_stock_record(business, product, location=local)
        stock.quantity = Decimal('10')
        stock.save(update_fields=['quantity', 'updated_at'])
    customer = Customer.objects.create(business=business, name='Cliente ficticio')
    return SimpleNamespace(business=business, user=user, local=local, A=low, B=high, customer=customer)


def _stock(s, product):
    return ProductStock.objects.get(business=s.business, product=product, location=s.local)


def _sales_order(s, *, status, reserve=False, products=None, quantity=Decimal('1')):
    order = Order.objects.create(
        business=s.business, number=f'O-{uuid.uuid4().hex[:6]}', customer=s.customer, status=status,
    )
    for product in products or (s.B, s.A):
        OrderItem.objects.create(
            order=order, product=product, name_snapshot=getattr(product, 'name', 'Producto eliminado'),
            unit_price=Decimal('10'), quantity=quantity, subtotal=Decimal('10') * quantity,
            reserved_quantity=quantity if reserve else Decimal('0'),
        )
        if reserve:
            reserve_stock(s.business, product, quantity)
    return order


def _order_action(s, order_pk, action):
    """Invoca la acción del viewset como la vista: get_object sin lock."""
    def run():
        view = OrderViewSet()
        view.get_object = lambda: Order.objects.get(pk=order_pk)
        request = SimpleNamespace(user=get_user_model().objects.get(pk=s.user.pk))
        response = getattr(OrderViewSet, action)(view, request, pk=str(order_pk))
        if response.status_code == 200:
            return 'ok'
        return f"http_{response.status_code}:{response.data.get('error')}"
    return run


@skipUnless(connection.vendor == 'postgresql', 'Requiere PostgreSQL: pg_blocking_pids.')
class StockDocumentTransitionRaceTests(TransactionTestCase):

    def _fixture_teardown(self):
        # Mismo workaround que PR2/PR3: el flush por TRUNCATE falla contra
        # tablas unmanaged de treasury. Cada prueba usa su propio negocio.
        pass

    def _race(self, first, second, *, pause_on):
        tag = threading.local()
        pids, results = {}, {}
        first_paused = threading.Event()
        release_first = threading.Event()
        overlap = {'proved': False}

        def pause(sender, instance, **kwargs):
            if getattr(tag, 'name', None) == 'first' and not first_paused.is_set():
                # Todos los efectos del primero escritos, transacción abierta.
                first_paused.set()
                release_first.wait(WAIT_SECONDS)

        def prepare(name):
            close_old_connections()
            tag.name = name
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_backend_pid()')
                pids[name] = cursor.fetchone()[0]
                cursor.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")

        def runner(name, fn):
            prepare(name)
            try:
                if name == 'second' and not first_paused.wait(WAIT_SECONDS):
                    results[name] = 'first_never_paused'
                    return
                outcome = fn()
                results[name] = 'ok' if outcome is None else outcome
            except Exception as exc:  # noqa: BLE001 - se clasifica y la prueba lo evalúa
                results[name] = _classify(exc)
            finally:
                tag.name = None
                close_old_connections()

        uid = f'race-pause-{uuid.uuid4().hex}'
        post_save.connect(pause, sender=pause_on, weak=False, dispatch_uid=uid)
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(runner, 'first', first)
                f2 = executor.submit(runner, 'second', second)
                try:
                    self.assertTrue(first_paused.wait(WAIT_SECONDS), f'El primero nunca llegó a la pausa: {results}')
                    deadline = time.monotonic() + WAIT_SECONDS
                    while time.monotonic() < deadline and not overlap['proved']:
                        pid = pids.get('second')
                        if pid is not None:
                            with connection.cursor() as cursor:
                                cursor.execute('SELECT pg_blocking_pids(%s)', [pid])
                                blockers = cursor.fetchone()[0] or []
                            if pids['first'] in blockers:
                                overlap['proved'] = True
                                break
                        if 'second' in results:
                            break
                        time.sleep(0.05)
                finally:
                    release_first.set()
                f1.result(timeout=WAIT_SECONDS * 2)
                f2.result(timeout=WAIT_SECONDS * 2)
        finally:
            post_save.disconnect(sender=pause_on, dispatch_uid=uid)
        run = SimpleNamespace(results=results, overlap=overlap['proved'])
        self.assertTrue(run.overlap, f'El segundo nunca esperó un lock del primero: sin solapamiento. {run}')
        return run

    # ------------------------------------------------------------------ #
    # Ventas
    # ------------------------------------------------------------------ #

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_cancellations_of_the_same_sale(self):
        s = _scenario()
        create = SaleCreateSerializer(
            data={'items': [
                {'product_id': str(s.B.pk), 'quantity': '2'},
                {'product_id': str(s.A.pk), 'quantity': '2'},
            ]},
            context={'business': s.business, 'request': SimpleNamespace(user=s.user)},
        )
        create.is_valid(raise_exception=True)
        sale = create.save()

        def cancel():
            stale = Sale.objects.get(pk=sale.pk)  # como get_object_or_404 de la vista
            serializer = SaleCancelSerializer(
                data={'reason': 'Error de carga ficticio'},
                context={'sale': stale, 'user': get_user_model().objects.get(pk=s.user.pk)},
            )
            serializer.is_valid(raise_exception=True)
            result = serializer.save()
            return 'ok' if result.status == Sale.Status.CANCELLED else f'status:{result.status}'

        run = self._race(cancel, cancel, pause_on=Sale)
        self.assertEqual(run.results, {'first': 'ok', 'second': 'ok'}, run)
        for product in (s.A, s.B):
            self.assertEqual(_stock(s, product).quantity, Decimal('10'))
        reversals = StockMovement.objects.filter(business=s.business, note=f'Reversa venta #{sale.number}')
        self.assertEqual(reversals.count(), 2)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CANCELLED)
        self.assertEqual(sale.notes.count('Cancelación:'), 1)

    # ------------------------------------------------------------------ #
    # Pedidos comerciales
    # ------------------------------------------------------------------ #

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_confirmations_of_the_same_order(self):
        s = _scenario()
        order = _sales_order(s, status=Order.Status.DRAFT)
        confirm = _order_action(s, order.pk, 'confirm')
        run = self._race(confirm, confirm, pause_on=OrderHistory)
        self.assertEqual(run.results['first'], 'ok', run)
        self.assertEqual(
            run.results['second'], 'http_400:Solo pedidos en borrador o pendientes se pueden confirmar', run,
        )
        for product in (s.A, s.B):
            stock = _stock(s, product)
            self.assertEqual(stock.quantity, Decimal('10'))
            self.assertEqual(stock.reserved_quantity, Decimal('1'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(set(order.items.values_list('reserved_quantity', flat=True)), {Decimal('1')})
        self.assertEqual(OrderHistory.objects.filter(order=order).count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_deliveries_of_the_same_order(self):
        s = _scenario()
        order = _sales_order(s, status=Order.Status.CONFIRMED, reserve=True)
        deliver = _order_action(s, order.pk, 'deliver')
        run = self._race(deliver, deliver, pause_on=OrderHistory)
        self.assertEqual(run.results, {'first': 'ok', 'second': 'ok'}, run)
        for product in (s.A, s.B):
            stock = _stock(s, product)
            self.assertEqual(stock.quantity, Decimal('9'))
            self.assertEqual(stock.reserved_quantity, Decimal('0'))
        self.assertEqual(StockMovement.objects.filter(business=s.business, reason='order_delivery').count(), 2)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertEqual(set(order.items.values_list('delivered_quantity', flat=True)), {Decimal('1')})
        self.assertEqual(list(OrderHistory.objects.filter(order=order).values_list('action', flat=True)), ['delivered'])

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_cancellations_of_the_same_order(self):
        s = _scenario()
        # Otro pedido confirmado reserva los mismos productos: una segunda
        # liberación consumiría su reserva.
        _sales_order(s, status=Order.Status.CONFIRMED, reserve=True, products=(s.A, s.B))
        order = _sales_order(s, status=Order.Status.CONFIRMED, reserve=True)
        cancel = _order_action(s, order.pk, 'cancel')
        run = self._race(cancel, cancel, pause_on=OrderHistory)
        self.assertEqual(run.results, {'first': 'ok', 'second': 'ok'}, run)
        for product in (s.A, s.B):
            stock = _stock(s, product)
            self.assertEqual(stock.quantity, Decimal('10'))
            self.assertEqual(stock.reserved_quantity, Decimal('1'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(set(order.items.values_list('reserved_quantity', flat=True)), {Decimal('0')})
        self.assertEqual(list(OrderHistory.objects.filter(order=order).values_list('action', flat=True)), ['cancelled'])

    @skipUnlessDBFeature('has_select_for_update')
    def test_delivery_then_concurrent_cancellation_is_rejected(self):
        s = _scenario()
        order = _sales_order(s, status=Order.Status.CONFIRMED, reserve=True)
        run = self._race(
            _order_action(s, order.pk, 'deliver'), _order_action(s, order.pk, 'cancel'), pause_on=OrderHistory,
        )
        self.assertEqual(run.results['first'], 'ok', run)
        self.assertEqual(run.results['second'], 'http_400:No se puede cancelar un pedido entregado', run)
        for product in (s.A, s.B):
            stock = _stock(s, product)
            self.assertEqual(stock.quantity, Decimal('9'))
            self.assertEqual(stock.reserved_quantity, Decimal('0'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertIsNone(order.deleted_at)
        self.assertEqual(list(OrderHistory.objects.filter(order=order).values_list('action', flat=True)), ['delivered'])

    @skipUnlessDBFeature('has_select_for_update')
    def test_cancellation_then_concurrent_delivery_is_rejected(self):
        s = _scenario()
        order = _sales_order(s, status=Order.Status.CONFIRMED, reserve=True)
        run = self._race(
            _order_action(s, order.pk, 'cancel'), _order_action(s, order.pk, 'deliver'), pause_on=OrderHistory,
        )
        self.assertEqual(run.results['first'], 'ok', run)
        self.assertEqual(run.results['second'], 'http_400:No se puede entregar un pedido cancelado', run)
        for product in (s.A, s.B):
            stock = _stock(s, product)
            self.assertEqual(stock.quantity, Decimal('10'))
            self.assertEqual(stock.reserved_quantity, Decimal('0'))
        self.assertFalse(StockMovement.objects.filter(business=s.business, reason='order_delivery').exists())
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(list(OrderHistory.objects.filter(order=order).values_list('action', flat=True)), ['cancelled'])

    @skipUnlessDBFeature('has_select_for_update')
    def test_confirmation_then_concurrent_cancellation_releases_reservations(self):
        s = _scenario()
        order = _sales_order(s, status=Order.Status.DRAFT)
        run = self._race(
            _order_action(s, order.pk, 'confirm'), _order_action(s, order.pk, 'cancel'), pause_on=OrderHistory,
        )
        self.assertEqual(run.results, {'first': 'ok', 'second': 'ok'}, run)
        for product in (s.A, s.B):
            self.assertEqual(_stock(s, product).reserved_quantity, Decimal('0'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(set(order.items.values_list('reserved_quantity', flat=True)), {Decimal('0')})
        self.assertEqual(
            list(OrderHistory.objects.filter(order=order).order_by('created_at').values_list('action', flat=True)),
            ['confirmed', 'cancelled'],
        )

    # ------------------------------------------------------------------ #
    # Reposiciones
    # ------------------------------------------------------------------ #

    def _replenishment(self, s, *, linked):
        account = Account.objects.create(
            business=s.business, name='Caja ficticia', type='cash', currency='ARS', opening_balance=Decimal('100000'),
        )
        replenishment = create_stock_replenishment(
            business=s.business,
            supplier_name='Proveedor ficticio',
            account=account,
            items=[
                {'product_id': s.A.pk, 'quantity': '2', 'unit_cost': '3'},
                {'product_id': s.B.pk, 'quantity': '2', 'unit_cost': '3'},
            ],
        )
        tx_id = replenishment.transaction_id
        if not linked:
            # Reposición sin transacción de tesorería vinculada.
            StockReplenishment.objects.filter(pk=replenishment.pk).update(transaction=None)
        return replenishment, tx_id

    def _void_race(self, *, linked):
        s = _scenario()
        replenishment, tx_id = self._replenishment(s, linked=linked)

        def void():
            stale = StockReplenishment.objects.select_related('transaction').get(pk=replenishment.pk)
            result = void_stock_replenishment(replenishment=stale, reason='Duplicada ficticia')
            return 'ok' if result.status == StockReplenishment.Status.VOIDED else f'status:{result.status}'

        run = self._race(void, void, pause_on=StockReplenishment)
        self.assertEqual(run.results, {'first': 'ok', 'second': 'ok'}, run)
        for product in (s.A, s.B):
            self.assertEqual(_stock(s, product).quantity, Decimal('10'))
        reversals = StockMovement.objects.filter(replenishment=replenishment, reason='replenishment_void')
        self.assertEqual(reversals.count(), 2)
        replenishment.refresh_from_db()
        self.assertEqual(replenishment.status, StockReplenishment.Status.VOIDED)
        self.assertEqual(
            Transaction.objects.get(pk=tx_id).status,
            Transaction.Status.VOIDED if linked else Transaction.Status.POSTED,
        )
        expense = Expense.objects.get(source_type='stock_replenishment', source_id=str(replenishment.pk))
        self.assertEqual(expense.status, Expense.Status.CANCELLED)
        payment = TreasuryPayment.objects.get(expense=expense)
        self.assertEqual(payment.status, TreasuryPayment.Status.VOIDED)
        self.assertEqual((payment.notes or '').count('[ANULADO'), 1, payment.notes)

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_voids_of_the_same_replenishment_with_treasury_link(self):
        self._void_race(linked=True)

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_voids_of_the_same_replenishment_without_treasury_link(self):
        self._void_race(linked=False)


class OrderConfirmRollbackTests(TestCase):
    """Fallo en un renglón posterior: nada de la confirmación queda aplicado."""

    def setUp(self):
        self.s = _scenario()
        Membership.objects.create(user=self.s.user, business=self.s.business, role='owner')
        self.client = APIClient()
        self.client.force_authenticate(user=self.s.user)
        self.client.cookies['bid'] = str(self.s.business.id)
        # Reserva previa de otro pedido sobre A: debe quedar intacta.
        reserve_stock(self.s.business, self.s.A, Decimal('1'))

    def _confirm(self, order):
        return self.client.post(f'/api/v1/sales/orders/{order.pk}/confirm/', {}, format='json')

    def _assert_unchanged(self, order):
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DRAFT)
        self.assertEqual(set(order.items.values_list('reserved_quantity', flat=True)), {Decimal('0')})
        self.assertEqual(_stock(self.s, self.s.A).reserved_quantity, Decimal('1'))
        self.assertEqual(_stock(self.s, self.s.B).reserved_quantity, Decimal('0'))
        self.assertFalse(OrderHistory.objects.filter(order=order).exists())
        self.assertFalse(StockMovement.objects.filter(business=self.s.business).exists())

    def test_later_item_without_product_rolls_back_first_reservation(self):
        # Flujo real: el segundo renglón perdió su producto (FK SET_NULL).
        order = _sales_order(self.s, status=Order.Status.DRAFT, products=(self.s.A, None), quantity=Decimal('2'))
        self.assertEqual([i.product_id for i in order.items.all()], [self.s.A.pk, None])

        with _quiet_logger('apps.sales.views'):
            response = self._confirm(order)

        self.assertEqual(response.status_code, 400, response.data)
        self._assert_unchanged(order)
        self.assertNotIn('NoneType', str(response.data))
        self.assertNotIn('attribute', str(response.data))

    def test_database_error_on_later_item_rolls_back_and_hides_internal_text(self):
        # Fallo inyectado explícitamente: el segundo reserve_stock lanza un
        # error de PostgreSQL después de que el primero escribió su reserva.
        order = _sales_order(self.s, status=Order.Status.DRAFT, products=(self.s.A, self.s.B), quantity=Decimal('2'))
        original = sales_views.reserve_stock
        calls = []

        def failing_reserve(business, product, quantity, *args, **kwargs):
            calls.append(product.pk)
            if len(calls) == 2:
                self.assertEqual(_stock(self.s, self.s.A).reserved_quantity, Decimal('3'))
                raise OperationalError(
                    'deadlock detected\nDETAIL:  Process 11 waits for ShareLock on transaction 99; '
                    'blocked by process 12.\nCONTEXT:  while locking tuple (0,1) in relation "inventory_productstock"'
                )
            return original(business, product, quantity, *args, **kwargs)

        with patch.object(sales_views, 'reserve_stock', failing_reserve), _quiet_logger('apps.sales.views'):
            response = self._confirm(order)

        self.assertEqual(len(calls), 2)
        self.assertEqual(response.status_code, 400, response.data)
        self._assert_unchanged(order)
        body = str(response.data)
        for internal in ('deadlock', 'DETAIL', 'ShareLock', 'inventory_productstock'):
            self.assertNotIn(internal, body)

    def test_successful_confirmation_contract_is_preserved(self):
        order = _sales_order(self.s, status=Order.Status.DRAFT, products=(self.s.A, self.s.B))
        response = self._confirm(order)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Order.Status.CONFIRMED)
        self.assertEqual(_stock(self.s, self.s.A).reserved_quantity, Decimal('2'))
        self.assertEqual(_stock(self.s, self.s.B).reserved_quantity, Decimal('1'))
        response = self._confirm(order)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': 'Solo pedidos en borrador o pendientes se pueden confirmar'})

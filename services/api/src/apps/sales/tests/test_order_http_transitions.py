"""
Recorrido HTTP de pedidos comerciales (sales.Order) - PR3.3.

Run with: python manage.py test apps.sales.tests.test_order_http_transitions

Todas las pruebas autentican con POST /api/v1/auth/login/ (cookie JWT real)
y atraviesan HasBusinessMembership + HasPermission con los permisos
efectivos del rol (defaults de rbac + RolePermissionOverride). Nada usa
force_authenticate.

Matriz de transiciones (acción: origen permitido → destino):

  confirm              DRAFT | PENDING_CONFIRMATION → CONFIRMED
  mark_in_preparation  CONFIRMED                     → IN_PREPARATION
  mark_ready           CONFIRMED | IN_PREPARATION    → READY_FOR_DELIVERY
  deliver              CONFIRMED | IN_PREPARATION | READY_FOR_DELIVERY → DELIVERED
  cancel               cualquier estado salvo DELIVERED → CANCELLED

Reintento idéntico (el pedido ya está en el destino): 200 con el pedido
actual, sin historial nuevo ni efectos de stock. confirm es la excepción
heredada de PR3.2: un segundo confirm responde 400.

Datos ficticios. La carrera requiere PostgreSQL.
"""
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from rest_framework.test import APIClient

from apps.accounts.models import AccountProfile, Membership, RolePermissionOverride
from apps.accounts.rbac_registry import get_registry
from apps.inventory.models import StockMovement
from apps.inventory.services import register_stock_movement
# Importado como módulo: enlazar la clase de PR3.2 por nombre haría que el
# runner la vuelva a descubrir y ejecutar dentro de esta suite.
from apps.inventory.tests import test_stock_document_transitions as pr32
from apps.sales import views as sales_views
from apps.sales.models import Order, OrderHistory

PASSWORD = 'Ficticia-PR33-pass!'
LOGIN_URL = '/api/v1/auth/login/'
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def _member(s, role, *, business=None):
    from django.contrib.auth import get_user_model

    business = business or s.business
    n = Membership.objects.filter(business=business).count()
    email = f'{role}-{n}-{business.pk}@example.com'
    user = get_user_model().objects.create_user(username=email, email=email, password=PASSWORD)
    AccountProfile.objects.get_or_create(user=user)
    Membership.objects.create(user=user, business=business, role=role)
    return user


_sales_order = pr32._sales_order
_scenario = pr32._scenario
_stock = pr32._stock


def _login(user, business):
    # El throttle de login cuenta por IP en toda la suite; se reinicia para
    # que cada login de prueba pase por la vista real sin quedar regulado.
    cache.clear()
    client = APIClient()
    response = client.post(LOGIN_URL, {'email': user.email, 'password': PASSWORD}, format='json')
    assert response.status_code == 200, response.content
    assert 'access_token' in response.cookies
    client.credentials(HTTP_X_BUSINESS_ID=str(business.pk))
    return client


def _post(client, order, action):
    return client.post(f'/api/v1/sales/orders/{order.pk}/{action}/', {}, format='json')


def _snapshot(s, order):
    order.refresh_from_db()
    return {
        'status': order.status,
        'deleted_at': order.deleted_at,
        'items': sorted(
            (str(i.pk), i.reserved_quantity, i.delivered_quantity) for i in order.items.all()
        ),
        'stock': {
            p.pk: (_stock(s, p).quantity, _stock(s, p).reserved_quantity) for p in (s.A, s.B)
        },
        'movements': StockMovement.objects.filter(business=s.business).count(),
        'history': list(
            OrderHistory.objects.filter(order=order)
            .order_by('created_at').values_list('action', 'from_status', 'to_status')
        ),
    }


@override_settings(CACHES=LOCMEM)
class OrderDeliverPermissionHttpTests(TestCase):
    """deliver_orders: owner/admin/manager entregan; el resto, rechazo sin efectos."""

    def setUp(self):
        self.s = _scenario()
        self.order = _sales_order(self.s, status=Order.Status.READY_FOR_DELIVERY, reserve=True)

    def _assert_delivered(self, response):
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Order.Status.DELIVERED)
        for product in (self.s.A, self.s.B):
            stock = _stock(self.s, product)
            self.assertEqual((stock.quantity, stock.reserved_quantity), (Decimal('9'), Decimal('0')))
        self.assertEqual(
            StockMovement.objects.filter(business=self.s.business, reason='order_delivery').count(), 2,
        )
        self.assertEqual(
            list(OrderHistory.objects.filter(order=self.order).values_list('action', 'from_status', 'to_status')),
            [('delivered', Order.Status.READY_FOR_DELIVERY, Order.Status.DELIVERED)],
        )

    def _assert_rejected_without_effects(self, response, expected_status, before, order=None):
        self.assertEqual(response.status_code, expected_status, getattr(response, 'data', response))
        self.assertEqual(_snapshot(self.s, order or self.order), before)

    def test_owner_admin_manager_can_deliver(self):
        for role in ('owner', 'admin', 'manager'):
            with self.subTest(role=role):
                self.s = _scenario()
                self.order = _sales_order(self.s, status=Order.Status.READY_FOR_DELIVERY, reserve=True)
                client = _login(_member(self.s, role), self.s.business)
                self._assert_delivered(_post(client, self.order, 'deliver'))

    def test_roles_without_permission_are_rejected_without_effects(self):
        for role in ('cashier', 'staff', 'viewer', 'analyst', 'contador'):
            with self.subTest(role=role):
                # Un negocio por rol: el plan ficticio limita los asientos.
                self.s = _scenario()
                self.order = _sales_order(self.s, status=Order.Status.READY_FOR_DELIVERY, reserve=True)
                before = _snapshot(self.s, self.order)
                client = _login(_member(self.s, role), self.s.business)
                response = _post(client, self.order, 'deliver')
                self._assert_rejected_without_effects(response, 403, before)
                self.assertEqual(response.data['detail'], 'No tenes permisos para operar este recurso.')

    def test_user_of_another_business_gets_404_without_effects(self):
        before = _snapshot(self.s, self.order)
        other = _scenario()
        outsider = _member(other, 'owner', business=other.business)
        # Con su propio negocio activo: el pedido no está en su queryset.
        client = _login(outsider, other.business)
        self._assert_rejected_without_effects(_post(client, self.order, 'deliver'), 404, before)
        # Pidiendo el negocio ajeno: sin membership allí, el contexto cae en el
        # propio y el pedido sigue fuera de alcance.
        client = _login(outsider, self.s.business)
        self._assert_rejected_without_effects(_post(client, self.order, 'deliver'), 404, before)

    def test_anonymous_request_is_rejected_without_effects(self):
        before = _snapshot(self.s, self.order)
        client = APIClient()
        client.credentials(HTTP_X_BUSINESS_ID=str(self.s.business.pk))
        response = _post(client, self.order, 'deliver')
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(_snapshot(self.s, self.order), before)

    def test_role_editor_override_grants_and_revokes_deliver(self):
        RolePermissionOverride.objects.create(
            business=self.s.business, service='gestion', role='cashier', permission='deliver_orders', enabled=True,
        )
        RolePermissionOverride.objects.create(
            business=self.s.business, service='gestion', role='manager', permission='deliver_orders', enabled=False,
        )
        before = _snapshot(self.s, self.order)
        manager = _login(_member(self.s, 'manager'), self.s.business)
        self._assert_rejected_without_effects(_post(manager, self.order, 'deliver'), 403, before)
        cashier = _login(_member(self.s, 'cashier'), self.s.business)
        self._assert_delivered(_post(cashier, self.order, 'deliver'))

    def test_stage_actions_require_change_order_status(self):
        # staff tiene change_order_status (y no deliver_orders); viewer, ninguno.
        order = _sales_order(self.s, status=Order.Status.CONFIRMED, reserve=True)
        viewer = _login(_member(self.s, 'viewer'), self.s.business)
        before = _snapshot(self.s, order)
        for action in ('mark_in_preparation', 'mark_ready'):
            self._assert_rejected_without_effects(_post(viewer, order, action), 403, before, order)
        staff = _login(_member(self.s, 'staff'), self.s.business)
        self.assertEqual(_post(staff, order, 'mark_in_preparation').status_code, 200)
        self.assertEqual(_post(staff, order, 'mark_ready').status_code, 200)
        before = _snapshot(self.s, order)
        self._assert_rejected_without_effects(_post(staff, order, 'deliver'), 403, before, order)

    def test_capability_is_registered_for_the_role_editor(self):
        codes = {cap.code for cap in get_registry().get_by_service('gestion')}
        self.assertIn('deliver_orders', codes)


@override_settings(CACHES=LOCMEM)
class OrderTransitionHttpTests(TestCase):

    def setUp(self):
        self.s = _scenario()
        self.client = _login(_member(self.s, 'owner'), self.s.business)

    def _ok(self, order, action, expected_status):
        response = _post(self.client, order, action)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], expected_status)
        return response

    def test_valid_path_until_delivery_with_identical_retries(self):
        order = _sales_order(self.s, status=Order.Status.DRAFT, quantity=Decimal('2'))

        self._ok(order, 'confirm', Order.Status.CONFIRMED)
        self.assertEqual(_snapshot(self.s, order)['stock'][self.s.A.pk], (Decimal('10'), Decimal('2')))

        for action, status in (
            ('mark_in_preparation', Order.Status.IN_PREPARATION),
            ('mark_ready', Order.Status.READY_FOR_DELIVERY),
        ):
            self._ok(order, action, status)
            after_first = _snapshot(self.s, order)
            # Reintento idéntico: 200, mismo pedido, nada nuevo.
            self._ok(order, action, status)
            self.assertEqual(_snapshot(self.s, order), after_first)

        self._ok(order, 'deliver', Order.Status.DELIVERED)
        delivered = _snapshot(self.s, order)
        self._ok(order, 'deliver', Order.Status.DELIVERED)
        self.assertEqual(_snapshot(self.s, order), delivered)

        for product in (self.s.A, self.s.B):
            self.assertEqual(delivered['stock'][product.pk], (Decimal('8'), Decimal('0')))
        self.assertEqual(
            sorted(StockMovement.objects.filter(business=self.s.business).values_list('reason', 'quantity')),
            [('order_delivery', Decimal('2')), ('order_delivery', Decimal('2'))],
        )
        self.assertEqual({(r, d) for _, r, d in delivered['items']}, {(Decimal('0'), Decimal('2'))})
        self.assertEqual(delivered['history'], [
            ('confirmed', Order.Status.DRAFT, Order.Status.CONFIRMED),
            ('in_preparation', Order.Status.CONFIRMED, Order.Status.IN_PREPARATION),
            ('ready', Order.Status.IN_PREPARATION, Order.Status.READY_FOR_DELIVERY),
            ('delivered', Order.Status.READY_FOR_DELIVERY, Order.Status.DELIVERED),
        ])

    def test_shortcuts_kept_by_the_current_ui(self):
        # La UI ofrece "Entregar" desde confirmado y "Listo" saltea preparación.
        order = _sales_order(self.s, status=Order.Status.CONFIRMED, reserve=True)
        self._ok(order, 'deliver', Order.Status.DELIVERED)
        order = _sales_order(self.s, status=Order.Status.CONFIRMED, reserve=True)
        self._ok(order, 'mark_ready', Order.Status.READY_FOR_DELIVERY)
        order = _sales_order(self.s, status=Order.Status.IN_PREPARATION, reserve=True)
        self._ok(order, 'deliver', Order.Status.DELIVERED)

    def _assert_rejected(self, order, action, message):
        before = _snapshot(self.s, order)
        response = _post(self.client, order, action)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data, {'error': message})
        self.assertEqual(_snapshot(self.s, order), before)

    def test_cancelled_order_cannot_reenter_the_flow(self):
        order = _sales_order(self.s, status=Order.Status.CONFIRMED, reserve=True)
        self._ok(order, 'cancel', Order.Status.CANCELLED)
        self.assertEqual(_snapshot(self.s, order)['stock'][self.s.A.pk], (Decimal('10'), Decimal('0')))
        self._assert_rejected(order, 'mark_in_preparation', 'Debe estar confirmado')
        self._assert_rejected(order, 'mark_ready', 'Debe estar confirmado o en preparación')
        self._assert_rejected(order, 'deliver', 'No se puede entregar un pedido cancelado')
        self.assertFalse(StockMovement.objects.filter(business=self.s.business).exists())
        self.assertEqual(_snapshot(self.s, order)['history'], [
            ('cancelled', Order.Status.CONFIRMED, Order.Status.CANCELLED),
        ])

    def test_delivered_order_cannot_go_back(self):
        order = _sales_order(self.s, status=Order.Status.READY_FOR_DELIVERY, reserve=True)
        self._ok(order, 'deliver', Order.Status.DELIVERED)
        self._assert_rejected(order, 'mark_in_preparation', 'Debe estar confirmado')
        self._assert_rejected(order, 'mark_ready', 'Debe estar confirmado o en preparación')
        self._assert_rejected(order, 'cancel', 'No se puede cancelar un pedido entregado')
        self.assertEqual(StockMovement.objects.filter(business=self.s.business).count(), 2)
        self.assertEqual(len(_snapshot(self.s, order)['history']), 1)

    def test_unconfirmed_order_cannot_skip_confirmation(self):
        for status in (Order.Status.DRAFT, Order.Status.PENDING_CONFIRMATION):
            with self.subTest(status=status):
                order = _sales_order(self.s, status=status)
                self._assert_rejected(order, 'mark_in_preparation', 'Debe estar confirmado')
                self._assert_rejected(order, 'mark_ready', 'Debe estar confirmado o en preparación')
                self._assert_rejected(order, 'deliver', 'Debe estar confirmado')
        order = _sales_order(self.s, status=Order.Status.READY_FOR_DELIVERY, reserve=True)
        self._assert_rejected(order, 'mark_in_preparation', 'Debe estar confirmado')

    def test_patch_cannot_change_status(self):
        order = _sales_order(self.s, status=Order.Status.CONFIRMED, reserve=True)
        self._ok(order, 'cancel', Order.Status.CANCELLED)
        before = _snapshot(self.s, order)
        response = self.client.patch(
            f'/api/v1/sales/orders/{order.pk}/', {'status': Order.Status.CONFIRMED}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Order.Status.CANCELLED)
        self.assertEqual(_snapshot(self.s, order), before)


@override_settings(CACHES=LOCMEM)
class OrderDeliverInsufficientStockHttpTests(TestCase):
    """Un renglón posterior sin saldo: la entrega se revierte completa."""

    def setUp(self):
        self.s = _scenario()
        self.client = _login(_member(self.s, 'manager'), self.s.business)
        # Reserva previa de otro pedido sobre ambos productos: debe quedar intacta.
        self.other = _sales_order(self.s, status=Order.Status.CONFIRMED, reserve=True)

    def test_later_line_without_stock_rolls_back_everything(self):
        order = _sales_order(self.s, status=Order.Status.READY_FOR_DELIVERY, reserve=True, quantity=Decimal('4'))
        lines = list(order.items.select_related('product'))  # mismo orden que la vista
        first, later = lines[0], lines[1]
        # El renglón posterior quedó sin saldo físico (p. ej. ajuste de inventario).
        stock = _stock(self.s, later.product)
        stock.quantity = Decimal('3')
        stock.save(update_fields=['quantity', 'updated_at'])
        before = _snapshot(self.s, order)
        other_before = _snapshot(self.s, self.other)

        calls = []

        def spy(**kwargs):
            calls.append(kwargs['product'].pk)
            result = register_stock_movement(**kwargs)
            # El primer renglón llegó a escribir su salida antes del fallo.
            if len(calls) == 1:
                self.assertEqual(_stock(self.s, first.product).quantity, Decimal('6'))
            return result

        with patch.object(sales_views, 'register_stock_movement', side_effect=spy):
            response = _post(self.client, order, 'deliver')

        self.assertEqual(calls, [first.product_id, later.product_id])
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data, {
            'error': f'No hay stock suficiente para entregar "{later.name_snapshot}". No se aplicó ningún cambio.',
            'code': 'insufficient_stock',
            'item_id': str(later.pk),
        })
        self.assertEqual(_snapshot(self.s, order), before)
        self.assertEqual(_snapshot(self.s, self.other), other_before)
        self.assertEqual(before['status'], Order.Status.READY_FOR_DELIVERY)
        self.assertEqual(before['stock'][first.product_id], (Decimal('10'), Decimal('5')))
        self.assertFalse(StockMovement.objects.filter(business=self.s.business, reason='order_delivery').exists())

        # Repuesto el saldo, la misma entrega se completa.
        stock.quantity = Decimal('4')
        stock.save(update_fields=['quantity', 'updated_at'])
        response = _post(self.client, order, 'deliver')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Order.Status.DELIVERED)

    def test_unexpected_database_error_hides_internal_text(self):
        from django.db import OperationalError

        order = _sales_order(self.s, status=Order.Status.CONFIRMED, reserve=True)
        before = _snapshot(self.s, order)
        calls = []

        def failing(**kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise OperationalError('deadlock detected\nDETAIL:  relation "inventory_productstock"')
            return register_stock_movement(**kwargs)

        with patch.object(sales_views, 'register_stock_movement', side_effect=failing), \
                self.assertLogs('apps.sales.views', level='ERROR'):
            response = _post(self.client, order, 'deliver')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'error': 'No pudimos registrar la entrega del pedido. No se aplicó ningún cambio.'})
        self.assertEqual(_snapshot(self.s, order), before)


@skipUnless(connection.vendor == 'postgresql', 'Requiere PostgreSQL: pg_blocking_pids.')
@override_settings(CACHES=LOCMEM)
class OrderCancelReadyRaceHttpTests(TransactionTestCase):
    """Cancelar y marcar listo en paralelo, por HTTP real con solapamiento probado."""

    _fixture_teardown = pr32.StockDocumentTransitionRaceTests._fixture_teardown
    _race = pr32.StockDocumentTransitionRaceTests._race

    def _http(self, s, user, order, action):
        # Un APIClient con su propio login por participante: el cliente de
        # pruebas no se comparte entre hilos.
        client = _login(user, s.business)

        def run():
            response = _post(client, order, action)
            if response.status_code == 200:
                return f"ok:{response.data['status']}"
            return f"http_{response.status_code}:{response.data.get('error')}"
        return run

    def _setup(self):
        s = _scenario()
        user = _member(s, 'owner')
        order = _sales_order(s, status=Order.Status.IN_PREPARATION, reserve=True)
        return s, user, order

    @skipUnlessDBFeature('has_select_for_update')
    def test_cancel_then_concurrent_mark_ready_is_rejected(self):
        s, user, order = self._setup()
        run = self._race(
            self._http(s, user, order, 'cancel'), self._http(s, user, order, 'mark_ready'), pause_on=OrderHistory,
        )
        self.assertEqual(run.results, {
            'first': 'ok:cancelled',
            'second': 'http_400:Debe estar confirmado o en preparación',
        }, run)
        snap = _snapshot(s, order)
        self.assertEqual(snap['status'], Order.Status.CANCELLED)
        self.assertEqual({(r, d) for _, r, d in snap['items']}, {(Decimal('0'), Decimal('0'))})
        for product in (s.A, s.B):
            self.assertEqual(snap['stock'][product.pk], (Decimal('10'), Decimal('0')))
        self.assertEqual(snap['movements'], 0)
        self.assertEqual(snap['history'], [('cancelled', Order.Status.IN_PREPARATION, Order.Status.CANCELLED)])

    @skipUnlessDBFeature('has_select_for_update')
    def test_mark_ready_then_concurrent_cancel_releases_reservations(self):
        s, user, order = self._setup()
        run = self._race(
            self._http(s, user, order, 'mark_ready'), self._http(s, user, order, 'cancel'), pause_on=OrderHistory,
        )
        self.assertEqual(run.results, {'first': 'ok:ready_for_delivery', 'second': 'ok:cancelled'}, run)
        snap = _snapshot(s, order)
        self.assertEqual(snap['status'], Order.Status.CANCELLED)
        self.assertEqual({(r, d) for _, r, d in snap['items']}, {(Decimal('0'), Decimal('0'))})
        for product in (s.A, s.B):
            self.assertEqual(snap['stock'][product.pk], (Decimal('10'), Decimal('0')))
        self.assertEqual(snap['movements'], 0)
        self.assertEqual(snap['history'], [
            ('ready', Order.Status.IN_PREPARATION, Order.Status.READY_FOR_DELIVERY),
            ('cancelled', Order.Status.READY_FOR_DELIVERY, Order.Status.CANCELLED),
        ])

"""Timeline unificada de un `Customer` (CUSTOMER 04A/04B): Turnos + Ventas + Presupuestos + Pedidos.

Las entidades fuente siguen siendo la verdad: NO existe una tabla de eventos.
Cada consulta normaliza `Appointment` / `Sale` / `Quote` / `Order` (comercial,
`sales.Order`) a un contrato común:

  {type, id, source_id, occurred_at, title, subtitle, status, status_display,
   amount, currency, href, metadata}

Fecha canónica (`occurred_at`) por entidad:

- appointment → regla única de `customer_history.appointment_occurred_at`
  (CUSTOMER 04A.1): cancelado → `updated_at`, vencido → `expires_at`, resto
  → `start_at`. Se reutiliza el scope `history` de CUSTOMER 03: los turnos
  próximos que ocupan agenda quedan FUERA (se muestran aparte); pasados en
  cualquier estado y futuros cancelados/vencidos quedan DENTRO, fechados
  cuando ocurrió la cancelación/vencimiento.
- sale → `created_at`: la venta se registra completada en el mismo acto
  (`Sale.Status` = completed|cancelled, sin fecha de cierre separada). Una
  venta anulada conserva su fecha original (`cancelled_at` va en metadata).
  Si la venta tiene factura (`Invoice` OneToOne) va en `metadata.invoice`: el
  mismo dato que ya expone el detalle de venta con `view_sales`.
- quote → `created_at` (emisión: el número P-XXXXXX se asigna al crearlo).
  `sent_at` es opcional/nullable y va en metadata.
- order → `order_date` (CUSTOMER 04B), la fecha de negocio del pedido. Es un
  `DateField` NOT NULL (sin hora): al crear toma la fecha de hoy (no se
  recibe en el alta) y solo cambia si se edita el pedido. Para ubicarlo en la
  línea de tiempo: si `order_date` coincide con el día local (zona del
  Business) de `created_at` → ese instante exacto (mantiene el orden dentro
  del día); si fue editada → 00:00 de `order_date` en la zona del Business.
  Siempre cae en el día de `order_date`. Los cancelados (`status=cancelled`,
  que además setea `deleted_at`) se incluyen igual que en el listado de
  pedidos; no hay otro borrado lógico.

Qué fuentes entran lo decide la vista (módulos del Business + RBAC por
fuente); este módulo solo recibe la lista de `types` ya autorizada.

Paginación (limit/offset, orden global: `occurred_at` desc, luego tipo, luego
pk desc — determinista):
1. por cada fuente se trae solo `(pk, fecha)` de las primeras
   `offset + limit` filas en el MISMO orden (índices por business/fecha);
2. se mergean/ordenan esas claves en memoria y se corta la página;
3. se cargan completas solo las ≤ `limit` filas de la página.
Como el orden por fuente coincide con el global, el top-(offset+limit) global
siempre está en la unión de los top-(offset+limit) por fuente. Costo de claves
lineal en `offset` (aceptable para una ficha; ver `TIMELINE_MAX_OFFSET`).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from zoneinfo import ZoneInfo

from django.db.models import Case, Count, DateTimeField, F, Func, QuerySet, Value, When
from django.db.models.functions import TruncDate

from apps.sales.models import Order, Quote, Sale

TYPE_APPOINTMENT = 'appointment'
TYPE_SALE = 'sale'
TYPE_QUOTE = 'quote'
TYPE_ORDER = 'order'
TIMELINE_TYPES = (TYPE_APPOINTMENT, TYPE_SALE, TYPE_QUOTE, TYPE_ORDER)

# Desempate estable entre tipos con el mismo `occurred_at` (mayor = primero).
_TYPE_RANK = {TYPE_APPOINTMENT: 4, TYPE_SALE: 3, TYPE_ORDER: 2, TYPE_QUOTE: 1}

# Tope del offset: la ficha pagina de a pocos; evita ventanas de claves enormes.
TIMELINE_MAX_OFFSET = 5000

DEFAULT_TIMEZONE = 'America/Argentina/Buenos_Aires'


# ── Fuentes: queryset base ordenado + campo de fecha canónica ────────────────

def _appointments_qs(customer, now, tz) -> QuerySet:
  from apps.appointments.services.customer_history import SCOPE_HISTORY, scoped_customer_appointments

  return scoped_customer_appointments(customer, SCOPE_HISTORY, now=now)


def _sales_qs(customer, now, tz) -> QuerySet:
  return Sale.objects.filter(business_id=customer.business_id, customer=customer).order_by('-created_at', '-pk')


def _quotes_qs(customer, now, tz) -> QuerySet:
  return Quote.objects.filter(
    business_id=customer.business_id, customer=customer, is_deleted=False,
  ).order_by('-created_at', '-pk')


class _LocalMidnight(Func):
  """00:00 de una fecha en la zona `tzname`, como instante (timestamptz)."""
  output_field = DateTimeField()

  def __init__(self, date_expression, tzname: str):
    super().__init__(date_expression, Value(tzname))

  def as_sql(self, compiler, connection, **extra_context):
    date_sql, date_params = compiler.compile(self.source_expressions[0])
    tz_sql, tz_params = compiler.compile(self.source_expressions[1])
    return f'(({date_sql})::timestamp AT TIME ZONE {tz_sql})', [*date_params, *tz_params]


def _orders_qs(customer, now, tz) -> QuerySet:
  # `occurred_at` desde `order_date` (ver docstring del módulo).
  return Order.objects.filter(business_id=customer.business_id, customer=customer).annotate(
    occurred_at=Case(
      When(order_date=TruncDate('created_at', tzinfo=tz), then=F('created_at')),
      default=_LocalMidnight(F('order_date'), tz.key),
      output_field=DateTimeField(),
    ),
  ).order_by('-occurred_at', '-pk')


_SOURCES = {
  TYPE_APPOINTMENT: (_appointments_qs, 'occurred_at'),  # anotado por customer_history
  TYPE_SALE: (_sales_qs, 'created_at'),
  TYPE_QUOTE: (_quotes_qs, 'created_at'),
  TYPE_ORDER: (_orders_qs, 'occurred_at'),  # anotado desde order_date
}


# ── Serialización por tipo ───────────────────────────────────────────────────

def _money(value) -> str:
  return f'{value:.2f}'


def _serialize_appointment(appointment, *, now, tz) -> dict:
  from apps.appointments.services.customer_history import serialize_history_item

  item = serialize_history_item(appointment, now=now)
  local_day = appointment.start_at.astimezone(tz).date().isoformat()
  return {
    'type': TYPE_APPOINTMENT,
    'id': f'{TYPE_APPOINTMENT}:{appointment.pk}',
    'source_id': str(appointment.pk),
    'occurred_at': item['occurred_at'],
    'title': appointment.service_name,
    'subtitle': item['professional_name'],
    'status': item['status'],
    'status_display': item['status_display'],
    'amount': item['service_price'] if appointment.service_price and appointment.service_price > 0 else None,
    'currency': None,
    # Deep link existente de la agenda (Slice 6D): día en la zona del Business.
    'href': f'/app/turnos/turnos?date={local_day}&appointment={appointment.pk}',
    'metadata': item,
  }


def _serialize_sale(sale: Sale, **_) -> dict:
  items_count = getattr(sale, 'items_count', None)
  return {
    'type': TYPE_SALE,
    'id': f'{TYPE_SALE}:{sale.pk}',
    'source_id': str(sale.pk),
    'occurred_at': sale.created_at.isoformat(),
    'title': f'Venta #{sale.number}',
    'subtitle': sale.get_payment_method_display(),
    'status': sale.status,
    'status_display': sale.get_status_display(),
    'amount': _money(sale.total),
    'currency': None,  # Sale no tiene moneda propia
    'href': f'/app/gestion/ventas/{sale.pk}',
    'metadata': {
      'number': sale.number,
      'items_count': items_count,
      'payment_method': sale.payment_method,
      'payment_method_display': sale.get_payment_method_display(),
      'cancelled_at': sale.cancelled_at.isoformat() if sale.cancelled_at else None,
      'invoice': _sale_invoice(sale),
    },
  }


def _sale_invoice(sale: Sale) -> dict | None:
  # `select_related('invoice')` en `_load_page_objects`: sin consultas extra.
  from apps.invoices.models import Invoice

  try:
    invoice = sale.invoice
  except Invoice.DoesNotExist:
    return None
  return {
    'id': str(invoice.pk),
    'full_number': invoice.full_number,
    'status': invoice.status,
    'status_display': invoice.get_status_display(),
  }


def _serialize_quote(quote: Quote, **_) -> dict:
  items_count = getattr(quote, 'items_count', None)
  return {
    'type': TYPE_QUOTE,
    'id': f'{TYPE_QUOTE}:{quote.pk}',
    'source_id': str(quote.pk),
    'occurred_at': quote.created_at.isoformat(),
    'title': f'Presupuesto {quote.number}',
    'subtitle': None,
    'status': quote.status,
    'status_display': quote.get_status_display(),
    'amount': _money(quote.total),
    'currency': quote.currency or None,
    'href': f'/app/gestion/ventas/presupuestos/{quote.pk}',
    'metadata': {
      'number': quote.number,
      'items_count': items_count,
      'valid_until': quote.valid_until.isoformat() if quote.valid_until else None,
      'sent_at': quote.sent_at.isoformat() if quote.sent_at else None,
    },
  }


def _serialize_order(order: Order, **_) -> dict:
  items_count = getattr(order, 'items_count', None)
  return {
    'type': TYPE_ORDER,
    'id': f'{TYPE_ORDER}:{order.pk}',
    'source_id': str(order.pk),
    'occurred_at': order.occurred_at.isoformat(),
    'title': f'Pedido {order.number}',
    'subtitle': None,
    'status': order.status,
    'status_display': order.get_status_display(),
    'amount': _money(order.total),
    'currency': None,  # Order no tiene moneda propia
    'href': f'/app/gestion/ventas/pedidos/{order.pk}',
    'metadata': {
      'number': order.number,
      'items_count': items_count,
      'order_date': order.order_date.isoformat(),
      'estimated_delivery_date': (
        order.estimated_delivery_date.isoformat() if order.estimated_delivery_date else None
      ),
      'payment_status': order.payment_status,
      'payment_status_display': order.get_payment_status_display(),
      'total_paid': _money(order.total_paid),
      'pending_balance': _money(order.pending_balance),
    },
  }


def _load_page_objects(source_type: str, customer, pks, now, tz) -> dict:
  """Carga completas solo las filas de la página (siempre acotadas al Business)."""
  base_qs, _ = _SOURCES[source_type]
  qs = base_qs(customer, now, tz).filter(pk__in=pks)
  if source_type in (TYPE_SALE, TYPE_QUOTE, TYPE_ORDER):
    qs = qs.annotate(items_count=Count('items'))
  if source_type == TYPE_SALE:
    qs = qs.select_related('invoice')
  return {str(obj.pk): obj for obj in qs}


_SERIALIZERS = {
  TYPE_APPOINTMENT: _serialize_appointment,
  TYPE_SALE: _serialize_sale,
  TYPE_QUOTE: _serialize_quote,
  TYPE_ORDER: _serialize_order,
}


def build_customer_timeline(customer, types, *, offset: int, limit: int, now, timezone_name: str | None = None):
  """Devuelve `(count, events)` de la página pedida para las fuentes `types`."""
  tz = ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
  window = offset + limit
  count = 0
  keys: list[tuple[dt.datetime, int, str, str]] = []
  for source_type in types:
    base_qs, date_field = _SOURCES[source_type]
    qs = base_qs(customer, now, tz).select_related(None).prefetch_related(None)
    count += qs.count()
    if window <= 0:
      continue
    for pk, occurred_at in qs.values_list('pk', date_field)[:window]:
      keys.append((occurred_at, _TYPE_RANK[source_type], str(pk), source_type))

  keys.sort(reverse=True)
  page = keys[offset:window]

  pks_by_type: dict[str, list] = defaultdict(list)
  for _, _, pk, source_type in page:
    pks_by_type[source_type].append(pk)
  objects = {
    source_type: _load_page_objects(source_type, customer, pks, now, tz)
    for source_type, pks in pks_by_type.items()
  }

  events = []
  for _, _, pk, source_type in page:
    obj = objects[source_type].get(pk)
    if obj is None:  # borrado entre las dos consultas
      continue
    events.append(_SERIALIZERS[source_type](obj, now=now, tz=tz))
  return count, events

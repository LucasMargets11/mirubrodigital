from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone as dj_timezone
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.access import resolve_business_context
from apps.accounts.permissions import HasBusinessMembership, HasPermission, HasEntitlement, request_has_permission
from apps.business.entitlements import CUSTOMER_CORE_ENTITLEMENTS
from apps.sales.models import Quote, Sale
from apps.sales.quote_serializers import QuoteListSerializer
from apps.sales.serializers import SaleListSerializer
from apps.sales.views import _annotate_payments_totals
from .models import Customer, CustomerContactPreferences, CustomerMessageDelivery, CustomerNote, CustomerReminder
from .serializers import CustomerContactPreferencesSerializer, CustomerMessageDeliverySerializer, CustomerNoteSerializer, CustomerReminderSerializer, CustomerSerializer


class CustomerPagination(LimitOffsetPagination):
	default_limit = 25
	max_limit = 100
	limit_query_param = 'limit'
	offset_query_param = 'offset'


def _business_has_appointments(request) -> bool:
  membership = getattr(request, 'membership', None)
  if membership is None:
    return False
  context = resolve_business_context(request, membership)
  return 'appointments' in (context.get('enabled_services') or [])


def _includes_appointments_summary(request) -> bool:
  """`appointments_summary` solo para negocios con Turnos y roles que ven turnos."""
  return _business_has_appointments(request) and request_has_permission(request, 'view_appointments')


class CanViewCustomerAppointments(BasePermission):
  """Historial de Turnos: el Business tiene Turnos y el rol ve turnos.

  Se suma a `HasPermission` (`view_customers`): hacen falta AMBOS permisos.
  """
  message = {
    'code': 'appointments_access_required',
    'message': 'Tu rol o tu plan no incluye ver los turnos del cliente.',
  }

  def has_permission(self, request, view) -> bool:
    return _includes_appointments_summary(request)


def _business_entitlements(request) -> set:
  business = getattr(request, 'business', None)
  if business is None:
    return set()
  cached = getattr(request, '_customer_timeline_entitlements', None)
  if cached is None:
    from apps.billing.runtime import resolve_subscription
    cached = set(resolve_subscription(business).entitlements or ())
    request._customer_timeline_entitlements = cached
  return cached


def timeline_allowed_types(request) -> list[str]:
  """Fuentes de la timeline que este request puede ver (CUSTOMER 04A).

  Cada fuente exige el módulo del Business Y el permiso RBAC de esa fuente,
  igual que su endpoint dedicado; la timeline nunca es un bypass:

  - appointment: Business con Turnos + `view_appointments`
    (= `CanViewCustomerAppointments` / `appointments_summary`).
  - sale: entitlement `gestion.customers` + `view_sales`
    (= `/customers/{id}/sales/`).
  - quote: entitlements `gestion.customers` + `gestion.quotes` + `view_quotes`
    (= `/customers/{id}/quotes/` + el flag `quotes` del plan).
  - order (CUSTOMER 04B): entitlements `gestion.customers` + `gestion.orders`
    + `view_orders` (= `/sales/orders/` + el módulo Pedidos del plan).
  """
  from .timeline import TYPE_APPOINTMENT, TYPE_ORDER, TYPE_QUOTE, TYPE_SALE

  allowed: list[str] = []
  if _includes_appointments_summary(request):
    allowed.append(TYPE_APPOINTMENT)
  entitlements = _business_entitlements(request)
  if 'gestion.customers' in entitlements:
    if request_has_permission(request, 'view_sales'):
      allowed.append(TYPE_SALE)
    if 'gestion.quotes' in entitlements and request_has_permission(request, 'view_quotes'):
      allowed.append(TYPE_QUOTE)
    if 'gestion.orders' in entitlements and request_has_permission(request, 'view_orders'):
      allowed.append(TYPE_ORDER)
  return allowed


class CanViewCustomerTimeline(BasePermission):
  """Al menos una fuente de la timeline visible; si no, 403 (no lista vacía falsa)."""
  message = {
    'code': 'timeline_access_required',
    'message': 'Tu rol o tu plan no incluye ver la actividad del cliente.',
  }

  def has_permission(self, request, view) -> bool:
    return bool(timeline_allowed_types(request))


class CustomerListCreateView(generics.ListCreateAPIView):
  serializer_class = CustomerSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = CUSTOMER_CORE_ENTITLEMENTS
  permission_map = {
    'GET': 'view_customers',
    'POST': ('manage_customers', 'create_sales'),
  }
  pagination_class = CustomerPagination
  filter_backends = [SearchFilter]
  search_fields = ['name', 'doc_number', 'email', 'phone', 'note']

  def get_queryset(self):
    business = getattr(self.request, 'business')
    queryset = Customer.objects.filter(business=business)

    include_inactive = self.request.query_params.get('include_inactive', 'false').lower() == 'true'
    if not include_inactive:
      queryset = queryset.filter(is_active=True)

    return queryset.order_by('name')

  def perform_create(self, serializer):
    serializer.save(business=self.request.business)


class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
  serializer_class = CustomerSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = CUSTOMER_CORE_ENTITLEMENTS
  permission_map = {
    'GET': 'view_customers',
    'PUT': 'manage_customers',
    'PATCH': 'manage_customers',
    'DELETE': 'manage_customers',
  }

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return Customer.objects.filter(business=business)

  def retrieve(self, request, *args, **kwargs):
    instance = self.get_object()
    data = self.get_serializer(instance).data
    if _includes_appointments_summary(request):
      from apps.appointments.services.customer_summary import build_customer_appointments_summary
      data['appointments_summary'] = build_customer_appointments_summary(instance)
    return Response(data)

  def perform_destroy(self, instance):
    if instance.is_active:
      instance.is_active = False
      instance.save(update_fields=['is_active', 'updated_at'])


class CustomerSalesView(generics.ListAPIView):
  """GET /api/v1/customers/{pk}/sales/ — ventas del cliente paginadas."""
  serializer_class = SaleListSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.customers'
  permission_map = {'GET': 'view_sales'}
  pagination_class = CustomerPagination

  def get_queryset(self):
    business = getattr(self.request, 'business')
    customer = get_object_or_404(Customer, pk=self.kwargs['pk'], business=business)
    qs = (
      Sale.objects.filter(business=business, customer=customer)
      .select_related('customer', 'invoice')
      .annotate(items_count=Count('items'))
      .order_by('-created_at', '-number')
    )
    return _annotate_payments_totals(qs)


class CustomerQuotesView(generics.ListAPIView):
  """GET /api/v1/customers/{pk}/quotes/ — presupuestos del cliente paginados."""
  serializer_class = QuoteListSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = 'gestion.customers'
  permission_map = {'GET': 'view_quotes'}
  pagination_class = CustomerPagination

  def get_queryset(self):
    business = getattr(self.request, 'business')
    customer = get_object_or_404(Customer, pk=self.kwargs['pk'], business=business)
    return (
      Quote.objects.filter(business=business, customer=customer, is_deleted=False)
      .select_related('customer')
      .annotate(items_count=Count('items'))
      .order_by('-created_at', '-number')
    )



class CustomerAppointmentsView(generics.ListAPIView):
  """GET /api/v1/customers/{pk}/appointments/?scope=upcoming|history|all (Turnos CUSTOMER 03).

  Feed paginado (limit/offset) derivado de `Appointment.customer`; la partición
  y el formato viven en `appointments/services/customer_history.py`.
  """
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission, CanViewCustomerAppointments]
  required_entitlement = CUSTOMER_CORE_ENTITLEMENTS
  permission_map = {'GET': 'view_customers'}
  pagination_class = CustomerPagination

  def get_queryset(self):
    from apps.appointments.services.customer_history import SCOPE_ALL, SCOPES, scoped_customer_appointments

    business = getattr(self.request, 'business')
    customer = get_object_or_404(Customer, pk=self.kwargs['pk'], business=business)
    scope = self.request.query_params.get('scope') or SCOPE_ALL
    if scope not in SCOPES:
      raise ValidationError({'scope': f"Valor inválido. Opciones: {', '.join(SCOPES)}."})
    self._now = dj_timezone.now()
    return scoped_customer_appointments(customer, scope, now=self._now)

  def list(self, request, *args, **kwargs):
    from apps.appointments.services.customer_history import serialize_history_item

    queryset = self.get_queryset()
    page = self.paginate_queryset(queryset)
    rows = page if page is not None else list(queryset)
    data = [serialize_history_item(appt, now=self._now) for appt in rows]
    if page is not None:
      return self.get_paginated_response(data)
    return Response(data)


class CustomerTimelineView(generics.GenericAPIView):
  """GET /api/v1/customers/{pk}/timeline/?types=appointment,sale,quote,order&limit&offset (CUSTOMER 04A/04B).

  Historial unificado construido al consultar desde las entidades fuente
  (`customers/timeline.py`); nada se persiste. Solo incluye las fuentes que
  el Business tiene y el rol puede ver (`timeline_allowed_types`). `types`
  filtra dentro de esas; pedir solo fuentes no autorizadas → 403.
  """
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission, CanViewCustomerTimeline]
  required_entitlement = CUSTOMER_CORE_ENTITLEMENTS
  permission_map = {'GET': 'view_customers'}
  pagination_class = CustomerPagination

  def get(self, request, *args, **kwargs):
    from .timeline import TIMELINE_MAX_OFFSET, TIMELINE_TYPES, build_customer_timeline

    business = getattr(request, 'business')
    customer = get_object_or_404(Customer, pk=self.kwargs['pk'], business=business)

    allowed = timeline_allowed_types(request)
    raw_types = request.query_params.get('types')
    if raw_types:
      requested = [t.strip() for t in raw_types.split(',') if t.strip()]
      invalid = [t for t in requested if t not in TIMELINE_TYPES]
      if invalid or not requested:
        raise ValidationError({'types': f"Valor inválido. Opciones: {', '.join(TIMELINE_TYPES)}."})
      types = [t for t in TIMELINE_TYPES if t in requested and t in allowed]
      if not types:
        raise PermissionDenied(CanViewCustomerTimeline.message)
    else:
      types = [t for t in TIMELINE_TYPES if t in allowed]

    paginator = self.paginator
    paginator.request = request
    paginator.limit = paginator.get_limit(request)
    paginator.offset = min(paginator.get_offset(request), TIMELINE_MAX_OFFSET)
    count, events = build_customer_timeline(
      customer, types, offset=paginator.offset, limit=paginator.limit,
      now=dj_timezone.now(), timezone_name=getattr(business, 'timezone', None),
    )
    paginator.count = count
    response = paginator.get_paginated_response(events)
    response.data['types'] = types
    return response


class _CustomerNotesMixin:
  """Notas internas del Customer (CUSTOMER 04C).

  Lectura `view_customers`; alta/edición/borrado `manage_customer_notes`
  (owner/admin/manager, CUSTOMER 04C.1), con el RBAC del servicio activo (sin
  bypass). `manage_customers` NO alcanza: cashier/staff lo tienen para POS. Todo se resuelve dentro del Business
  del request: Customer o nota de otro tenant → 404.
  """
  serializer_class = CustomerNoteSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = CUSTOMER_CORE_ENTITLEMENTS
  permission_map = {
    'GET': 'view_customers',
    'POST': 'manage_customer_notes',
    'PATCH': 'manage_customer_notes',
    'DELETE': 'manage_customer_notes',
  }

  def get_customer(self) -> Customer:
    if not hasattr(self, '_customer'):
      business = getattr(self.request, 'business')
      self._customer = get_object_or_404(Customer, pk=self.kwargs['pk'], business=business)
    return self._customer

  def get_queryset(self):
    customer = self.get_customer()
    return (
      CustomerNote.objects.filter(business=customer.business_id, customer=customer)
      .select_related('author')
      .order_by('-created_at', '-id')
    )


class CustomerNotesView(_CustomerNotesMixin, generics.ListCreateAPIView):
  """GET/POST /api/v1/customers/{pk}/notes/ — más recientes primero, paginado."""
  pagination_class = CustomerPagination

  def perform_create(self, serializer):
    customer = self.get_customer()
    serializer.save(business=customer.business, customer=customer, author=self.request.user)


class CustomerNoteDetailView(_CustomerNotesMixin, generics.RetrieveUpdateDestroyAPIView):
  """GET/PATCH/DELETE /api/v1/customers/{pk}/notes/{note_id}/ (sin PUT: solo `body` es editable)."""
  lookup_url_kwarg = 'note_id'
  http_method_names = ['get', 'patch', 'delete', 'head', 'options']


REMINDER_SCOPE_PENDING = 'pending'
REMINDER_SCOPE_CLOSED = 'closed'
REMINDER_SCOPE_ALL = 'all'
REMINDER_SCOPES = (REMINDER_SCOPE_PENDING, REMINDER_SCOPE_CLOSED, REMINDER_SCOPE_ALL)
_REMINDER_CLOSED_STATUSES = (CustomerReminder.Status.COMPLETED, CustomerReminder.Status.CANCELLED)


class _CustomerRemindersMixin:
  """Recordatorios internos del Customer (CUSTOMER 07A).

  Mismo esquema que las notas: lectura `view_customers`; alta/edición/
  completar/cancelar `manage_customer_reminders` (owner/admin/manager; NO
  `manage_customers`, que cashier/staff tienen para POS). Todo se resuelve
  dentro del Business del request: Customer o recordatorio ajeno → 404.
  Sin DELETE: cancelar conserva la trazabilidad.
  """
  serializer_class = CustomerReminderSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = CUSTOMER_CORE_ENTITLEMENTS
  permission_map = {
    'GET': 'view_customers',
    'POST': 'manage_customer_reminders',
    'PATCH': 'manage_customer_reminders',
    # No hay handler (405), pero sin permiso de escritura ni siquiera se llega ahí.
    'PUT': 'manage_customer_reminders',
    'DELETE': 'manage_customer_reminders',
  }

  def get_customer(self) -> Customer:
    if not hasattr(self, '_customer'):
      business = getattr(self.request, 'business')
      self._customer = get_object_or_404(Customer, pk=self.kwargs['pk'], business=business)
    return self._customer

  def get_serializer_context(self):
    context = super().get_serializer_context()
    context['customer'] = self.get_customer()
    context['now'] = getattr(self, '_now', None) or dj_timezone.now()
    return context

  def base_queryset(self):
    customer = self.get_customer()
    return (
      CustomerReminder.objects.filter(business=customer.business_id, customer=customer)
      .select_related('created_by', 'appointment')
    )

  def get_queryset(self):
    return self.base_queryset()


class CustomerRemindersView(_CustomerRemindersMixin, generics.ListCreateAPIView):
  """GET/POST /api/v1/customers/{pk}/reminders/?scope=pending|closed|all.

  - pending (default): los que faltan hacer, el más próximo primero (los
    vencidos quedan arriba).
  - closed: completados + cancelados, el más reciente primero.
  - all: pendientes primero y después los cerrados.
  La respuesta suma `counts: {pending, closed}` para la sección de la ficha.
  """
  pagination_class = CustomerPagination

  def get_scope(self) -> str:
    scope = self.request.query_params.get('scope') or REMINDER_SCOPE_PENDING
    if scope not in REMINDER_SCOPES:
      raise ValidationError({'scope': f"Valor inválido. Opciones: {', '.join(REMINDER_SCOPES)}."})
    return scope

  def get_queryset(self):
    from django.db.models import Case, IntegerField, Value, When

    qs = self.base_queryset()
    scope = self.get_scope()
    if scope == REMINDER_SCOPE_PENDING:
      return qs.filter(status=CustomerReminder.Status.PENDING).order_by('remind_at', 'id')
    if scope == REMINDER_SCOPE_CLOSED:
      return qs.filter(status__in=_REMINDER_CLOSED_STATUSES).order_by('-remind_at', '-id')
    return qs.annotate(
      _closed=Case(When(status=CustomerReminder.Status.PENDING, then=Value(0)), default=Value(1), output_field=IntegerField()),
    ).order_by('_closed', 'remind_at', 'id')

  def list(self, request, *args, **kwargs):
    self._now = dj_timezone.now()
    response = super().list(request, *args, **kwargs)
    totals = self.base_queryset().aggregate(
      pending=Count('id', filter=Q(status=CustomerReminder.Status.PENDING)),
      closed=Count('id', filter=Q(status__in=_REMINDER_CLOSED_STATUSES)),
    )
    if isinstance(response.data, dict):
      response.data['counts'] = totals
    return response

  def perform_create(self, serializer):
    customer = self.get_customer()
    serializer.save(business=customer.business, customer=customer, created_by=self.request.user)


class CustomerReminderDetailView(_CustomerRemindersMixin, generics.RetrieveUpdateAPIView):
  """GET/PATCH /api/v1/customers/{pk}/reminders/{reminder_id}/.

  Completar = PATCH {status: "completed"} (setea `completed_at`); cancelar =
  PATCH {status: "cancelled"}. Sin PUT ni DELETE.
  """
  lookup_url_kwarg = 'reminder_id'
  http_method_names = ['get', 'patch', 'head', 'options']


class CustomerContactPreferencesView(generics.GenericAPIView):
  """GET/PATCH /api/v1/customers/{pk}/contact-preferences/ (CUSTOMER 07D.1).

  Un solo recurso para todos los canales. Lectura `view_customers`; edición
  `manage_customer_contact_preferences` (owner/admin/manager; NO
  `manage_customers`, que cashier/staff tienen para POS). Customer de otro
  Business → 404. Sin fila devuelve los defaults sin crearla; el primer PATCH
  la crea. No envía nada: solo registra preferencias y consentimiento.
  """
  serializer_class = CustomerContactPreferencesSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = CUSTOMER_CORE_ENTITLEMENTS
  permission_map = {
    'GET': 'view_customers',
    'PATCH': 'manage_customer_contact_preferences',
    'PUT': 'manage_customer_contact_preferences',
  }
  http_method_names = ['get', 'patch', 'head', 'options']

  def get(self, request, *args, **kwargs):
    business = getattr(request, 'business')
    customer = get_object_or_404(Customer, pk=self.kwargs['pk'], business=business)
    prefs = CustomerContactPreferences.for_customer(customer)
    return Response(self.get_serializer(prefs).data)

  def patch(self, request, *args, **kwargs):
    business = getattr(request, 'business')
    with transaction.atomic():
      # Lock del Customer: serializa el primer PATCH (crea la fila OneToOne).
      customer = get_object_or_404(Customer.objects.select_for_update(), pk=self.kwargs['pk'], business=business)
      prefs = CustomerContactPreferences.for_customer(customer)
      serializer = self.get_serializer(prefs, data=request.data, partial=True)
      serializer.is_valid(raise_exception=True)
      serializer.save(updated_by=request.user)
    return Response(serializer.data)


class CustomerDeliveriesView(generics.ListAPIView):
  """GET /api/v1/customers/{pk}/deliveries/ (CUSTOMER 07D.2) — solo lectura.

  Historial/auditoría de comunicaciones externas, más recientes primero,
  paginado. Lectura `view_customers`; no hay alta/edición desde la API: los
  Deliveries los crean y ejecutan solo los servicios internos
  (`customers/deliveries.py`). Customer de otro Business → 404.
  """
  serializer_class = CustomerMessageDeliverySerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
  required_entitlement = CUSTOMER_CORE_ENTITLEMENTS
  permission_map = {'GET': 'view_customers'}
  pagination_class = CustomerPagination
  http_method_names = ['get', 'head', 'options']

  def get_queryset(self):
    business = getattr(self.request, 'business')
    customer = get_object_or_404(Customer, pk=self.kwargs['pk'], business=business)
    return CustomerMessageDelivery.objects.filter(business=business, customer=customer).order_by('-created_at', '-id')

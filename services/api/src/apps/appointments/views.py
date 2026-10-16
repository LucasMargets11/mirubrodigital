import datetime as dt

from django.db.models import Count, Q
from django.utils import timezone as dj_timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission, request_has_permission
from .models import (
  Appointment,
  AppointmentCategory,
  AppointmentException,
  AppointmentProfessional,
  AppointmentSchedule,
  AppointmentService,
)
from .serializers import (
  CommunicationAutomationSettingsSerializer,
  CustomerCommunicationSettingsSerializer,
  ReminderAutomationSettingsSerializer,
  AppointmentCategorySerializer,
  AppointmentExceptionSerializer,
  AppointmentProfessionalSerializer,
  AppointmentScheduleSerializer,
  AppointmentSerializer,
  AppointmentServiceSerializer,
)
from .services import admin_mutation
from .services.availability import AvailabilityError, compute_availability, resolve_business_timezone


def _filter_by_professional(queryset, request):
  professional_id = request.query_params.get('professional')
  if professional_id is None:
    return queryset
  if professional_id.lower() in ('null', 'business', ''):
    return queryset.filter(professional__isnull=True)
  return queryset.filter(professional_id=professional_id)


def _filter_by_effective_status(queryset, status_param):
  """Filtra por estado operativo efectivo (Slice 7B.3).

  Un `pending_payment` con el hold vencido cuenta como `expired` (misma
  regla que `Appointment.effective_status` / `AppointmentQuerySet.occupying`)
  aunque el job de expiración todavía no lo haya normalizado.
  """
  now = dj_timezone.now()
  if status_param == Appointment.Status.PENDING_PAYMENT:
    return queryset.filter(status=Appointment.Status.PENDING_PAYMENT, expires_at__gt=now)
  if status_param == Appointment.Status.EXPIRED:
    return queryset.filter(
      Q(status=Appointment.Status.EXPIRED)
      | Q(status=Appointment.Status.PENDING_PAYMENT, expires_at__lte=now)
    )
  return queryset.filter(status=status_param)


MAX_APPOINTMENT_RANGE_DAYS = 31


def _parse_date_range(query_params):
  """`date_from`/`date_to` (YYYY-MM-DD, inclusive) del listado de turnos (Slice 7D).

  Devuelve `(date_from, date_to)` o None si no se pidió rango. Los límites
  son días locales del Business (el caller los convierte con su timezone).
  Rango incompleto, inválido, invertido, mayor a MAX_APPOINTMENT_RANGE_DAYS
  o combinado con `date` → 400.
  """
  raw_from = query_params.get('date_from')
  raw_to = query_params.get('date_to')
  if raw_from is None and raw_to is None:
    return None
  if query_params.get('date'):
    raise ValidationError({'date': ['Usá `date` o `date_from`/`date_to`, no ambos.']})
  errors = {}
  parsed = {}
  for field, raw in (('date_from', raw_from), ('date_to', raw_to)):
    if not raw:
      errors[field] = ['Este parámetro es requerido.']
      continue
    try:
      parsed[field] = dt.date.fromisoformat(raw)
    except ValueError:
      errors[field] = ['Fecha inválida. Formato esperado YYYY-MM-DD.']
  if errors:
    raise ValidationError(errors)
  date_from, date_to = parsed['date_from'], parsed['date_to']
  if date_to < date_from:
    raise ValidationError({'date_to': ['Debe ser igual o posterior a `date_from`.']})
  if (date_to - date_from).days + 1 > MAX_APPOINTMENT_RANGE_DAYS:
    raise ValidationError({'date_to': [f'El rango máximo es de {MAX_APPOINTMENT_RANGE_DAYS} días.']})
  return date_from, date_to


class AppointmentCategoryListCreateView(generics.ListCreateAPIView):
  serializer_class = AppointmentCategorySerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'POST': 'manage_appointments',
  }
  pagination_class = None

  def get_queryset(self):
    business = getattr(self.request, 'business')
    queryset = AppointmentCategory.objects.filter(business=business)

    queryset = queryset.annotate(
      services_count=Count('services', filter=Q(services__is_active=True))
    )

    include_inactive = self.request.query_params.get('include_inactive', 'false').lower() == 'true'
    if not include_inactive:
      queryset = queryset.filter(is_active=True)

    search = self.request.query_params.get('search')
    if search:
      queryset = queryset.filter(name__icontains=search)

    return queryset.order_by('sort_order', 'name')

  def perform_create(self, serializer):
    serializer.save(business=self.request.business)


class AppointmentCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
  serializer_class = AppointmentCategorySerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'PUT': 'manage_appointments',
    'PATCH': 'manage_appointments',
    'DELETE': 'manage_appointments',
  }

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return AppointmentCategory.objects.filter(business=business).annotate(
      services_count=Count('services', filter=Q(services__is_active=True))
    )

  def perform_destroy(self, instance):
    # Soft delete: mark as inactive instead of deleting.
    instance.is_active = False
    instance.save(update_fields=['is_active', 'updated_at'])


class AppointmentServiceListCreateView(generics.ListCreateAPIView):
  serializer_class = AppointmentServiceSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'POST': 'manage_appointments',
  }
  pagination_class = None

  def get_queryset(self):
    business = getattr(self.request, 'business')
    queryset = AppointmentService.objects.filter(business=business).select_related('category')

    include_inactive = self.request.query_params.get('include_inactive', 'false').lower() == 'true'
    if not include_inactive:
      queryset = queryset.filter(is_active=True)

    category_id = self.request.query_params.get('category')
    if category_id is not None:
      if category_id.lower() == 'null' or category_id == '':
        queryset = queryset.filter(category__isnull=True)
      else:
        queryset = queryset.filter(category_id=category_id)

    search = self.request.query_params.get('search')
    if search:
      queryset = queryset.filter(name__icontains=search)

    return queryset.order_by('sort_order', 'name')

  def perform_create(self, serializer):
    serializer.save(business=self.request.business)


class AppointmentServiceDetailView(generics.RetrieveUpdateDestroyAPIView):
  serializer_class = AppointmentServiceSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'PUT': 'manage_appointments',
    'PATCH': 'manage_appointments',
    'DELETE': 'manage_appointments',
  }

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return AppointmentService.objects.filter(business=business).select_related('category')

  def perform_destroy(self, instance):
    instance.is_active = False
    instance.save(update_fields=['is_active', 'updated_at'])


class AppointmentProfessionalListCreateView(generics.ListCreateAPIView):
  serializer_class = AppointmentProfessionalSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'POST': 'manage_appointments',
  }
  pagination_class = None

  def get_queryset(self):
    business = getattr(self.request, 'business')
    queryset = AppointmentProfessional.objects.filter(business=business).prefetch_related('services')

    include_inactive = self.request.query_params.get('include_inactive', 'false').lower() == 'true'
    if not include_inactive:
      queryset = queryset.filter(is_active=True)

    search = self.request.query_params.get('search')
    if search:
      queryset = queryset.filter(name__icontains=search)

    return queryset.order_by('sort_order', 'name')

  def perform_create(self, serializer):
    serializer.save(business=self.request.business)


class AppointmentProfessionalDetailView(generics.RetrieveUpdateDestroyAPIView):
  serializer_class = AppointmentProfessionalSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'PUT': 'manage_appointments',
    'PATCH': 'manage_appointments',
    'DELETE': 'manage_appointments',
  }

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return AppointmentProfessional.objects.filter(business=business).prefetch_related('services')

  def perform_destroy(self, instance):
    instance.is_active = False
    instance.save(update_fields=['is_active', 'updated_at'])


class AppointmentScheduleListCreateView(generics.ListCreateAPIView):
  serializer_class = AppointmentScheduleSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'POST': 'manage_appointments',
  }
  pagination_class = None

  def get_queryset(self):
    business = getattr(self.request, 'business')
    queryset = AppointmentSchedule.objects.filter(business=business).select_related('professional')
    queryset = _filter_by_professional(queryset, self.request)
    return queryset.order_by('weekday', 'start_time')

  def perform_create(self, serializer):
    serializer.save(business=self.request.business)


class AppointmentScheduleDetailView(generics.RetrieveUpdateDestroyAPIView):
  serializer_class = AppointmentScheduleSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'PUT': 'manage_appointments',
    'PATCH': 'manage_appointments',
    'DELETE': 'manage_appointments',
  }

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return AppointmentSchedule.objects.filter(business=business).select_related('professional')


class AppointmentExceptionListCreateView(generics.ListCreateAPIView):
  serializer_class = AppointmentExceptionSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'POST': 'manage_appointments',
  }
  pagination_class = None

  def get_queryset(self):
    business = getattr(self.request, 'business')
    queryset = AppointmentException.objects.filter(business=business).select_related('professional')
    queryset = _filter_by_professional(queryset, self.request)
    return queryset.order_by('-date')

  def perform_create(self, serializer):
    serializer.save(business=self.request.business)


class AppointmentExceptionDetailView(generics.RetrieveUpdateDestroyAPIView):
  serializer_class = AppointmentExceptionSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'PUT': 'manage_appointments',
    'PATCH': 'manage_appointments',
    'DELETE': 'manage_appointments',
  }

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return AppointmentException.objects.filter(business=business).select_related('professional')


class AppointmentListCreateView(generics.ListCreateAPIView):
  serializer_class = AppointmentSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'POST': 'manage_appointments',
  }
  pagination_class = None

  def get_queryset(self):
    business = getattr(self.request, 'business')
    queryset = Appointment.objects.filter(business=business).select_related('service__category', 'professional').prefetch_related('payments')

    tzinfo = resolve_business_timezone(business)
    date_range = _parse_date_range(self.request.query_params)
    date_param = self.request.query_params.get('date')
    if date_range is not None:
      range_start = dt.datetime.combine(date_range[0], dt.time.min, tzinfo=tzinfo)
      range_end = dt.datetime.combine(date_range[1] + dt.timedelta(days=1), dt.time.min, tzinfo=tzinfo)
      queryset = queryset.filter(start_at__gte=range_start, start_at__lt=range_end)
    elif date_param:
      try:
        target_date = dt.date.fromisoformat(date_param)
      except ValueError:
        return queryset.none()
      day_start = dt.datetime.combine(target_date, dt.time.min, tzinfo=tzinfo)
      day_end = day_start + dt.timedelta(days=1)
      queryset = queryset.filter(start_at__gte=day_start, start_at__lt=day_end)

    queryset = _filter_by_professional(queryset, self.request)

    status_param = self.request.query_params.get('status')
    if status_param:
      queryset = _filter_by_effective_status(queryset, status_param)

    return queryset.order_by('start_at')

  def perform_create(self, serializer):
    serializer.save(business=self.request.business)


class AppointmentDetailView(generics.RetrieveUpdateDestroyAPIView):
  serializer_class = AppointmentSerializer
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {
    'GET': 'view_appointments',
    'PUT': 'manage_appointments',
    'PATCH': 'manage_appointments',
    'DELETE': 'manage_appointments',
  }

  def get_queryset(self):
    business = getattr(self.request, 'business')
    return Appointment.objects.filter(business=business).select_related('service__category', 'professional').prefetch_related('payments')

  def perform_destroy(self, instance):
    # Cancelar en vez de borrar físicamente: nunca se pierden turnos históricos
    # ni sus `AppointmentPayment` (sin refund automático). Bajo el mismo
    # protocolo de locks que el webhook de pago (Slice 6B.1).
    admin_mutation.cancel_appointment(business=instance.business, appointment_id=instance.pk)


class AppointmentAvailabilityView(APIView):
  """Disponibilidad real de turnos (Slice 3B).

  Devuelve los slots teóricos (horarios/excepciones) descontando los
  `Appointment` ya ocupantes para ese negocio/profesional/fecha.
  """
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
  permission_map = {'GET': 'view_appointments'}

  def get(self, request, *args, **kwargs):
    business = getattr(request, 'business')

    service_id = request.query_params.get('service')
    date_param = request.query_params.get('date')
    professional_id = request.query_params.get('professional') or None
    # Uso interno: permite que el flujo de edición/reprogramación no se
    # bloquee a sí mismo al recalcular disponibilidad.
    exclude_appointment_id = request.query_params.get('exclude_appointment_id') or None

    if not service_id:
      return Response({'service': ['Este parámetro es requerido.']}, status=status.HTTP_400_BAD_REQUEST)
    if not date_param:
      return Response({'date': ['Este parámetro es requerido.']}, status=status.HTTP_400_BAD_REQUEST)

    try:
      target_date = dt.date.fromisoformat(date_param)
    except ValueError:
      return Response(
        {'date': ['Fecha inválida. Formato esperado YYYY-MM-DD.']},
        status=status.HTTP_400_BAD_REQUEST,
      )

    try:
      result = compute_availability(
        business=business,
        service_id=service_id,
        target_date=target_date,
        professional_id=professional_id,
        exclude_appointment_id=exclude_appointment_id,
      )
    except AvailabilityError as exc:
      field_name = exc.field or 'detail'
      return Response({field_name: [exc.message]}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
      'date': result.date.isoformat(),
      'service': str(result.service.id),
      'professional': str(result.professional.id) if result.professional else None,
      'slots': [slot.to_dict() for slot in result.slots],
    })


class _HasTurnosAccess(BasePermission):
  """El rol ve Turnos (`view_appointments`, solo existe en el servicio Turnos).
  Se suma a `HasPermission`: `manage_settings` solo no alcanza (Gestión lo tiene)."""

  def has_permission(self, request, view) -> bool:
    return request_has_permission(request, 'view_appointments')


class ReminderAutomationSettingsView(APIView):
  """GET/PATCH /api/v1/appointments/reminder-automation/ (CUSTOMER 07B).

  Recordatorios internos automáticos del Business; nunca se envían al cliente.
  Lectura: `manage_settings` (owner/admin/manager de Turnos). Escritura:
  `manage_reminder_automations` (solo owner/admin). Sin fila → defaults
  apagados; la fila se crea recién en el primer PATCH.
  """
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission, _HasTurnosAccess]
  permission_map = {
    'GET': 'manage_settings',
    'PATCH': 'manage_reminder_automations',
    'PUT': 'manage_reminder_automations',
  }
  http_method_names = ['get', 'patch', 'head', 'options']

  def get(self, request):
    from apps.customers.models import CustomerReminderAutomationSettings

    settings_obj = CustomerReminderAutomationSettings.for_business(request.business)
    return Response(ReminderAutomationSettingsSerializer(settings_obj).data)

  def patch(self, request):
    from apps.customers.models import CustomerReminderAutomationSettings

    settings_obj, _ = CustomerReminderAutomationSettings.objects.get_or_create(business=request.business)
    serializer = ReminderAutomationSettingsSerializer(settings_obj, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


class CustomerCommunicationSettingsView(APIView):
  """GET/PATCH /api/v1/appointments/communication-settings/ (CUSTOMER 07D.3A.1).

  "Email para respuestas" (Reply-To de los emails al cliente). Mismo gate que
  las automatizaciones: lectura `manage_settings` (owner/admin/manager),
  escritura `manage_reminder_automations` (solo owner/admin). Sin fila →
  vacío (sin Reply-To); la fila se crea en el primer PATCH.
  """
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission, _HasTurnosAccess]
  permission_map = {
    'GET': 'manage_settings',
    'PATCH': 'manage_reminder_automations',
    'PUT': 'manage_reminder_automations',
  }
  http_method_names = ['get', 'patch', 'head', 'options']

  def get(self, request):
    from apps.customers.models import CustomerCommunicationSettings

    settings_obj = CustomerCommunicationSettings.for_business(request.business)
    return Response(CustomerCommunicationSettingsSerializer(settings_obj).data)

  def patch(self, request):
    from apps.customers.models import CustomerCommunicationSettings

    settings_obj, _ = CustomerCommunicationSettings.objects.get_or_create(business=request.business)
    serializer = CustomerCommunicationSettingsSerializer(settings_obj, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


class CommunicationAutomationSettingsView(APIView):
  """GET/PATCH /api/v1/appointments/communication-automation-settings/ (CUSTOMER 07D.4A).

  Switches de comunicaciones automáticas por email (recordatorio de turno /
  seguimiento por inasistencia). Mismo gate que `communication-settings`:
  lectura `manage_settings` (owner/admin/manager), escritura
  `manage_reminder_automations` (solo owner/admin). Sin fila → apagado; la
  fila se crea en el primer PATCH.
  """
  permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission, _HasTurnosAccess]
  permission_map = {
    'GET': 'manage_settings',
    'PATCH': 'manage_reminder_automations',
    'PUT': 'manage_reminder_automations',
  }
  http_method_names = ['get', 'patch', 'head', 'options']

  def get(self, request):
    from apps.customers.models import CustomerCommunicationSettings

    settings_obj = CustomerCommunicationSettings.for_business(request.business)
    return Response(CommunicationAutomationSettingsSerializer(settings_obj).data)

  def patch(self, request):
    from apps.customers.models import CustomerCommunicationSettings

    settings_obj, _ = CustomerCommunicationSettings.objects.get_or_create(business=request.business)
    serializer = CommunicationAutomationSettingsSerializer(settings_obj, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

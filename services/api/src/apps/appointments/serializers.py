from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.customers.models import Customer, CustomerCommunicationSettings, CustomerReminderAutomationSettings

from .models import (
  Appointment,
  AppointmentCategory,
  AppointmentException,
  AppointmentProfessional,
  AppointmentSchedule,
  AppointmentService,
)
from .services import admin_mutation, booking, reminder_automation
from .services.customer_link import resolve_customer_for_appointment
from .services.deposit import deposit_config_error
from .services.payment_summary import build_payment_summary


class AppointmentCategorySerializer(serializers.ModelSerializer):
  services_count = serializers.IntegerField(read_only=True, default=0)

  class Meta:
    model = AppointmentCategory
    fields = [
      'id', 'business', 'name', 'description', 'is_active', 'sort_order',
      'services_count', 'created_at', 'updated_at',
    ]
    read_only_fields = ['id', 'business', 'services_count', 'created_at', 'updated_at']

  def validate_name(self, value: str) -> str:
    value = value.strip()
    if len(value) < 2:
      raise serializers.ValidationError('El nombre debe tener al menos 2 caracteres.')
    if len(value) > 100:
      raise serializers.ValidationError('El nombre no puede exceder 100 caracteres.')
    return value

  def validate(self, attrs):
    business = attrs.get('business') or getattr(self.instance, 'business', None)
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)

    name = attrs.get('name')
    if business and name:
      conflict = AppointmentCategory.objects.filter(business=business, name__iexact=name)
      if self.instance:
        conflict = conflict.exclude(pk=self.instance.pk)
      if conflict.exists():
        raise serializers.ValidationError({'name': 'Ya existe una categoría con este nombre.'})

    return attrs


class AppointmentCategorySummarySerializer(serializers.ModelSerializer):
  """Serializer reducido para embeber en AppointmentService."""
  class Meta:
    model = AppointmentCategory
    fields = ['id', 'name']
    read_only_fields = fields


class AppointmentServiceSerializer(serializers.ModelSerializer):
  category = AppointmentCategorySummarySerializer(read_only=True)
  category_id = serializers.PrimaryKeyRelatedField(
    queryset=AppointmentCategory.objects.all(),
    source='category',
    allow_null=True,
    required=False,
    write_only=True,
  )

  class Meta:
    model = AppointmentService
    fields = [
      'id',
      'business',
      'category',
      'category_id',
      'name',
      'description',
      'duration_minutes',
      'price',
      'deposit_type',
      'deposit_value',
      'is_active',
      'sort_order',
      'created_at',
      'updated_at',
    ]
    read_only_fields = ['id', 'business', 'created_at', 'updated_at', 'category']

  def validate_name(self, value: str) -> str:
    value = value.strip()
    if len(value) < 2:
      raise serializers.ValidationError('El nombre debe tener al menos 2 caracteres.')
    if len(value) > 255:
      raise serializers.ValidationError('El nombre no puede exceder 255 caracteres.')
    return value

  def validate_category_id(self, value):
    if value is None:
      return value

    business = getattr(self.instance, 'business', None) if self.instance else None
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)

    if business and value.business_id != business.id:
      raise serializers.ValidationError('La categoría no pertenece a este negocio.')

    return value

  def validate_duration_minutes(self, value: int) -> int:
    if value <= 0:
      raise serializers.ValidationError('La duración debe ser mayor a 0 minutos.')
    return value

  def validate_price(self, value: Decimal) -> Decimal:
    if value < 0:
      raise serializers.ValidationError('El precio debe ser mayor o igual a 0.')
    return value

  def validate(self, attrs):
    deposit_type = attrs.get('deposit_type', getattr(self.instance, 'deposit_type', AppointmentService.DepositType.NONE))
    deposit_value = attrs.get('deposit_value', getattr(self.instance, 'deposit_value', Decimal('0')))
    price = attrs.get('price', getattr(self.instance, 'price', Decimal('0')))

    if deposit_value is None:
      deposit_value = Decimal('0')

    # Slice 7C: regla canónica compartida con `AppointmentService.clean`.
    error = deposit_config_error(price=price, deposit_type=deposit_type, deposit_value=deposit_value)
    if error:
      raise serializers.ValidationError({'deposit_value': error})
    if deposit_type == AppointmentService.DepositType.NONE:
      attrs['deposit_value'] = Decimal('0')
    else:
      attrs['deposit_value'] = deposit_value

    business = attrs.get('business') or getattr(self.instance, 'business', None)
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)

    name = attrs.get('name')
    if business and name:
      conflict = AppointmentService.objects.filter(business=business, name__iexact=name)
      if self.instance:
        conflict = conflict.exclude(pk=self.instance.pk)
      if conflict.exists():
        raise serializers.ValidationError({'name': 'Ya existe un servicio con este nombre.'})

    return attrs

  def update(self, instance, validated_data):
    validated_data.pop('business', None)
    return super().update(instance, validated_data)


class AppointmentServiceSummarySerializer(serializers.ModelSerializer):
  category = AppointmentCategorySummarySerializer(read_only=True)

  class Meta:
    model = AppointmentService
    fields = ['id', 'name', 'duration_minutes', 'price', 'is_active', 'category']
    read_only_fields = fields


class AppointmentProfessionalSerializer(serializers.ModelSerializer):
  services = AppointmentServiceSummarySerializer(many=True, read_only=True)
  service_ids = serializers.PrimaryKeyRelatedField(
    queryset=AppointmentService.objects.all(),
    source='services',
    many=True,
    required=False,
    write_only=True,
  )

  class Meta:
    model = AppointmentProfessional
    fields = [
      'id',
      'business',
      'name',
      'description',
      'phone',
      'email',
      'services',
      'service_ids',
      'is_active',
      'sort_order',
      'created_at',
      'updated_at',
    ]
    read_only_fields = ['id', 'business', 'services', 'created_at', 'updated_at']

  def validate_name(self, value: str) -> str:
    value = value.strip()
    if len(value) < 2:
      raise serializers.ValidationError('El nombre debe tener al menos 2 caracteres.')
    if len(value) > 150:
      raise serializers.ValidationError('El nombre no puede exceder 150 caracteres.')
    return value

  def validate_service_ids(self, value):
    business = getattr(self.instance, 'business', None) if self.instance else None
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)

    if business:
      foreign = [str(service.id) for service in value if service.business_id != business.id]
      if foreign:
        raise serializers.ValidationError('Uno o más servicios no pertenecen a este negocio.')

    return value

  def validate(self, attrs):
    business = attrs.get('business') or getattr(self.instance, 'business', None)
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)

    name = attrs.get('name')
    if business and name:
      conflict = AppointmentProfessional.objects.filter(business=business, name__iexact=name)
      if self.instance:
        conflict = conflict.exclude(pk=self.instance.pk)
      if conflict.exists():
        raise serializers.ValidationError({'name': 'Ya existe un profesional con este nombre.'})

    return attrs

  def update(self, instance, validated_data):
    validated_data.pop('business', None)
    return super().update(instance, validated_data)


class AppointmentProfessionalSummarySerializer(serializers.ModelSerializer):
  """Serializer reducido para embeber en AppointmentSchedule / AppointmentException."""
  class Meta:
    model = AppointmentProfessional
    fields = ['id', 'name']
    read_only_fields = fields


class AppointmentScheduleSerializer(serializers.ModelSerializer):
  professional = AppointmentProfessionalSummarySerializer(read_only=True)
  professional_id = serializers.PrimaryKeyRelatedField(
    queryset=AppointmentProfessional.objects.all(),
    source='professional',
    allow_null=True,
    required=False,
    write_only=True,
  )
  weekday_display = serializers.CharField(source='get_weekday_display', read_only=True)

  class Meta:
    model = AppointmentSchedule
    fields = [
      'id',
      'business',
      'professional',
      'professional_id',
      'weekday',
      'weekday_display',
      'start_time',
      'end_time',
      'created_at',
      'updated_at',
    ]
    read_only_fields = ['id', 'business', 'professional', 'created_at', 'updated_at']

  def validate_professional_id(self, value):
    if value is None:
      return value

    business = getattr(self.instance, 'business', None) if self.instance else None
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)

    if business and value.business_id != business.id:
      raise serializers.ValidationError('El profesional no pertenece a este negocio.')

    return value

  def validate(self, attrs):
    start_time = attrs.get('start_time', getattr(self.instance, 'start_time', None))
    end_time = attrs.get('end_time', getattr(self.instance, 'end_time', None))

    if start_time is not None and end_time is not None and start_time >= end_time:
      raise serializers.ValidationError({'end_time': 'La hora de fin debe ser posterior a la hora de inicio.'})

    weekday = attrs.get('weekday', getattr(self.instance, 'weekday', None))
    professional = attrs.get('professional', self.instance.professional if self.instance else None)

    business = attrs.get('business') or getattr(self.instance, 'business', None)
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)

    if business and weekday is not None and start_time is not None and end_time is not None:
      conflicts = AppointmentSchedule.objects.filter(business=business, professional=professional, weekday=weekday)
      if self.instance:
        conflicts = conflicts.exclude(pk=self.instance.pk)
      for block in conflicts:
        if start_time < block.end_time and end_time > block.start_time:
          raise serializers.ValidationError('Este horario se superpone con otro bloque existente para ese día.')

    return attrs

  def update(self, instance, validated_data):
    validated_data.pop('business', None)
    return super().update(instance, validated_data)


class BusinessCustomerField(serializers.PrimaryKeyRelatedField):
  """`customer_id` acotado al `Business` del turno (Turnos CUSTOMER 05).

  El queryset se resuelve por request: un id de otro negocio responde igual
  que uno inexistente (`does_not_exist`), así el campo no sirve de oráculo
  para enumerar Customers ajenos.
  """

  def get_queryset(self):
    business = self.parent._get_business() if self.parent is not None else None
    if business is None:
      return Customer.objects.none()
    return Customer.objects.filter(business=business)

  def to_representation(self, value):
    # Mismo formato que el `UUIDField` read-only de CUSTOMER 01 (string).
    return str(value.pk)


class AppointmentSerializer(serializers.ModelSerializer):
  service = AppointmentServiceSummarySerializer(read_only=True)
  service_id = serializers.PrimaryKeyRelatedField(
    queryset=AppointmentService.objects.all(),
    source='service',
    write_only=True,
  )
  professional = AppointmentProfessionalSummarySerializer(read_only=True)
  professional_id = serializers.PrimaryKeyRelatedField(
    queryset=AppointmentProfessional.objects.all(),
    source='professional',
    allow_null=True,
    required=False,
    write_only=True,
  )
  status_display = serializers.CharField(source='get_status_display', read_only=True)
  # Slice 7B.3: estado operativo real (un `pending_payment` con el hold
  # vencido es `expired` aunque `expire_appointment_holds` todavía no haya
  # normalizado la DB). `status` sigue siendo el valor almacenado.
  effective_status = serializers.SerializerMethodField()
  effective_status_display = serializers.SerializerMethodField()
  # Resumen financiero del intento de pago representativo (o null). Solo en
  # endpoints internos del Business; ver `services.payment_summary`.
  payment_summary = serializers.SerializerMethodField()
  # Turnos CUSTOMER 01: solo el id del `Customer` vinculado (o null). La UI
  # sigue mostrando los snapshots `customer_*` del turno.
  # CUSTOMER 05: también es input opcional (CustomerPicker). Si viene, ese
  # Customer (mismo Business, activo) es el vínculo y NO se resuelve por
  # teléfono; si no viene, rige el resolver de CUSTOMER 01. Los snapshots
  # siempre salen del payload del turno: el Customer nunca se modifica.
  customer_id = BusinessCustomerField(source='customer', required=False, allow_null=False)

  class Meta:
    model = Appointment
    fields = [
      'id',
      'business',
      'service',
      'service_id',
      'professional',
      'professional_id',
      'customer_id',
      'customer_name',
      'customer_phone',
      'customer_email',
      'start_at',
      'end_at',
      'status',
      'status_display',
      'effective_status',
      'effective_status_display',
      'expires_at',
      'payment_summary',
      'notes',
      'source',
      'service_name',
      'service_duration_minutes',
      'service_price',
      'deposit_type',
      'deposit_value',
      'created_at',
      'updated_at',
    ]
    read_only_fields = [
      'id',
      'business',
      'service',
      'professional',
      'end_at',
      'expires_at',
      'source',
      'service_name',
      'service_duration_minutes',
      'service_price',
      'deposit_type',
      'deposit_value',
      'created_at',
      'updated_at',
    ]

  def get_effective_status(self, obj) -> str:
    return obj.effective_status()

  def get_effective_status_display(self, obj) -> str:
    return Appointment.Status(obj.effective_status()).label

  def get_payment_summary(self, obj):
    summary = build_payment_summary(obj)
    if summary is not None and summary['paid_at'] is not None:
      summary['paid_at'] = serializers.DateTimeField().to_representation(summary['paid_at'])
    return summary

  def _get_business(self):
    if self.instance is not None:
      return self.instance.business
    request = self.context.get('request')
    return getattr(request, 'business', None) if request else None

  def validate_service_id(self, value):
    business = self._get_business()
    if business and value.business_id != business.id:
      raise serializers.ValidationError('El servicio no pertenece a este negocio.')
    return value

  def validate_professional_id(self, value):
    if value is None:
      return value
    business = self._get_business()
    if business and value.business_id != business.id:
      raise serializers.ValidationError('El profesional no pertenece a este negocio.')
    return value

  def validate_customer_id(self, value: Customer) -> Customer:
    # Conservar el vínculo actual siempre es válido (aunque ese Customer se
    # haya dado de baja después): editar un turno no obliga a re-vincularlo.
    if self.instance is not None and value.pk == self.instance.customer_id:
      return value
    if not value.is_active:
      raise serializers.ValidationError('El cliente está dado de baja. Reactivalo desde su ficha o elegí otro.')
    return value

  def validate_customer_name(self, value: str) -> str:
    value = value.strip()
    if len(value) < 2:
      raise serializers.ValidationError('El nombre del cliente debe tener al menos 2 caracteres.')
    if len(value) > 150:
      raise serializers.ValidationError('El nombre del cliente no puede exceder 150 caracteres.')
    return value

  def validate_customer_phone(self, value: str) -> str:
    value = value.strip()
    if len(value) < 6:
      raise serializers.ValidationError('El teléfono no es válido.')
    return value

  def validate(self, attrs):
    is_create = self.instance is None
    if is_create and 'start_at' not in attrs:
      raise serializers.ValidationError({'start_at': 'Este campo es requerido.'})
    if is_create and 'service' not in attrs:
      raise serializers.ValidationError({'service_id': 'Este campo es requerido.'})
    return attrs

  @transaction.atomic
  def create(self, validated_data):
    business = validated_data.pop('business')
    service = validated_data.pop('service')
    professional = validated_data.pop('professional', None)
    start_at = validated_data.pop('start_at')

    booking.lock_professionals(business, {professional})
    end_at = booking.compute_end_at(service, start_at)
    try:
      booking.ensure_slot_available(
        business=business, service=service, professional=professional, start_at=start_at, end_at=end_at,
      )
      booking.ensure_no_overlap(
        business=business, service=service, professional=professional, start_at=start_at, end_at=end_at,
      )
    except booking.BookingError as exc:
      raise serializers.ValidationError({exc.field or 'start_at': [exc.message]}) from exc

    customer = validated_data.pop('customer', None)
    if customer is None:
      customer = resolve_customer_for_appointment(
        business=business,
        customer_name=validated_data['customer_name'],
        customer_phone=validated_data['customer_phone'],
        customer_email=validated_data.get('customer_email', ''),
      )

    appointment = Appointment.objects.create(
      business=business,
      customer=customer,
      service=service,
      professional=professional,
      start_at=start_at,
      end_at=end_at,
      status=Appointment.Status.CONFIRMED,
      source=Appointment.Source.MANUAL,
      service_name=service.name,
      service_duration_minutes=service.duration_minutes,
      service_price=service.price,
      deposit_type=service.deposit_type,
      deposit_value=service.deposit_value,
      customer_name=validated_data['customer_name'],
      customer_phone=validated_data['customer_phone'],
      customer_email=validated_data.get('customer_email', ''),
      notes=validated_data.get('notes', ''),
    )
    # CUSTOMER 07B: recordatorio interno automático (si la regla está activa).
    reminder_automation.reconcile_appointment_reminders(appointment)
    return appointment

  def update(self, instance, validated_data):
    # Slice 6B.1: `instance` fue leída sin lock al inicio del request. Toda
    # la lógica corre contra el estado bloqueado (ver `services.admin_mutation`)
    # y solo escribe lo que cambia: un formulario viejo nunca revierte un
    # `confirmed` del webhook ni un `expires_at` ya limpiado.
    try:
      return admin_mutation.update_appointment(
        business=instance.business, appointment_id=instance.pk, changes=validated_data,
      )
    except booking.BookingError as exc:
      raise serializers.ValidationError({exc.field or 'start_at': [exc.message]}) from exc


class AppointmentExceptionSerializer(serializers.ModelSerializer):
  professional = AppointmentProfessionalSummarySerializer(read_only=True)
  professional_id = serializers.PrimaryKeyRelatedField(
    queryset=AppointmentProfessional.objects.all(),
    source='professional',
    allow_null=True,
    required=False,
    write_only=True,
  )

  class Meta:
    model = AppointmentException
    fields = [
      'id',
      'business',
      'professional',
      'professional_id',
      'date',
      'is_closed',
      'start_time',
      'end_time',
      'note',
      'created_at',
      'updated_at',
    ]
    read_only_fields = ['id', 'business', 'professional', 'created_at', 'updated_at']

  def validate_professional_id(self, value):
    if value is None:
      return value

    business = getattr(self.instance, 'business', None) if self.instance else None
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)

    if business and value.business_id != business.id:
      raise serializers.ValidationError('El profesional no pertenece a este negocio.')

    return value

  def validate_note(self, value: str) -> str:
    return value.strip() if value else value

  def validate(self, attrs):
    is_closed = attrs.get('is_closed', getattr(self.instance, 'is_closed', False))
    start_time = attrs.get('start_time', getattr(self.instance, 'start_time', None))
    end_time = attrs.get('end_time', getattr(self.instance, 'end_time', None))

    if is_closed:
      attrs['start_time'] = None
      attrs['end_time'] = None
    else:
      if start_time is None or end_time is None:
        raise serializers.ValidationError('Debés indicar hora de inicio y fin, o marcar el día como cerrado.')
      if start_time >= end_time:
        raise serializers.ValidationError({'end_time': 'La hora de fin debe ser posterior a la hora de inicio.'})

    business = attrs.get('business') or getattr(self.instance, 'business', None)
    if business is None:
      request = self.context.get('request')
      business = getattr(request, 'business', None)

    professional = attrs.get('professional', self.instance.professional if self.instance else None)
    date = attrs.get('date', getattr(self.instance, 'date', None))

    if business and date:
      conflict = AppointmentException.objects.filter(business=business, professional=professional, date=date)
      if self.instance:
        conflict = conflict.exclude(pk=self.instance.pk)
      if conflict.exists():
        raise serializers.ValidationError({'date': 'Ya existe una excepción para esta fecha.'})

    return attrs

  def update(self, instance, validated_data):
    validated_data.pop('business', None)
    return super().update(instance, validated_data)


class ReminderAutomationSettingsSerializer(serializers.ModelSerializer):
  """Reglas de recordatorios internos automáticos del Business (CUSTOMER 07B).

  Límites (backend y frontend): anticipación 1–168 h (una semana), seguimiento
  de inasistencia 1–720 h (30 días). 0, negativos o más quedan en 400.
  """

  appointment_reminder_hours_before = serializers.IntegerField(
    min_value=CustomerReminderAutomationSettings.APPOINTMENT_HOURS_MIN,
    max_value=CustomerReminderAutomationSettings.APPOINTMENT_HOURS_MAX,
    required=False,
  )
  no_show_followup_delay_hours = serializers.IntegerField(
    min_value=CustomerReminderAutomationSettings.NO_SHOW_HOURS_MIN,
    max_value=CustomerReminderAutomationSettings.NO_SHOW_HOURS_MAX,
    required=False,
  )

  class Meta:
    model = CustomerReminderAutomationSettings
    fields = [
      'appointment_reminder_enabled',
      'appointment_reminder_hours_before',
      'no_show_followup_enabled',
      'no_show_followup_delay_hours',
      'updated_at',
    ]
    read_only_fields = ['updated_at']


class CustomerCommunicationSettingsSerializer(serializers.ModelSerializer):
  """Email operativo para respuestas (Reply-To) de los emails a clientes (CUSTOMER 07D.3A.1).

  Vacío = sin Reply-To. Se normaliza (trim + dominio en minúsculas). El From no
  es configurable: no hay campo para eso.
  """

  reply_to_email = serializers.EmailField(required=False, allow_blank=True, max_length=254)

  class Meta:
    model = CustomerCommunicationSettings
    fields = ['reply_to_email', 'updated_at']
    read_only_fields = ['updated_at']

  def validate_reply_to_email(self, value: str) -> str:
    value = (value or '').strip()
    if not value:
      return ''
    local, _, domain = value.rpartition('@')
    return f'{local}@{domain.lower()}'


class CommunicationAutomationSettingsSerializer(serializers.ModelSerializer):
  """Comunicaciones automáticas al cliente por email (CUSTOMER 07D.4A).

  Apagadas por defecto. `email_delivery_mode` (solo lectura) refleja el
  proveedor configurado en el ENTORNO: `simulation` (fake, nada sale) salvo
  opt-in explícito `CUSTOMER_DELIVERY_PROVIDER_EMAIL=ses` → `live`. Nunca se
  infiere de credenciales ni de que el código SES exista.
  """

  email_delivery_mode = serializers.SerializerMethodField()

  class Meta:
    model = CustomerCommunicationSettings
    fields = ['appointment_email_enabled', 'no_show_email_enabled', 'email_delivery_mode', 'updated_at']
    read_only_fields = ['updated_at']

  def get_email_delivery_mode(self, obj) -> str:
    from django.conf import settings as dj_settings

    provider = str(getattr(dj_settings, 'CUSTOMER_DELIVERY_PROVIDER_EMAIL', 'fake') or 'fake').strip().lower()
    return 'live' if provider == 'ses' else 'simulation'

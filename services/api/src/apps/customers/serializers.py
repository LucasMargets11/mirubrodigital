from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import Customer, CustomerContactPreferences, CustomerMessageDelivery, CustomerNote, CustomerReminder


class CustomerSummarySerializer(serializers.ModelSerializer):
  class Meta:
    model = Customer
    fields = ['id', 'name', 'doc_type', 'doc_number', 'email', 'phone']
    read_only_fields = fields


class CustomerSerializer(serializers.ModelSerializer):
  class Meta:
    model = Customer
    fields = [
      'id',
      'business',
      'name',
      'type',
      'doc_type',
      'doc_number',
      'tax_condition',
      'email',
      'phone',
      'address_line',
      'city',
      'province',
      'postal_code',
      'country',
      'note',
      'tags',
      'is_active',
      'created_at',
      'updated_at',
    ]
    read_only_fields = ['id', 'business', 'created_at', 'updated_at']

  def validate_name(self, value: str) -> str:
    if not value.strip():
      raise serializers.ValidationError('El nombre no puede estar vacío.')
    return value

  def validate_doc_number(self, value: str) -> str:
    if value is None:
      return ''
    return value.strip()

  def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
    business = attrs.get('business') or getattr(self.instance, 'business', None)
    email = attrs.get('email')
    if business and email:
      conflict = Customer.objects.filter(business=business, email__iexact=email)
      if self.instance is not None:
        conflict = conflict.exclude(pk=self.instance.pk)
      if conflict.exists():
        raise serializers.ValidationError({'email': 'Ya existe un cliente con este email.'})
    doc_type = attrs.get('doc_type')
    doc_number = attrs.get('doc_number')
    if business and doc_type and doc_number:
      lookup = Customer.objects.filter(business=business, doc_type=doc_type, doc_number__iexact=doc_number)
      if self.instance is not None:
        lookup = lookup.exclude(pk=self.instance.pk)
      if lookup.exists():
        raise serializers.ValidationError({'doc_number': 'Ya existe un cliente con este documento.'})

    return attrs

  def create(self, validated_data: dict[str, Any]) -> Customer:
    if 'tags' not in validated_data or validated_data['tags'] is None:
      validated_data['tags'] = []
    return Customer.objects.create(**validated_data)

  def update(self, instance: Customer, validated_data: dict[str, Any]) -> Customer:
    validated_data.pop('business', None)
    if 'tags' in validated_data and validated_data['tags'] is None:
      validated_data['tags'] = []
    return super().update(instance, validated_data)

  def to_representation(self, instance: Customer) -> dict[str, Any]:
    data = super().to_representation(instance)
    if data.get('note') == '':
      data['note'] = None
    if data.get('tags') == []:
      data['tags'] = []
    return data


def _author_display_name(user) -> str:
  """Nombre visible del autor sin exponer el email (username suele serlo)."""
  full_name = (user.get_full_name() or '').strip()
  if full_name:
    return full_name
  return (user.get_username() or '').split('@', 1)[0]


class CustomerNoteSerializer(serializers.ModelSerializer):
  """Nota interna (CUSTOMER 04C). `author` sale del request, nunca del payload."""

  body = serializers.CharField(
    max_length=CustomerNote.BODY_MAX_LENGTH,
    trim_whitespace=True,
    allow_blank=False,
    error_messages={'blank': 'La nota no puede estar vacía.'},
  )
  author = serializers.SerializerMethodField()

  class Meta:
    model = CustomerNote
    fields = ['id', 'body', 'author', 'created_at', 'updated_at']
    read_only_fields = ['id', 'author', 'created_at', 'updated_at']

  def get_author(self, obj: CustomerNote) -> dict[str, Any] | None:
    if obj.author_id is None:
      return None
    return {'id': str(obj.author_id), 'name': _author_display_name(obj.author)}


class BusinessDateTimeField(serializers.DateTimeField):
  """DateTime en la zona del Business del request (CUSTOMER 07A).

  Un valor sin offset ("2026-10-03T16:00") se interpreta como hora local del
  Business, nunca del navegador ni UTC; con offset se respeta el instante. La
  salida lleva el offset del Business. Siempre se guarda timezone-aware.
  """

  def default_timezone(self):
    from apps.appointments.services.availability import resolve_business_timezone

    request = self.context.get('request')
    business = getattr(request, 'business', None) if request is not None else None
    if business is not None:
      return resolve_business_timezone(business)
    return super().default_timezone()


class CustomerReminderSerializer(serializers.ModelSerializer):
  """Recordatorio interno (CUSTOMER 07A).

  `created_by`, `business` y `customer` salen del request/URL, nunca del
  payload. `status` solo admite pending → completed | cancelled (finales);
  un recordatorio cerrado no se edita. `is_overdue` es derivado.

  CUSTOMER 07B: los automáticos (`source` != manual) solo se completan o
  cancelan; título/fecha/descripción/turno los administra la automatización
  (una reconciliación posterior pisaría un cambio manual). Lo creado por la
  API siempre es `manual`.
  """

  AUTOMATIC_LOCKED_FIELDS = ('title', 'description', 'remind_at', 'appointment_id')

  title = serializers.CharField(
    max_length=CustomerReminder.TITLE_MAX_LENGTH,
    trim_whitespace=True,
    allow_blank=False,
    error_messages={'blank': 'El título no puede estar vacío.', 'required': 'El título es obligatorio.'},
  )
  description = serializers.CharField(
    max_length=CustomerReminder.DESCRIPTION_MAX_LENGTH, trim_whitespace=True, allow_blank=True, required=False,
  )
  remind_at = BusinessDateTimeField(error_messages={'required': 'Elegí fecha y hora.'})
  status = serializers.ChoiceField(choices=CustomerReminder.Status.choices, required=False)
  status_display = serializers.CharField(source='get_status_display', read_only=True)
  source = serializers.CharField(read_only=True)
  source_display = serializers.CharField(source='get_source_display', read_only=True)
  is_automatic = serializers.BooleanField(read_only=True)
  is_overdue = serializers.SerializerMethodField()
  appointment_id = serializers.UUIDField(required=False, allow_null=True)
  appointment_start_at = BusinessDateTimeField(source='appointment.start_at', read_only=True, allow_null=True)
  created_by = serializers.SerializerMethodField()
  completed_at = BusinessDateTimeField(read_only=True)
  # CUSTOMER 07C: cuándo salió el aviso interno. No es un estado ni completa nada.
  notified_at = BusinessDateTimeField(read_only=True)
  created_at = BusinessDateTimeField(read_only=True)
  updated_at = BusinessDateTimeField(read_only=True)

  class Meta:
    model = CustomerReminder
    fields = [
      'id', 'title', 'description', 'remind_at', 'status', 'status_display', 'is_overdue',
      'source', 'source_display', 'is_automatic', 'appointment_id', 'appointment_start_at', 'created_by', 'completed_at', 'notified_at',
      'created_at', 'updated_at',
    ]
    read_only_fields = ['id', 'status_display', 'is_overdue', 'created_by', 'completed_at', 'notified_at', 'created_at', 'updated_at']

  def get_is_overdue(self, obj: CustomerReminder) -> bool:
    return obj.is_overdue(now=self.context.get('now'))

  def get_created_by(self, obj: CustomerReminder) -> dict[str, Any] | None:
    if obj.created_by_id is None:
      return None
    return {'id': str(obj.created_by_id), 'name': _author_display_name(obj.created_by)}

  def validate_appointment_id(self, value):
    if value is None:
      return None
    from apps.appointments.models import Appointment

    customer: Customer = self.context['customer']
    # Lookup dentro del Business del Customer: un turno ajeno es indistinguible de uno inexistente.
    appointment = Appointment.objects.filter(pk=value, business_id=customer.business_id).first()
    if appointment is None:
      raise serializers.ValidationError('El turno no existe en este negocio.')
    if CustomerReminder.appointment_mismatch(customer, appointment) == 'customer':
      raise serializers.ValidationError('El turno pertenece a otro cliente.')
    return appointment

  def validate(self, attrs):
    instance: CustomerReminder | None = self.instance
    status = attrs.get('status')
    if instance is None:
      if status not in (None, CustomerReminder.Status.PENDING):
        raise serializers.ValidationError({'status': 'Un recordatorio nuevo siempre empieza pendiente.'})
      return attrs
    if instance.status != CustomerReminder.Status.PENDING:
      raise serializers.ValidationError(
        {'status': f'El recordatorio ya está {instance.get_status_display().lower()} y no se puede modificar.'}
      )
    if instance.is_automatic:
      locked = [field for field in self.AUTOMATIC_LOCKED_FIELDS if field in self.initial_data]
      if locked:
        raise serializers.ValidationError({
          field: 'Los recordatorios automáticos no se editan: completalo o cancelalo y creá uno manual.'
          for field in locked
        })
    return attrs

  def _apply_appointment(self, attrs):
    if 'appointment_id' in attrs:
      attrs['appointment'] = attrs.pop('appointment_id')
    return attrs

  def create(self, validated_data):
    validated_data.pop('status', None)
    return super().create(self._apply_appointment(validated_data))

  def update(self, instance, validated_data):
    from django.utils import timezone as dj_timezone

    status = validated_data.get('status')
    if status == CustomerReminder.Status.COMPLETED:
      validated_data['completed_at'] = dj_timezone.now()
    validated_data = self._apply_appointment(validated_data)
    for attr, value in validated_data.items():
      setattr(instance, attr, value)
    # Solo los campos editados: nunca pisar `notified_at`, que el worker de
    # avisos (CUSTOMER 07C) puede haber escrito en paralelo.
    instance.save(update_fields=[*validated_data.keys(), 'updated_at'])
    return instance


class CustomerContactPreferencesSerializer(serializers.ModelSerializer):
  """Preferencias de contacto operativo (CUSTOMER 07D.1). Solo GET/PATCH.

  Encender WhatsApp o email (apagado → encendido) exige
  `<canal>_consent_confirmed: true` y un destino real: teléfono válido para
  WhatsApp / email cargado (CUSTOMER 07D.1.1; antes se permitía sin dato).
  Se registran `<canal>_consent_at`, `consent_source` (default `manual`) y el
  destino normalizado autorizado (`<canal>_consent_value`, no se expone).
  Con el canal ya encendido, `<canal>_consent_confirmed: true` RENUEVA la
  autorización contra el destino actual (p. ej. cambió el teléfono). Nada de
  eso viene del payload. Apagar un canal conserva su registro; volver a
  encenderlo pide confirmar de nuevo. `channels` es derivado
  (`contact_preferences.channels_status`).
  """

  MISSING_DESTINATION_ERRORS = {
    'whatsapp': 'El cliente no tiene un teléfono válido para WhatsApp. Cargalo en la ficha antes de autorizar el canal.',
    'email': 'El cliente no tiene email cargado. Cargalo en la ficha antes de autorizar el canal.',
  }

  # Desde el panel solo se registra lo que el equipo puede afirmar; los
  # orígenes `public_booking`/`imported` quedan para flujos de sistema.
  PANEL_CONSENT_SOURCES = (
    CustomerContactPreferences.ConsentSource.MANUAL,
    CustomerContactPreferences.ConsentSource.CUSTOMER_REQUEST,
  )

  customer_id = serializers.UUIDField(read_only=True)
  preferred_channel = serializers.ChoiceField(
    choices=CustomerContactPreferences.Channel.choices, allow_null=True, required=False,
  )
  whatsapp_consent_confirmed = serializers.BooleanField(write_only=True, required=False)
  email_consent_confirmed = serializers.BooleanField(write_only=True, required=False)
  consent_source = serializers.ChoiceField(choices=[(s.value, s.label) for s in PANEL_CONSENT_SOURCES], write_only=True, required=False)
  whatsapp_consent_at = BusinessDateTimeField(read_only=True)
  email_consent_at = BusinessDateTimeField(read_only=True)
  updated_at = BusinessDateTimeField(read_only=True)
  channels = serializers.SerializerMethodField()

  class Meta:
    model = CustomerContactPreferences
    fields = [
      'customer_id', 'whatsapp_enabled', 'email_enabled', 'phone_enabled', 'preferred_channel', 'do_not_contact',
      'whatsapp_consent_at', 'whatsapp_consent_source', 'email_consent_at', 'email_consent_source',
      'whatsapp_consent_confirmed', 'email_consent_confirmed', 'consent_source',
      'channels', 'updated_at',
    ]
    read_only_fields = ['customer_id', 'whatsapp_consent_source', 'email_consent_source', 'channels', 'updated_at']

  def get_channels(self, obj: CustomerContactPreferences) -> dict[str, Any]:
    from .contact_preferences import channels_status

    return channels_status(obj.customer, obj)

  def _final(self, attrs, field):
    return attrs[field] if field in attrs else getattr(self.instance, field)

  def validate(self, attrs):
    from .contact_preferences import CONSENT_CHANNELS

    from .contact_preferences import consent_destination

    errors: dict[str, str] = {}
    self._consents: dict[str, str] = {}
    customer = self.instance.customer
    for channel in CONSENT_CHANNELS:
      enabled = self._final(attrs, f'{channel}_enabled')
      enabling = enabled and not getattr(self.instance, f'{channel}_enabled')
      confirmed = bool(attrs.get(f'{channel}_consent_confirmed'))
      if enabling and not confirmed:
        errors[f'{channel}_consent_confirmed'] = 'Confirmá que el cliente autorizó este canal.'
        continue
      if not (enabled and confirmed):
        continue
      # Alta o renovación: el consentimiento corresponde a un destino real.
      destination = consent_destination(customer, channel)
      if destination is None:
        errors[f'{channel}_enabled'] = self.MISSING_DESTINATION_ERRORS[channel]
        continue
      self._consents[channel] = destination
    preferred = self._final(attrs, 'preferred_channel')
    if preferred and not self._final(attrs, f'{preferred}_enabled'):
      errors['preferred_channel'] = 'El canal preferido tiene que estar permitido.'
    if errors:
      raise serializers.ValidationError(errors)
    return attrs

  def update(self, instance: CustomerContactPreferences, validated_data):
    from django.utils import timezone as dj_timezone

    from .contact_preferences import CONSENT_CHANNELS

    source = validated_data.pop('consent_source', None) or CustomerContactPreferences.ConsentSource.MANUAL
    now = dj_timezone.now()
    for channel in CONSENT_CHANNELS:
      validated_data.pop(f'{channel}_consent_confirmed', None)
    for channel, destination in getattr(self, '_consents', {}).items():
      setattr(instance, f'{channel}_consent_at', now)
      setattr(instance, f'{channel}_consent_source', source)
      setattr(instance, f'{channel}_consent_value', destination)
    for attr, value in validated_data.items():
      setattr(instance, attr, value)
    instance.save()
    return instance


class CustomerMessageDeliverySerializer(serializers.ModelSerializer):
  """Historial de comunicaciones externas (CUSTOMER 07D.2). Solo lectura.

  Nunca expone el destino completo (`destination_masked`), ni
  `idempotency_key`, `context` o `failure_message` (detalle interno del
  proveedor): el resumen del error es `failure_code`.
  """
  channel_display = serializers.CharField(source='get_channel_display', read_only=True)
  purpose_display = serializers.CharField(source='get_purpose_display', read_only=True)
  status_display = serializers.CharField(source='get_status_display', read_only=True)
  destination_masked = serializers.SerializerMethodField()
  max_attempts = serializers.SerializerMethodField()
  # True si lo procesó un proveedor fake (sin envío real): la UI no debe
  # presentarlo como un mensaje que el cliente recibió.
  is_simulated = serializers.SerializerMethodField()
  # Nombre del proveedor real (p. ej. 'Amazon SES'); None si fake o sin intento.
  # Nunca el provider_message_id.
  provider_display = serializers.SerializerMethodField()
  appointment_id = serializers.UUIDField(read_only=True)
  reminder_id = serializers.UUIDField(read_only=True)
  created_at = BusinessDateTimeField(read_only=True)
  last_attempt_at = BusinessDateTimeField(read_only=True)
  next_retry_at = BusinessDateTimeField(read_only=True)
  sent_at = BusinessDateTimeField(read_only=True)
  delivered_at = BusinessDateTimeField(read_only=True)
  failed_at = BusinessDateTimeField(read_only=True)
  skipped_at = BusinessDateTimeField(read_only=True)
  cancelled_at = BusinessDateTimeField(read_only=True)

  class Meta:
    model = CustomerMessageDelivery
    fields = [
      'id', 'channel', 'channel_display', 'purpose', 'purpose_display', 'status', 'status_display',
      'destination_masked', 'attempt_count', 'max_attempts', 'is_simulated', 'provider_display', 'skip_reason', 'failure_code',
      'appointment_id', 'reminder_id', 'created_at', 'last_attempt_at', 'next_retry_at',
      'sent_at', 'delivered_at', 'failed_at', 'skipped_at', 'cancelled_at',
    ]
    read_only_fields = fields

  def get_destination_masked(self, obj: CustomerMessageDelivery) -> str | None:
    from .deliveries import mask_destination

    return mask_destination(obj.channel, obj.destination_snapshot)

  def get_max_attempts(self, obj: CustomerMessageDelivery) -> int:
    from .deliveries import max_attempts

    return max_attempts()

  def get_is_simulated(self, obj: CustomerMessageDelivery) -> bool:
    return (obj.provider or '').startswith('fake_')

  def get_provider_display(self, obj: CustomerMessageDelivery) -> str | None:
    if not obj.provider or self.get_is_simulated(obj):
      return None
    return obj.get_provider_display()

"""Serializers públicos para el flujo `/t/[slug]` (Slice 4A/4B).

Deliberadamente separados de `serializers.py`: los serializers privados
incluyen campos administrativos (sort_order, timestamps, contacto de
profesionales) que no deben exponerse en la landing pública.
"""
from rest_framework import serializers

from .models import AppointmentCategory, AppointmentPayment, AppointmentProfessional, AppointmentService
from .services.contact import booking_whatsapp_url
from .services.payment_summary import representative_payment


class PublicAppointmentCategorySummarySerializer(serializers.ModelSerializer):
  class Meta:
    model = AppointmentCategory
    fields = ['id', 'name']
    read_only_fields = fields


class PublicAppointmentCategorySerializer(serializers.ModelSerializer):
  class Meta:
    model = AppointmentCategory
    fields = ['id', 'name', 'description']
    read_only_fields = fields


class PublicAppointmentServiceSerializer(serializers.ModelSerializer):
  category = PublicAppointmentCategorySummarySerializer(read_only=True)

  class Meta:
    model = AppointmentService
    fields = [
      'id',
      'name',
      'description',
      'duration_minutes',
      'price',
      'deposit_type',
      'deposit_value',
      'category',
    ]
    read_only_fields = fields


class PublicAppointmentProfessionalSerializer(serializers.ModelSerializer):
  """Vista pública de un profesional: sin phone/email/sort_order."""

  class Meta:
    model = AppointmentProfessional
    fields = ['id', 'name', 'description']
    read_only_fields = fields


class PublicAppointmentBookingCreateSerializer(serializers.Serializer):
  """Payload de entrada de `POST .../bookings/` (Slice 4B).

  Únicamente lo que el cliente final puede decidir. Cualquier otro dato
  (precio, seña, `business_id`, `status`, `end`, `source`, `expires_at`) se
  resuelve siempre server-side en `services.booking.create_public_appointment`
  — no se declaran acá, así que un payload que los incluya los ignora.
  """
  service = serializers.UUIDField()
  professional = serializers.UUIDField(required=False, allow_null=True, default=None)
  start = serializers.DateTimeField()
  customer_name = serializers.CharField()
  customer_phone = serializers.CharField()
  customer_email = serializers.EmailField(required=False, allow_blank=True, default='')

  def validate_customer_name(self, value: str) -> str:
    value = value.strip()
    if len(value) < 2:
      raise serializers.ValidationError('El nombre debe tener al menos 2 caracteres.')
    if len(value) > 150:
      raise serializers.ValidationError('El nombre no puede exceder 150 caracteres.')
    return value

  def validate_customer_phone(self, value: str) -> str:
    value = value.strip()
    if len(value) < 6:
      raise serializers.ValidationError('El teléfono no es válido.')
    if len(value) > 30:
      raise serializers.ValidationError('El teléfono no puede exceder 30 caracteres.')
    return value


class PublicAppointmentBookingServiceSerializer(serializers.Serializer):
  """Snapshot de servicio embebido en la respuesta de una reserva pública."""
  name = serializers.CharField(source='service_name')
  price = serializers.DecimalField(source='service_price', max_digits=12, decimal_places=2)
  duration_minutes = serializers.IntegerField(source='service_duration_minutes')


class PublicAppointmentBookingProfessionalSerializer(serializers.Serializer):
  name = serializers.CharField()


# Slice 6C: estados de `AppointmentPayment` que pueden verse en la página
# pública. Whitelist explícita: un estado nuevo no se filtra hasta decidirlo.
PUBLIC_PAYMENT_STATUSES = frozenset({
  AppointmentPayment.Status.CREATING,
  AppointmentPayment.Status.PENDING,
  AppointmentPayment.Status.APPROVED,
  AppointmentPayment.Status.REJECTED,
  AppointmentPayment.Status.CANCELLED,
  AppointmentPayment.Status.ERROR,
  AppointmentPayment.Status.UNCERTAIN,
  AppointmentPayment.Status.REQUIRES_REVIEW,
})

def public_payment_status(appointment) -> str | None:
  """Estado público normalizado del pago de la seña de un turno, o None.

  El intento representativo sale de `services.payment_summary` (misma regla
  que el panel interno). Nunca expone ids de provider, `external_reference`,
  `failure_reason` ni `review_reason`: solo el estado, que la página usa para
  decidir qué mensaje mostrar. La decisión de si se puede reintentar sigue
  siendo del endpoint de checkout.
  """
  chosen = representative_payment(appointment)
  if chosen is None:
    return None
  return chosen.status if chosen.status in PUBLIC_PAYMENT_STATUSES else None


class PublicAppointmentBookingStatusSerializer(serializers.Serializer):
  """Respuesta pública de `POST/GET .../bookings/...` (Slice 4B, punto 9).

  Expone solo lo necesario para la pantalla de confirmación/hold del
  cliente: nunca `id` interno, ni datos privados del profesional/negocio.
  Slice 6C: `payment_status` es el estado público normalizado del intento de
  pago relevante (ver `public_payment_status`), fuente de verdad del retorno
  desde Mercado Pago — la query `payment=` de la back URL es solo una pista.
  Slice 6D: `contact_whatsapp_url` es un link `https://wa.me/...` con mensaje
  prearmado (ver `services.contact`), o null. Nunca el teléfono crudo.
  """
  public_token = serializers.UUIDField()
  status = serializers.SerializerMethodField()
  expires_at = serializers.DateTimeField(allow_null=True)
  start_at = serializers.DateTimeField()
  end_at = serializers.DateTimeField()
  customer_name = serializers.CharField()
  service = PublicAppointmentBookingServiceSerializer(source='*')
  professional = serializers.SerializerMethodField()
  deposit_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
  payment_status = serializers.SerializerMethodField()
  contact_whatsapp_url = serializers.SerializerMethodField()

  def get_status(self, obj) -> str:
    return obj.effective_status()

  def get_professional(self, obj):
    if not obj.professional_id:
      return None
    return PublicAppointmentBookingProfessionalSerializer(obj.professional).data

  def get_payment_status(self, obj) -> str | None:
    return public_payment_status(obj)

  def get_contact_whatsapp_url(self, obj) -> str | None:
    # Slice 6D: link `https://wa.me/...` armado server-side, solo para
    # confirmed / requires_review y si el negocio configuró su WhatsApp.
    return booking_whatsapp_url(obj, public_payment_status(obj))


class PublicAppointmentCheckoutSerializer(serializers.Serializer):
  """Respuesta de `POST .../bookings/<public_token>/checkout/` (Slice 6A).

  Solo lo necesario para redirigir al checkout: nunca external_reference,
  ids de Mercado Pago, ids internos del turno ni datos del negocio.
  """
  payment_id = serializers.UUIDField(source='payment.id')
  status = serializers.CharField(source='payment.status')
  amount = serializers.DecimalField(source='payment.amount', max_digits=12, decimal_places=2)
  currency = serializers.CharField(source='payment.currency')
  checkout_url = serializers.URLField(source='payment.checkout_url')
  expires_at = serializers.DateTimeField(source='appointment.expires_at')

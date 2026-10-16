"""Endpoints públicos de Turnos (Slice 4A/4B): landing + reserva `/t/[slug]`.

Read-only (Slice 4A) + creación/estado de reserva (Slice 4B). Sin
autenticación. Resuelven el negocio únicamente por `slug` (nunca por
`business_id`) y reusan el motor de disponibilidad y booking existentes
(`services.availability`, `services.booking`) sin duplicar lógica.
"""
from __future__ import annotations

import datetime as dt

from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.business.models import Business

from .models import Appointment, AppointmentCategory, AppointmentProfessional, AppointmentService
from .public_serializers import (
  PublicAppointmentBookingCreateSerializer,
  PublicAppointmentBookingStatusSerializer,
  PublicAppointmentCheckoutSerializer,
  PublicAppointmentCategorySerializer,
  PublicAppointmentProfessionalSerializer,
  PublicAppointmentServiceSerializer,
)
from .public_page import PUBLISHABLE_STATUSES, public_booking_unavailable_reason  # noqa: F401 (re-export)
from .services import booking, payment as payment_service
from .services.availability import AvailabilityError, compute_availability


def _resolve_public_business(slug: str) -> Business | None:
  """Resuelve el negocio público para Turnos, o None si no corresponde exponerlo.

  Cubre en un solo lugar los tres motivos de "recurso público no
  disponible": slug inexistente, negocio no publicable, o Turnos no
  habilitado para ese negocio. La regla vive en `public_page` y es la
  misma que ve el panel ("Página de reservas").
  """
  try:
    business = Business.objects.get(slug=slug)
  except Business.DoesNotExist:
    return None
  if public_booking_unavailable_reason(business) is not None:
    return None
  return business


class PublicAppointmentBusinessView(APIView):
  """GET /api/v1/appointments/public/<slug>/

  Info pública del negocio + categorías/servicios activos.
  """
  permission_classes = []
  throttle_classes = [ScopedRateThrottle]
  throttle_scope = 'public_appointments'

  def get(self, request, slug):
    business = _resolve_public_business(slug)
    if business is None:
      return Response(status=status.HTTP_404_NOT_FOUND)

    categories = (
      AppointmentCategory.objects.filter(business=business, is_active=True)
      .order_by('sort_order', 'name')
    )
    services = (
      AppointmentService.objects.filter(business=business, is_active=True)
      .select_related('category')
      .order_by('sort_order', 'name')
    )

    return Response({
      'business': {
        'name': business.name,
        'slug': business.slug,
        'timezone': business.timezone,
      },
      'categories': PublicAppointmentCategorySerializer(categories, many=True).data,
      'services': PublicAppointmentServiceSerializer(services, many=True).data,
    })


class PublicAppointmentProfessionalsView(APIView):
  """GET /api/v1/appointments/public/<slug>/professionals/?service=<id>

  Profesionales activos habilitados para el servicio pedido. Si el negocio
  no usa profesionales para ese servicio, devuelve una lista vacía (el
  frontend debe permitir continuar sin seleccionar uno).
  """
  permission_classes = []
  throttle_classes = [ScopedRateThrottle]
  throttle_scope = 'public_appointments'

  def get(self, request, slug):
    business = _resolve_public_business(slug)
    if business is None:
      return Response(status=status.HTTP_404_NOT_FOUND)

    service_id = request.query_params.get('service')
    if not service_id:
      return Response({'service': ['Este parámetro es requerido.']}, status=status.HTTP_400_BAD_REQUEST)

    try:
      service = AppointmentService.objects.get(pk=service_id, business=business, is_active=True)
    except (AppointmentService.DoesNotExist, ValueError, TypeError):
      return Response({'service': ['Servicio no encontrado.']}, status=status.HTTP_400_BAD_REQUEST)

    professionals = (
      AppointmentProfessional.objects.filter(business=business, is_active=True, services=service)
      .order_by('sort_order', 'name')
    )
    return Response(PublicAppointmentProfessionalSerializer(professionals, many=True).data)


class PublicAppointmentAvailabilityView(APIView):
  """GET /api/v1/appointments/public/<slug>/availability/?service=&date=&professional=

  Delega enteramente en `compute_availability` (mismo motor que el panel
  interno, Slice 3B): valida servicio/profesional activos, relación
  profesional-servicio y tenant, sin duplicar ninguna regla.
  """
  permission_classes = []
  throttle_classes = [ScopedRateThrottle]
  throttle_scope = 'public_appointments'

  def get(self, request, slug):
    business = _resolve_public_business(slug)
    if business is None:
      return Response(status=status.HTTP_404_NOT_FOUND)

    service_id = request.query_params.get('service')
    date_param = request.query_params.get('date')
    professional_id = request.query_params.get('professional') or None

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


class PublicAppointmentBookingCreateView(APIView):
  """POST /api/v1/appointments/public/<slug>/bookings/  (Slice 4B)

  Crea la reserva del cliente final. Delega enteramente en
  `services.booking.create_public_appointment` (lock + revalidación de
  disponibilidad/solapamiento + creación, todo en una transacción). Sin
  seña: turno `confirmed`. Con seña: turno `pending_payment` con hold de
  10 minutos. Todavía no crea ningún pago (Mercado Pago queda fuera de
  este slice).
  """
  permission_classes = []
  throttle_classes = [ScopedRateThrottle]
  throttle_scope = 'public_appointments_booking'

  def post(self, request, slug):
    business = _resolve_public_business(slug)
    if business is None:
      return Response(status=status.HTTP_404_NOT_FOUND)

    serializer = PublicAppointmentBookingCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
      appointment = booking.create_public_appointment(
        business=business,
        service_id=str(data['service']),
        professional_id=str(data['professional']) if data.get('professional') else None,
        start_at=data['start'],
        customer_name=data['customer_name'],
        customer_phone=data['customer_phone'],
        customer_email=data.get('customer_email', ''),
      )
    except booking.BookingError as exc:
      return Response({exc.field or 'detail': [exc.message]}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
      PublicAppointmentBookingStatusSerializer(appointment).data,
      status=status.HTTP_201_CREATED,
    )


class PublicAppointmentBookingStatusView(APIView):
  """GET /api/v1/appointments/public/<slug>/bookings/<public_token>/  (Slice 4B)

  Permite al cliente final volver a consultar su reserva (p.ej. tras
  refrescar la página) usando el `public_token` opaco recibido al crearla.
  Valida que el token pertenezca al negocio del slug: un token válido de
  otro negocio no debe resolver nada acá.
  """
  permission_classes = []
  throttle_classes = [ScopedRateThrottle]
  throttle_scope = 'public_appointments'

  def get(self, request, slug, public_token):
    business = _resolve_public_business(slug)
    if business is None:
      return Response(status=status.HTTP_404_NOT_FOUND)

    try:
      appointment = Appointment.objects.select_related('professional', 'business__branding').get(
        business=business, public_token=public_token,
      )
    except Appointment.DoesNotExist:
      return Response(status=status.HTTP_404_NOT_FOUND)

    return Response(PublicAppointmentBookingStatusSerializer(appointment).data)


# Código de `CheckoutError` → HTTP status.
_CHECKOUT_ERROR_STATUS = {
  'not_found': status.HTTP_404_NOT_FOUND,
  'not_payable': status.HTTP_409_CONFLICT,
  'expired': status.HTTP_409_CONFLICT,
  'payment_in_progress': status.HTTP_409_CONFLICT,
  'payment_unavailable': status.HTTP_503_SERVICE_UNAVAILABLE,
  'payment_provider_error': status.HTTP_502_BAD_GATEWAY,
  'payment_uncertain': status.HTTP_502_BAD_GATEWAY,
}


class PublicAppointmentCheckoutView(APIView):
  """POST /api/v1/appointments/public/<slug>/bookings/<public_token>/checkout/  (Slice 6A)

  Inicia el pago de la seña con Mercado Pago (cuenta del Business). El
  body se ignora por completo: monto, moneda, referencia y URLs se derivan
  server-side del turno resuelto por `slug` + `public_token`. Un segundo
  POST sobre un intento `pending` devuelve el mismo checkout (200), nunca
  una Preference nueva. Ver `services.payment`.

  Usado por el botón "Continuar al pago" de `/t/[slug]` (Slice 6C).
  La confirmación por pago llega por el webhook `flow=appointment` (Slice 6B).
  """
  permission_classes = []
  throttle_classes = [ScopedRateThrottle]
  throttle_scope = 'public_appointments_checkout'

  def post(self, request, slug, public_token):
    business = _resolve_public_business(slug)
    if business is None:
      return Response(status=status.HTTP_404_NOT_FOUND)

    try:
      result = payment_service.start_appointment_checkout(business=business, public_token=public_token)
    except payment_service.CheckoutError as exc:
      http_status = _CHECKOUT_ERROR_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST)
      if http_status == status.HTTP_404_NOT_FOUND:
        return Response(status=http_status)
      return Response({'detail': exc.message, 'code': exc.code}, status=http_status)

    return Response(
      PublicAppointmentCheckoutSerializer(result).data,
      status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
    )

"""Owner-only quote and change endpoints for the S6 Turnos lifecycle."""
from __future__ import annotations

import logging

from django.conf import settings
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership

from .mp_service import MercadoPagoService
from .models import SubscriptionV2
from .services.appointments_lifecycle import (
    AppointmentsLifecycleError,
    apply_appointments_change,
    prepare_appointments_provider_change,
    quote_appointments_change,
    resolve_professional_excess,
    request_appointments_change,
)

logger = logging.getLogger(__name__)


class AppointmentsChangeSerializer(serializers.Serializer):
    plan_code = serializers.ChoiceField(
        choices=('appointments', 'appointments_pro', 'appointments_ai'),
        required=False,
    )
    usage_tier = serializers.ChoiceField(
        choices=('ai_300', 'ai_1500', 'ai_3000', 'custom'),
        allow_null=True,
        required=False,
    )
    billing_cycle = serializers.ChoiceField(
        choices=('monthly', 'yearly'),
        required=False,
    )
    automations = serializers.BooleanField(required=False)
    extra_professionals = serializers.IntegerField(min_value=0, required=False)


def _owner_subscription(request):
    membership = resolve_request_membership(request)
    if membership is None:
        return None, None, Response(
            {'detail': 'No se encontró membresía.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    if membership.role != 'owner':
        return None, None, Response(
            {'detail': 'Solo el propietario puede gestionar el plan de Turnos.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    subscription = (
        SubscriptionV2.objects.filter(
            business=membership.business,
            service_type=SubscriptionV2.ServiceType.APPOINTMENTS,
        )
        .exclude(status=SubscriptionV2.Status.CANCELED)
        .order_by('-created_at')
        .first()
    )
    if subscription is None:
        return None, None, Response(
            {'detail': 'No se encontró una suscripción V2 de Turnos.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return membership, subscription, None


def _serialize_quote(quote):
    result = dict(quote)
    for key in ('effective_at', 'next_renewal_at'):
        if result.get(key) is not None:
            result[key] = result[key].isoformat()
    proration = dict(result['proration'])
    for key in ('period_start', 'period_end', 'calculated_at'):
        if proration.get(key) is not None:
            proration[key] = proration[key].isoformat()
    result['proration'] = proration
    result['quote'] = dict(result['quote'])
    result['quote'].pop('created_at', None)
    return result


class AppointmentsLifecycleQuoteView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    billing_enforcement_bypass = True

    def post(self, request):
        _, subscription, error = _owner_subscription(request)
        if error:
            return error
        serializer = AppointmentsChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            quote = quote_appointments_change(
                subscription=subscription,
                target=serializer.validated_data,
            )
        except (AppointmentsLifecycleError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_serialize_quote(quote))


class AppointmentsLifecycleChangeView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    billing_enforcement_bypass = True

    def post(self, request):
        membership, _, error = _owner_subscription(request)
        if error:
            return error
        serializer = AppointmentsChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pending, quote = request_appointments_change(
                business=membership.business,
                user=request.user,
                target=serializer.validated_data,
            )
        except (AppointmentsLifecycleError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        result = {
            'pending_change_id': str(pending.pk),
            'status': pending.status,
            'requires_payment': pending.requires_checkout,
            'requires_resolution': pending.requires_resolution,
            'resolution': pending.resolution_details,
            'quote': _serialize_quote(quote),
        }
        if not pending.requires_checkout:
            if pending.status in ('scheduled', 'processing'):
                try:
                    prepare_appointments_provider_change(pending)
                    if pending.status == 'processing':
                        apply_appointments_change(pending)
                        pending.refresh_from_db()
                except Exception:
                    pending.status = 'failed'
                    pending.save(update_fields=['status', 'updated_at'])
                    logger.exception(
                        'Could not prepare Turnos provider change pending_change=%s',
                        pending.pk,
                    )
                    return Response(
                        {'detail': 'No pudimos actualizar el próximo cobro de Turnos.'},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
            result['scheduled'] = pending.status in ('scheduled', 'blocked')
            result['applied'] = pending.status == 'completed'
            return Response(result, status=status.HTTP_200_OK)

        try:
            base_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
            preference = MercadoPagoService().create_preference(
                items=[{
                    'title': quote['checkout_line_items'][0]['description'],
                    'quantity': 1,
                    'unit_price': float(pending.total_amount),
                    'currency_id': 'ARS',
                }],
                external_reference=f'subscription_change_{pending.pk}',
                back_urls={
                    'success': f'{base_url}/app/turnos/configuracion?payment=success',
                    'failure': f'{base_url}/app/turnos/configuracion?payment=failure',
                    'pending': f'{base_url}/app/turnos/configuracion?payment=pending',
                },
                metadata={
                    'business_id': membership.business_id,
                    'pending_change_id': str(pending.pk),
                    'service_type': 'appointments',
                    'subscription_v2_id': str(pending.subscription_v2_id),
                },
            )
            if not preference.get('id') or not preference.get('init_point'):
                raise ValueError('Mercado Pago no devolvió una preferencia válida.')
            pending.mp_preference_id = preference['id']
            pending.mp_init_point = preference['init_point']
            pending.save(update_fields=['mp_preference_id', 'mp_init_point', 'updated_at'])
        except Exception as exc:
            pending.status = 'failed'
            pending.save(update_fields=['status', 'updated_at'])
            logger.exception(
                'Could not create Turnos lifecycle preference pending_change=%s',
                pending.pk,
            )
            return Response(
                {'detail': 'No pudimos iniciar el pago de la actualización.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        result['checkout_url'] = preference['init_point']
        return Response(result, status=status.HTTP_201_CREATED)


class AppointmentsLifecycleResolveView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    billing_enforcement_bypass = True

    def post(self, request, pending_change_id):
        membership, subscription, error = _owner_subscription(request)
        if error:
            return error
        from .models import PendingSubscriptionChange

        pending = PendingSubscriptionChange.objects.filter(
            pk=pending_change_id,
            business=membership.business,
            subscription_v2=subscription,
        ).first()
        if pending is None:
            return Response(
                {'detail': 'No se encontró el cambio pendiente.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            pending = resolve_professional_excess(pending)
        except AppointmentsLifecycleError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        if pending.requires_resolution:
            return Response(
                {'detail': 'Desactivá profesionales hasta resolver el exceso.',
                 'resolution': pending.resolution_details},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            prepare_appointments_provider_change(pending)
        except Exception:
            pending.status = 'blocked'
            pending.requires_resolution = True
            pending.resolution_details = {'provider_schedule_error': True}
            pending.save(update_fields=[
                'status', 'requires_resolution', 'resolution_details', 'updated_at',
            ])
            logger.exception(
                'Could not prepare resolved Turnos provider change pending_change=%s',
                pending.pk,
            )
            return Response(
                {'detail': 'No pudimos programar el próximo cobro; reintentá la resolución.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({
            'pending_change_id': str(pending.pk),
            'status': pending.status,
            'scheduled_for': pending.scheduled_for.isoformat() if pending.scheduled_for else None,
            'requires_resolution': False,
        })

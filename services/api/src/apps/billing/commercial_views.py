"""
Vistas para gestión de suscripciones de Gestión Comercial.
"""
import logging
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

logger = logging.getLogger(__name__)

from apps.accounts.permissions import HasBusinessMembership
from apps.business.models import Business, Subscription as BusinessSubscription, SubscriptionAddon
from apps.billing.commercial_plans import (
    get_plan_config,
    get_addon_config,
    get_available_addons_for_plan,
    get_included_addons_for_plan,
    BRANCH_EXTRA_PRICING,
    SEAT_EXTRA_PRICING,
)
from apps.billing.services.commercial.limits import get_branch_limits


class CommercialSubscriptionView(APIView):
    """
    Vista para obtener la suscripción actual de Gestión Comercial.
    
    GET /api/billing/commercial/subscription/
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    
    def get(self, request):
        business: Business = getattr(request, 'business', None)
        if not business:
            return Response(
                {'detail': 'Business not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verificar si el usuario es owner
        membership = request.user.memberships.filter(business=business).first()
        can_manage = membership and membership.role == 'owner'
        
        # Obtener subscription (legacy business.Subscription)
        try:
            subscription = business.subscription
        except BusinessSubscription.DoesNotExist:
            return Response(
                {'detail': 'No subscription found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        plan_code = subscription.plan.lower()
        plan_config = get_plan_config(plan_code)
        
        if not plan_config:
            return Response(
                {'detail': f'Plan configuration not found for {plan_code}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Obtener addons actualmente contratados (no incluidos en el plan)
        active_addon_codes = []
        for addon in subscription.addons.filter(is_active=True):
            if addon.code in ['extra_branch', 'extra_seat']:
                continue  # Estos son recursos, no módulos
            active_addon_codes.append(addon.code)
        
        # Calcular límites de sucursales
        branches_extra_qty = sum(
            addon.quantity
            for addon in subscription.addons.filter(code='extra_branch', is_active=True)
        )
        
        branch_limits = get_branch_limits(plan_code, branches_extra_qty)
        
        # Calcular sucursales usadas
        branches_used = business.branches.count()
        
        # Obtener seats extras
        seats_extras_qty = sum(
            addon.quantity
            for addon in subscription.addons.filter(code='extra_seat', is_active=True)
        )
        
        # Calcular billing cycle (inferir de lo que hay o default a monthly)
        # TODO: cuando se implemente billing.Subscription, leer de ahí
        billing_cycle = 'monthly'  # Default por ahora
        
        # Obtener addons incluidos en el plan
        included_addons = []
        for addon in get_included_addons_for_plan(plan_code):
            included_addons.append({
                'code': addon['code'],
                'name': addon['name'],
                'description': addon['description'],
                'pricing': addon['pricing'],
            })
        
        # Obtener addons activos (contratados como extra, no incluidos)
        active_addons = []
        for addon_code in active_addon_codes:
            # Solo incluir si no está ya incluido en el plan
            if not any(a['code'] == addon_code for a in included_addons):
                addon_config = get_addon_config(addon_code)
                if addon_config:
                    active_addons.append({
                        'code': addon_config['code'],
                        'name': addon_config['name'],
                        'description': addon_config['description'],
                        'pricing': addon_config['pricing'],
                    })
        
        # Obtener addons disponibles para compra (no incluidos ni activos)
        available_addons = []
        for addon in get_available_addons_for_plan(plan_code):
            # Solo incluir si no está incluido ni activo
            if not any(a['code'] == addon['code'] for a in included_addons + active_addons):
                available_addons.append({
                    'code': addon['code'],
                    'name': addon['name'],
                    'description': addon['description'],
                    'pricing': addon['pricing'],
                })
        
        # Construir respuesta
        response_data = {
            # Plan actual
            'current_plan': {
                'code': plan_code,
                'name': plan_config['name'],
                'description': plan_config['description'],
                'pricing': plan_config['pricing'],
                'features': plan_config['features'],
                'is_custom': plan_config['is_custom'],
            },
            
            # Ciclo de facturación
            'billing_cycle': billing_cycle,
            
            # Status de suscripción
            'status': subscription.status,
            
            # Sucursales
            'branches': {
                'used': branches_used,
                'included': branch_limits.included,
                'extras_qty': branches_extra_qty,
                'max_total': branch_limits.max_total,
                'can_add_more': branch_limits.can_add_more,
                'remaining': branch_limits.remaining,
                'extras_allowed': branch_limits.extras_allowed,
                'max_extras': branch_limits.max_extras,
                'unit_pricing': BRANCH_EXTRA_PRICING,
            },
            
            # Seats/Usuarios
            'seats': {
                'included': plan_config['limits']['seats_included'],
                'extras_qty': seats_extras_qty,
                'total': plan_config['limits']['seats_included'] + seats_extras_qty,
                'unit_pricing': SEAT_EXTRA_PRICING,
            },
            
            # Add-ons
            'addons': {
                'active': active_addons,
                'available': available_addons,
                'included': included_addons,
            },
            
            # Permisos
            'can_manage': can_manage,
        }
        
        return Response(response_data)


class CommercialPreviewChangeView(APIView):
    """
    Vista para previsualizar cambios de suscripción.
    
    POST /api/billing/commercial/preview-change/
    Body: {
        "plan_code": "pro",
        "billing_cycle": "monthly",
        "crm": true,
        "invoicing": false,
        "branches_extra_qty": 2,
        "seats_extra_qty": 5
    }
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    
    def post(self, request):
        from apps.billing.services.commercial.preview import preview_subscription_change
        
        business: Business = getattr(request, 'business', None)
        if not business:
            return Response(
                {'detail': 'Business not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verificar si el usuario es owner
        membership = request.user.memberships.filter(business=business).first()
        can_manage = membership and membership.role == 'owner'
        
        if not can_manage:
            return Response(
                {'detail': 'Solo el propietario puede gestionar la suscripción'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validar datos de entrada
        data = request.data
        plan_code = data.get('plan_code', '').lower()
        billing_cycle = data.get('billing_cycle', 'monthly').lower()
        enable_crm = data.get('crm', False)
        enable_invoicing = data.get('invoicing', False)
        branches_extra_qty = int(data.get('branches_extra_qty', 0))
        seats_extra_qty = int(data.get('seats_extra_qty', 0))
        
        # Validar valores
        if billing_cycle not in ['monthly', 'yearly']:
            return Response(
                {'detail': 'billing_cycle debe ser "monthly" o "yearly"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if branches_extra_qty < 0 or seats_extra_qty < 0:
            return Response(
                {'detail': 'Las cantidades no pueden ser negativas'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Obtener preview
        preview = preview_subscription_change(
            business=business,
            new_plan_code=plan_code,
            billing_cycle=billing_cycle,
            enable_crm=enable_crm,
            enable_invoicing=enable_invoicing,
            branches_extra_qty=branches_extra_qty,
            seats_extra_qty=seats_extra_qty,
        )
        
        return Response(preview)


class CommercialCheckoutView(APIView):
    """
    Vista para iniciar el checkout de un cambio de suscripción.
    
    POST /api/billing/commercial/checkout/
    Body: {
        "plan_code": "pro",
        "billing_cycle": "monthly",
        "crm": true,
        "invoicing": false,
        "branches_extra_qty": 2,
        "seats_extra_qty": 5
    }
    
    Returns:
        {
            "pending_change_id": 123,
            "checkout_url": "https://mercadopago.com/...",
            "requires_payment": true
        }
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    
    def post(self, request):
        from django.conf import settings
        from apps.billing.models import PendingSubscriptionChange
        from apps.billing.services.commercial.preview import preview_subscription_change
        from apps.billing.services.commercial.apply import apply_subscription_change
        from apps.billing.mp_service import MercadoPagoService
        
        business: Business = getattr(request, 'business', None)
        if not business:
            return Response(
                {'detail': 'Business not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verificar si el usuario es owner
        membership = request.user.memberships.filter(business=business).first()
        can_manage = membership and membership.role == 'owner'
        
        if not can_manage:
            return Response(
                {'detail': 'Solo el propietario puede gestionar la suscripción'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validar datos de entrada
        data = request.data
        plan_code = data.get('plan_code', '').lower()
        billing_cycle = data.get('billing_cycle', 'monthly').lower()
        enable_crm = data.get('crm', False)
        enable_invoicing = data.get('invoicing', False)
        branches_extra_qty = int(data.get('branches_extra_qty', 0))
        seats_extra_qty = int(data.get('seats_extra_qty', 0))
        
        # Validar valores
        if billing_cycle not in ['monthly', 'yearly']:
            return Response(
                {'detail': 'billing_cycle debe ser "monthly" o "yearly"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if branches_extra_qty < 0 or seats_extra_qty < 0:
            return Response(
                {'detail': 'Las cantidades no pueden ser negativas'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Obtener preview para validar y calcular costos
        preview = preview_subscription_change(
            business=business,
            new_plan_code=plan_code,
            billing_cycle=billing_cycle,
            enable_crm=enable_crm,
            enable_invoicing=enable_invoicing,
            branches_extra_qty=branches_extra_qty,
            seats_extra_qty=seats_extra_qty,
        )
        
        # Verificar errores de validación
        if preview['validation_errors']:
            return Response(
                {
                    'detail': 'Validation errors',
                    'errors': preview['validation_errors']
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Crear configuración snapshot
        config_snapshot = {
            'crm': enable_crm,
            'invoicing': enable_invoicing,
            'branches_extra_qty': branches_extra_qty,
            'seats_extra_qty': seats_extra_qty,
        }
        
        # Crear PendingSubscriptionChange
        pending_change = PendingSubscriptionChange.objects.create(
            business=business,
            user=request.user,
            target_plan_code=plan_code,
            billing_cycle=billing_cycle,
            config_snapshot=config_snapshot,
            line_items=preview['line_items'],
            total_amount=preview['total_now'],
            requires_checkout=preview['requires_checkout'],
            is_upgrade=preview['is_upgrade'],
            is_downgrade=preview['is_downgrade'],
            status='pending_payment' if preview['requires_checkout'] else 'scheduled',
        )
        
        # Si es downgrade o no requiere pago, programar para aplicar más tarde
        if preview['is_downgrade'] or not preview['requires_checkout']:
            # Aplicar inmediatamente si no requiere pago
            if not preview['requires_checkout']:
                try:
                    apply_subscription_change(
                        business=business,
                        target_plan_code=plan_code,
                        billing_cycle=billing_cycle,
                        config=config_snapshot,
                    )
                    pending_change.status = 'completed'
                    pending_change.applied_at = timezone.now()
                    pending_change.save()
                    
                    return Response({
                        'pending_change_id': pending_change.id,
                        'requires_payment': False,
                        'applied': True,
                        'message': preview['change_summary'],
                    })
                except Exception as e:
                    pending_change.status = 'failed'
                    pending_change.save()
                    return Response(
                        {'detail': f'Error applying change: {str(e)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            else:
                # Downgrade: programar para próximo ciclo
                # TODO: Implementar lógica de scheduled_for basado en subscription.renews_at
                return Response({
                    'pending_change_id': pending_change.id,
                    'requires_payment': False,
                    'scheduled': True,
                    'message': preview['change_summary'],
                })
        
        # Upgrade: requiere pago
        # Crear preferencia de MercadoPago
        try:
            mp_service = MercadoPagoService()
            
            # Preparar items para MercadoPago
            mp_items = []
            for item in preview['line_items']:
                mp_items.append({
                    'title': item['description'],
                    'quantity': item['quantity'],
                    'unit_price': item['unit_price'] / 100.0,  # Convert centavos to pesos
                    'currency_id': 'ARS',
                })
            
            # URLs de retorno
            base_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            back_urls = {
                'success': f"{base_url}/app/servicios?payment=success&change_id={pending_change.id}",
                'failure': f"{base_url}/app/servicios?payment=failure&change_id={pending_change.id}",
                'pending': f"{base_url}/app/servicios?payment=pending&change_id={pending_change.id}",
            }
            
            # Crear preferencia
            preference = mp_service.create_preference(
                items=mp_items,
                external_reference=f"subscription_change_{pending_change.id}",
                back_urls=back_urls,
                metadata={
                    'business_id': business.id,
                    'pending_change_id': pending_change.id,
                    'plan_code': plan_code,
                }
            )
            
            # Guardar datos de MercadoPago
            pending_change.mp_preference_id = preference.get('id')
            pending_change.mp_init_point = preference.get('init_point')
            pending_change.save()
            
            return Response({
                'pending_change_id': pending_change.id,
                'checkout_url': preference.get('init_point'),
                'requires_payment': True,
                'message': preview['change_summary'],
            })
            
        except Exception as e:
            pending_change.status = 'failed'
            pending_change.save()
            return Response(
                {'detail': f'Error creating checkout: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AddonCheckoutView(APIView):
    """
    Vista para checkout de complementos individuales sin cambiar el plan.
    
    POST /api/billing/commercial/addon-checkout/
    Body: {
        "addon_code": "crm",
        "billing_cycle": "monthly"
    }
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    
    def post(self, request):
        from apps.billing.models import PendingSubscriptionChange
        from apps.billing.mp_service import MercadoPagoService
        from apps.billing.services.commercial.apply import apply_subscription_change
        from django.db import transaction
        from django.conf import settings
        
        business: Business = getattr(request, 'business', None)
        if not business:
            return Response(
                {'detail': 'Business not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verificar permisos: solo owner puede gestionar
        membership = request.user.memberships.filter(business=business).first()
        if not membership or membership.role != 'owner':
            return Response(
                {'detail': 'Solo el propietario puede gestionar complementos'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Obtener datos
        addon_code = request.data.get('addon_code', '').lower()
        billing_cycle = request.data.get('billing_cycle', 'monthly').lower()
        
        if not addon_code:
            return Response(
                {'detail': 'addon_code es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if billing_cycle not in ['monthly', 'yearly']:
            return Response(
                {'detail': 'billing_cycle debe ser monthly o yearly'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validar que el addon existe
        from apps.billing.commercial_plans import get_addon_config, is_addon_available_for_plan, is_addon_included_in_plan
        
        addon_config = get_addon_config(addon_code)
        if not addon_config:
            return Response(
                {'detail': f'Addon {addon_code} no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Obtener plan actual
        try:
            subscription = business.subscription
        except BusinessSubscription.DoesNotExist:
            return Response(
                {'detail': 'No subscription found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        plan_code = subscription.plan.lower()
        
        # Verificar que el addon está disponible para este plan
        if not is_addon_available_for_plan(addon_code, plan_code):
            if is_addon_included_in_plan(addon_code, plan_code):
                return Response(
                    {'detail': f'El complemento {addon_config["name"]} ya está incluido en tu plan {plan_code.upper()}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            return Response(
                {'detail': f'El complemento {addon_config["name"]} no está disponible para tu plan actual'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar que no esté ya activo
        existing_addon = subscription.addons.filter(code=addon_code, is_active=True).first()
        if existing_addon:
            return Response(
                {'detail': f'El complemento {addon_config["name"]} ya está activo en tu suscripción'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calcular precio
        price = addon_config['pricing'][billing_cycle]
        
        # Crear line items
        line_items = [{
            'description': addon_config['name'],
            'quantity': 1,
            'unit_price': price,
            'total': price,
            'is_recurring': True,
        }]
        
        # Configuración snapshot: solo activamos este addon
        config_snapshot = {
            addon_code: True,
        }
        
        # Crear PendingSubscriptionChange
        with transaction.atomic():
            pending_change = PendingSubscriptionChange.objects.create(
                business=business,
                user=request.user,
                target_plan_code=plan_code,  # Mantener el plan actual
                billing_cycle=billing_cycle,
                config_snapshot=config_snapshot,
                line_items=line_items,
                total_amount=price,
                requires_checkout=True,  # Siempre requiere pago para addons
                is_upgrade=True,  # Consideramos agregar un addon como upgrade
                is_downgrade=False,
                status='pending_payment',
            )
        
        # Crear preferencia de MercadoPago
        try:
            mp_service = MercadoPagoService()
            
            mp_items = [{
                'title': f"{addon_config['name']} - {billing_cycle.capitalize()}",
                'quantity': 1,
                'unit_price': price / 100.0,  # Convert centavos to pesos
                'currency_id': 'ARS',
            }]
            
            base_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            back_urls = {
                'success': f"{base_url}/app/servicios?payment=success&addon={addon_code}",
                'failure': f"{base_url}/app/servicios?payment=failure&addon={addon_code}",
                'pending': f"{base_url}/app/servicios?payment=pending&addon={addon_code}",
            }
            
            preference = mp_service.create_preference(
                items=mp_items,
                external_reference=f"addon_purchase_{pending_change.id}",
                back_urls=back_urls,
                metadata={
                    'business_id': business.id,
                    'pending_change_id': pending_change.id,
                    'addon_code': addon_code,
                    'type': 'addon_purchase',
                }
            )
            
            pending_change.mp_preference_id = preference.get('id')
            pending_change.mp_init_point = preference.get('init_point')
            pending_change.save()
            
            return Response({
                'pending_change_id': pending_change.id,
                'checkout_url': preference.get('init_point'),
                'requires_payment': True,
                'addon': {
                    'code': addon_code,
                    'name': addon_config['name'],
                    'description': addon_config['description'],
                },
                'price': price,
                'billing_cycle': billing_cycle,
                'message': f'Listo para activar {addon_config["name"]}',
            })
            
        except Exception as e:
            pending_change.status = 'failed'
            pending_change.save()
            logger.error(f'Error creating addon checkout: {str(e)}')
            return Response(
                {'detail': f'Error al crear el checkout: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

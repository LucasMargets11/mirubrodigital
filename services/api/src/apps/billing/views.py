from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from apps.accounts.access import resolve_business_context, resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership
from apps.business.models import Business
from apps.accounts.models import Membership

from .models import Module, Bundle, Promotion, Subscription, Plan, SubscriptionIntent, PaymentEvent
from .serializers import (
    ModuleSerializer, BundleSerializer, PromotionSerializer, 
    QuoteRequestSerializer, SubscribeRequestSerializer, SubscriptionSerializer
)
from .services import PricingService
from .mp_service import MercadoPagoService

User = get_user_model()

class BillingViewSet(viewsets.ViewSet):
    # Default permission is strict, we override per action if needed
    permission_classes = [IsAuthenticated, HasBusinessMembership]

    def get_permissions(self):
        if self.action in ['modules', 'bundles', 'promotions', 'quote']:
            return [AllowAny()]
        return [IsAuthenticated(), HasBusinessMembership()]

    @action(detail=False, methods=['get'])
    def modules(self, request):
        vertical = request.query_params.get('vertical')
        qs = Module.objects.filter(is_active=True)
        if vertical:
            qs = qs.filter(vertical__in=[vertical, 'both'])
        serializer = ModuleSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def bundles(self, request):
        vertical = request.query_params.get('vertical')
        qs = Bundle.objects.filter(is_active=True)
        if vertical:
            qs = qs.filter(vertical=vertical)
        serializer = BundleSerializer(qs, many=True)
        return Response(serializer.data)
        
    @action(detail=False, methods=['get'])
    def promotions(self, request):
        # vertical = request.query_params.get('vertical')
        qs = Promotion.objects.filter(is_active=True)
        serializer = PromotionSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def quote(self, request):
        serializer = QuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        try:
            quote = PricingService.calculate_quote(
                vertical=data['vertical'],
                billing_period=data['billing_period'],
                plan_type=data['plan_type'],
                selected_module_codes=data.get('selected_module_codes'),
                bundle_code=data.get('bundle_code')
            )
            return Response(quote)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def subscribe(self, request):
        membership = resolve_request_membership(request)
        if membership.role not in ['owner', 'manager']:
            return Response({'detail': 'Only owners/managers can subscribe.'}, status=403)
            
        business = membership.business
        
        serializer = SubscribeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        vertical_map = {'gestion': 'commercial', 'restaurante': 'restaurant'}
        vertical = vertical_map.get(business.default_service, 'commercial')
        
        try:
            quote = PricingService.calculate_quote(
                vertical=vertical,
                billing_period=data['billing_period'],
                plan_type=data['plan_type'],
                selected_module_codes=data.get('selected_module_codes'),
                bundle_code=data.get('bundle_code')
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
        # 2. Save Subscription
        sub, created = Subscription.objects.update_or_create(
            business=business,
            defaults={
                'plan_type': data['plan_type'],
                'billing_period': data['billing_period'],
                'currency': quote['currency'],
                'price_snapshot': quote,
                'status': 'active' 
            }
        )
        
        if data['plan_type'] == 'bundle':
            bundle = Bundle.objects.get(code=data['bundle_code'])
            sub.bundle = bundle
            sub.selected_modules.clear()
        else:
            sub.bundle = None
            codes = [m['code'] for m in quote['modules']]
            modules = Module.objects.filter(code__in=codes)
            sub.selected_modules.set(modules)
            
        sub.save()
        
        return Response(SubscriptionSerializer(sub).data)

    @action(detail=False, methods=['get'])
    def subscription(self, request):
        business = resolve_business_context(request)
        try:
            sub = Subscription.objects.get(business=business)
            return Response(SubscriptionSerializer(sub).data)
        except Subscription.DoesNotExist:
             return Response({})

class StartSubscriptionView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        business_name = request.data.get('business_name')
        plan_code = request.data.get('plan_code')
        
        if not all([email, password, business_name, plan_code]):
             return Response({'error': 'Missing required fields'}, status=400)
        
        if User.objects.filter(email=email).exists():
            return Response({'error': 'Email already registered'}, status=400)
            
        try:
            plan = Plan.objects.get(code=plan_code)
        except Plan.DoesNotExist:
            return Response({'error': 'Invalid plan code'}, status=400)
            
        try:
            with transaction.atomic():
                user = User.objects.create_user(email=email, password=password, username=email)
                business = Business.objects.create(name=business_name, status='pending_activation')
                
                # Subscription
                subscription = Subscription.objects.create(
                    business=business,
                    plan=plan,
                    plan_type='bundle', # Setting default for compatibility
                    billing_period='monthly', # default
                    status='active' 
                )
                
                mp_service = MercadoPagoService()
                
                # Ensure Plan has preapproval_plan_id
                if not plan.mp_preapproval_plan_id:
                    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
                    back_url = f"{frontend_url}/subscribe/return"
                    
                    auto_recurring = {
                        "frequency": 1,
                        "frequency_type": "months",
                        "transaction_amount": float(plan.price),
                        "currency_id": "ARS"
                    }
                    if plan.interval == 'yearly':
                        auto_recurring['frequency'] = 12
                    
                    mp_plan = mp_service.create_preapproval_plan(
                        reason=f"Subscription to {plan.name}",
                        auto_recurring=auto_recurring,
                        back_url=back_url
                    )
                    plan.mp_preapproval_plan_id = mp_plan['id']
                    plan.save()

                # Create Intent
                intent = SubscriptionIntent.objects.create(
                    tenant=business,
                    user=user,
                    plan_code=plan_code,
                    status='created'
                )
                
                frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
                back_url = f"{frontend_url}/subscribe/return?intent_id={intent.id}"
                
                mp_response = mp_service.create_preapproval(
                    email=email,
                    plan_id=plan.mp_preapproval_plan_id,
                    external_reference=str(intent.id),
                    back_url=back_url
                )
                
                intent.mp_init_point = mp_response['init_point']
                intent.mp_preapproval_id = mp_response['id']
                intent.save()
                
                subscription.mp_preapproval_id = mp_response['id']
                subscription.save()

                return Response({
                    'init_point': intent.mp_init_point,
                    'intent_id': intent.pk
                })
        except Exception as e:
            return Response({'error': str(e)}, status=500)

class IntentStatusView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        intent_id = request.query_params.get('intent_id')
        if not intent_id:
            return Response({'error': 'intent_id required'}, status=400)
            
        try:
            intent = SubscriptionIntent.objects.get(pk=intent_id)
            is_active = (intent.tenant.status == 'active')
                
            return Response({
                'status': intent.status,
                'active': is_active,
                'tenant_id': intent.tenant.id if is_active else None
            })
        except SubscriptionIntent.DoesNotExist:
             return Response({'error': 'Not found'}, status=404)

class MercadoPagoWebhookView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        topic = request.data.get('type')
        data_id = request.data.get('data', {}).get('id')
        
        event_id = request.headers.get('x-request-id') or data_id
        if event_id and PaymentEvent.objects.filter(event_id=str(event_id)).exists():
             return Response(status=200)

        if event_id:
             PaymentEvent.objects.create(
                 provider='mercadopago',
                 event_id=str(event_id),
                 resource_id=str(data_id) if data_id else '',
                 payload_json=request.data
             )
        
        if topic == 'subscription_preapproval':
             self.process_subscription_event(data_id)
        
        return Response(status=200)

    def process_subscription_event(self, preapproval_id):
        if not preapproval_id:
            return

        mp_service = MercadoPagoService()
        preapproval = mp_service.get_preapproval(preapproval_id)
        
        if not preapproval:
            return

        external_reference = preapproval.get('external_reference')
        if not external_reference:
            return

        try:
            intent = SubscriptionIntent.objects.get(id=external_reference)
        except (SubscriptionIntent.DoesNotExist, ValueError):
            return

        status_val = preapproval.get('status')
        
        if status_val == 'authorized':
             self.activate_tenant(intent, preapproval_id)

    def activate_tenant(self, intent, preapproval_id):
        with transaction.atomic():
            ticket = intent.tenant
            if ticket.status != 'active':
                ticket.status = 'active'
                ticket.save()
            
            if intent.status != 'confirmed':
                intent.status = 'confirmed'
                intent.confirmed_at = timezone.now()
                intent.save()
            
            sub = Subscription.objects.filter(mp_preapproval_id=preapproval_id).first()
            if sub:
                sub.status = 'active'
                sub.save()
            
            Membership.objects.get_or_create(
                user=intent.user,
                business=intent.tenant,
                defaults={'role': 'owner'}
            )


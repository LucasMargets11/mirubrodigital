from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action

from apps.accounts.access import resolve_business_context, resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership

from .models import Module, Bundle, Promotion, Subscription
from .serializers import (
    ModuleSerializer, BundleSerializer, PromotionSerializer, 
    QuoteRequestSerializer, SubscribeRequestSerializer, SubscriptionSerializer
)
from .services import PricingService

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

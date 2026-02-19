from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from apps.business.context import build_business_context
from apps.business.service_catalog import serialize_catalog
from apps.business.entitlements import get_effective_entitlements
from apps.business.models import (
	CommercialSettings, 
	Business, 
	Subscription, 
	BusinessPlan,
	BusinessBillingProfile,
	BusinessBranding,
)
from apps.business.serializers import (
	CommercialSettingsSerializer, 
	BranchSerializer, 
	BranchCreateSerializer,
	BusinessBillingProfileSerializer,
	BusinessBrandingSerializer,
)
from rest_framework import viewsets, status
from django.db import transaction
from apps.accounts.models import Membership


class ServiceHubView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership]

	def get(self, request):
		business = getattr(request, 'business', None)
		context = build_business_context(business)

		return Response(
			{
				'available': serialize_catalog(),
				'enabled': context['enabled_services'],
				'default': context['service'],
				'feature_flags': context['features'],
			}
		)


class CommercialSettingsView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'manage_commercial_settings'

	def _get_settings(self, request):
		business = getattr(request, 'business', None)
		return CommercialSettings.objects.for_business(business)

	def get(self, request):
		settings = self._get_settings(request)
		serializer = CommercialSettingsSerializer(settings, context={'request': request})
		return Response(serializer.data)

	def patch(self, request):
		settings = self._get_settings(request)
		serializer = CommercialSettingsSerializer(
			settings,
			data=request.data,
			partial=True,
			context={'request': request},
		)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data)


class BranchViewSet(viewsets.ModelViewSet):
	permission_classes = [IsAuthenticated, HasBusinessMembership]

	def get_queryset(self):
		hq = getattr(self.request, 'business', None)
		if not hq:
			return Business.objects.none()
		return Business.objects.filter(parent=hq)

	def get_serializer_class(self):
		if self.action == 'create':
			return BranchCreateSerializer
		return BranchSerializer

	def create(self, request, *args, **kwargs):
		hq = request.business  # HasBusinessMembership ensures this exists
		if hq.parent is not None:
			return Response(
				{'detail': 'Solo una cuenta principal (HQ) puede crear sucursales.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		sub = getattr(hq, 'subscription', None)
		max_branches = sub.max_branches if sub else 0
		current_branches = hq.branches.count()

		if current_branches >= max_branches:
			return Response(
				{'detail': f'Has alcanzado el límite de sucursales ({max_branches}) de tu plan.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		serializer = BranchCreateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		with transaction.atomic():
			branch = Business.objects.create(
				parent=hq,
				name=serializer.validated_data['name'],
				status='active',
				default_service=hq.default_service,
			)
			# Inherit plan or set default? For MVP same plan type but independent subscription object
			Subscription.objects.create(
				business=branch,
				plan=sub.plan if sub else BusinessPlan.STARTER,
				service=sub.service if sub else hq.default_service,
			)

			# Auto-add creator as owner so they can switch to it
			Membership.objects.create(user=request.user, business=branch, role='owner')
		
		return Response(BranchSerializer(branch).data, status=status.HTTP_201_CREATED)


class BusinessBillingProfileView(APIView):
	"""Vista para obtener y actualizar el perfil de facturación del negocio."""
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'manage_commercial_settings'

	def _get_profile(self, request):
		business = getattr(request, 'business', None)
		return BusinessBillingProfile.objects.get(business=business)

	def get(self, request):
		profile = self._get_profile(request)
		serializer = BusinessBillingProfileSerializer(profile, context={'request': request})
		return Response(serializer.data)

	def patch(self, request):
		profile = self._get_profile(request)
		serializer = BusinessBillingProfileSerializer(
			profile,
			data=request.data,
			partial=True,
			context={'request': request},
		)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data)


class BusinessBrandingView(APIView):
	"""Vista para obtener y actualizar el branding del negocio."""
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	parser_classes = [MultiPartParser, FormParser]
	required_permission = 'manage_commercial_settings'

	def _get_branding(self, request):
		business = getattr(request, 'business', None)
		return BusinessBranding.objects.get(business=business)

	def get(self, request):
		branding = self._get_branding(request)
		serializer = BusinessBrandingSerializer(branding, context={'request': request})
		return Response(serializer.data)

	def patch(self, request):
		branding = self._get_branding(request)
		serializer = BusinessBrandingSerializer(
			branding,
			data=request.data,
			partial=True,
			context={'request': request},
		)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data)


class BusinessEntitlementsView(APIView):
	"""
	Vista para obtener los entitlements (features habilitadas) del business actual.
	Este endpoint es usado por el frontend para feature gating en UI.
	"""
	permission_classes = [IsAuthenticated, HasBusinessMembership]

	def get(self, request):
		business = getattr(request, 'business', None)
		
		# Obtener subscription y calcular entitlements
		try:
			subscription = business.subscription
			entitlements = list(get_effective_entitlements(subscription))
			
			# Info adicional sobre el plan
			plan_info = {
				'plan': subscription.plan,
				'status': subscription.status,
				'max_branches': subscription.max_branches,
				'max_seats': subscription.max_seats,
				'effective_max_branches': subscription.effective_max_branches,
				'effective_max_seats': subscription.effective_max_seats,
			}
			
			# Listar add-ons activos
			addons = []
			if hasattr(subscription, 'addons'):
				addons = [
					{
						'code': addon.code,
						'quantity': addon.quantity,
						'is_active': addon.is_active,
					}
					for addon in subscription.addons.filter(is_active=True)
				]
			
		except Subscription.DoesNotExist:
			entitlements = []
			plan_info = {
				'plan': 'none',
				'status': 'inactive',
				'max_branches': 0,
				'max_seats': 0,
				'effective_max_branches': 0,
				'effective_max_seats': 0,
			}
			addons = []
		
		return Response({
			'entitlements': entitlements,
			'plan': plan_info,
			'addons': addons,
		})

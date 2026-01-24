from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from apps.business.context import build_business_context
from apps.business.service_catalog import serialize_catalog
from apps.business.models import CommercialSettings
from apps.business.serializers import CommercialSettingsSerializer


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

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership
from apps.business.context import build_business_context
from apps.business.service_catalog import serialize_catalog


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

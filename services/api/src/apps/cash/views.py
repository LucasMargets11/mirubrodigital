from __future__ import annotations

from datetime import datetime

from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, HasPermission
from .models import CashMovement, CashRegister, CashSession, Payment
from .serializers import (
	CashMovementCreateSerializer,
	CashMovementSerializer,
	CashPaymentCreateSerializer,
	CashPaymentSerializer,
	CashRegisterSerializer,
	CashSessionCloseSerializer,
	CashSessionOpenSerializer,
	CashSessionSerializer,
)
from .services import get_active_session


class CashRegisterListView(generics.ListAPIView):
	serializer_class = CashRegisterSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_cash'

	def get_queryset(self):
		business = getattr(self.request, 'business')
		return CashRegister.objects.filter(business=business).order_by('name')


class CashSessionOpenView(generics.CreateAPIView):
	serializer_class = CashSessionOpenSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'manage_cash'

	def get_serializer_context(self):
		context = super().get_serializer_context()
		context['business'] = getattr(self.request, 'business')
		context['user'] = self.request.user
		return context


class ActiveCashSessionView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_cash'

	def get(self, request):
		business = getattr(request, 'business')
		register_id = request.query_params.get('register_id')
		session = get_active_session(business, register_id)
		if session is None:
			return Response({'session': None})
		serializer = CashSessionSerializer(session, context={'request': request})
		return Response({'session': serializer.data})


class CashSummaryView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_cash'

	def get(self, request):
		business = getattr(request, 'business')
		session_id = request.query_params.get('session_id')
		if session_id:
			session = get_object_or_404(
				CashSession.objects.select_related('register', 'opened_by', 'closed_by'), pk=session_id, business=business
			)
		else:
			session = get_active_session(business)
		if session is None:
			return Response({'session': None})
		serializer = CashSessionSerializer(session, context={'request': request})
		return Response({'session': serializer.data})


class CashSessionSummaryView(generics.RetrieveAPIView):
	serializer_class = CashSessionSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'view_cash'

	def get_queryset(self):
		business = getattr(self.request, 'business')
		return CashSession.objects.filter(business=business).select_related('register', 'opened_by', 'closed_by')


class CashSessionCloseView(APIView):
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	required_permission = 'manage_cash'

	def post(self, request, pk: str):
		business = getattr(request, 'business')
		session = get_object_or_404(CashSession.objects.select_related('register', 'opened_by', 'closed_by'), pk=pk, business=business)
		serializer = CashSessionCloseSerializer(data=request.data, context={'session': session, 'user': request.user})
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data)


class CashPaymentView(generics.ListCreateAPIView):
	serializer_class = CashPaymentSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_cash',
		'POST': 'manage_cash',
	}

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = Payment.objects.filter(business=business).select_related('sale', 'session')

		session_id = self.request.query_params.get('session_id')
		if session_id:
			queryset = queryset.filter(session_id=session_id)

		sale_id = self.request.query_params.get('sale_id')
		if sale_id:
			queryset = queryset.filter(sale_id=sale_id)

		date_from = self._parse_date(self.request.query_params.get('date_from'))
		if date_from:
			queryset = queryset.filter(created_at__date__gte=date_from)

		date_to = self._parse_date(self.request.query_params.get('date_to'))
		if date_to:
			queryset = queryset.filter(created_at__date__lte=date_to)

		return queryset.order_by('-created_at')

	def get_serializer_class(self):
		if self.request.method == 'POST':
			return CashPaymentCreateSerializer
		return CashPaymentSerializer

	def get_serializer_context(self):
		context = super().get_serializer_context()
		context['business'] = getattr(self.request, 'business')
		context['user'] = self.request.user
		return context

	@staticmethod
	def _parse_date(value: str | None):
		if not value:
			return None
		try:
			return datetime.fromisoformat(value).date()
		except ValueError:
			return None


class CashMovementView(generics.ListCreateAPIView):
	serializer_class = CashMovementSerializer
	permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
	permission_map = {
		'GET': 'view_cash',
		'POST': 'manage_cash',
	}

	def get_queryset(self):
		business = getattr(self.request, 'business')
		queryset = CashMovement.objects.filter(business=business).select_related('session', 'created_by')

		session_id = self.request.query_params.get('session_id')
		if session_id:
			queryset = queryset.filter(session_id=session_id)

		movement_type = self.request.query_params.get('movement_type')
		if movement_type in dict(CashMovement.MovementType.choices):
			queryset = queryset.filter(movement_type=movement_type)

		return queryset.order_by('-created_at')

	def get_serializer_class(self):
		if self.request.method == 'POST':
			return CashMovementCreateSerializer
		return CashMovementSerializer

	def get_serializer_context(self):
		context = super().get_serializer_context()
		context['business'] = getattr(self.request, 'business')
		context['user'] = self.request.user
		return context

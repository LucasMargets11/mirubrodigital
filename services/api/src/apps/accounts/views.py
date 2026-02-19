from __future__ import annotations

from typing import Dict, List

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.access import (
	BUSINESS_COOKIE_MAX_AGE,
	BUSINESS_COOKIE_NAME,
	list_user_memberships,
	select_membership,
)
from apps.accounts.rbac import permissions_for_service
from apps.business.context import build_business_context
from apps.business.models import Business, Subscription, BusinessPlan
from apps.business.service_catalog import serialize_catalog
from .models import Membership
from .serializers import LoginSerializer, RegisterSerializer

User = get_user_model()

def _set_auth_cookies(response: Response, refresh_token: RefreshToken) -> None:
	access_token = refresh_token.access_token
	response.set_cookie(
		'access_token',
		str(access_token),
		httponly=True,
		secure=settings.AUTH_COOKIE_SECURE,
		samesite=settings.AUTH_COOKIE_SAMESITE,
		domain=settings.AUTH_COOKIE_DOMAIN or None,
		max_age=settings.AUTH_COOKIE_ACCESS_MAX_AGE,
		path=settings.AUTH_COOKIE_PATH,
	)
	response.set_cookie(
		'refresh_token',
		str(refresh_token),
		httponly=True,
		secure=settings.AUTH_COOKIE_SECURE,
		samesite=settings.AUTH_COOKIE_SAMESITE,
		domain=settings.AUTH_COOKIE_DOMAIN or None,
		max_age=settings.AUTH_COOKIE_REFRESH_MAX_AGE,
		path=settings.AUTH_COOKIE_PATH,
	)


def _clear_auth_cookies(response: Response) -> None:
	response.delete_cookie('access_token', domain=settings.AUTH_COOKIE_DOMAIN or None, path=settings.AUTH_COOKIE_PATH)
	response.delete_cookie('refresh_token', domain=settings.AUTH_COOKIE_DOMAIN or None, path=settings.AUTH_COOKIE_PATH)


def _set_business_cookie(response: Response, business_id: int) -> None:
	response.set_cookie(
		BUSINESS_COOKIE_NAME,
		str(business_id),
		httponly=True,
		secure=settings.AUTH_COOKIE_SECURE,
		samesite=settings.AUTH_COOKIE_SAMESITE,
		domain=settings.AUTH_COOKIE_DOMAIN or None,
		max_age=BUSINESS_COOKIE_MAX_AGE,
		path=settings.AUTH_COOKIE_PATH,
	)


def _clear_business_cookie(response: Response) -> None:
	response.delete_cookie(BUSINESS_COOKIE_NAME, domain=settings.AUTH_COOKIE_DOMAIN or None, path=settings.AUTH_COOKIE_PATH)


def _clear_session_cookies(response: Response) -> None:
	_clear_auth_cookies(response)
	_clear_business_cookie(response)


@transaction.atomic
def _ensure_membership(user: User) -> Membership:
	membership = (
		Membership.objects.select_related('business', 'business__subscription')
		.filter(user=user)
		.first()
	)
	if membership:
		if not hasattr(membership.business, 'subscription'):
			Subscription.objects.create(
				business=membership.business,
				service=membership.business.default_service or 'gestion',
			)
		return membership

	business_name = user.get_full_name() or user.email or user.get_username()
	business = Business.objects.create(name=f"{business_name} HQ")
	Subscription.objects.create(
		business=business,
		plan=BusinessPlan.STARTER,
		status='active',
		service=business.default_service,
	)
	membership = Membership.objects.create(user=user, business=business, role='owner')
	return membership


def _session_payload(user: User, membership: Membership, memberships: List[Membership]) -> Dict[str, object]:
	context = build_business_context(membership.business)
	service_catalog = serialize_catalog()
	permissions = permissions_for_service(context['service'], membership.role)
	return {
		'user': {
			'id': user.id,
			'email': user.email,
			'name': user.get_full_name() or user.get_username(),
		},
		'memberships': [
			{
				'business': {
					'id': member.business_id,
					'name': member.business.name,
				},
				'role': member.role,
				'service': build_business_context(member.business)['service'],
			}
			for member in memberships
		],
		'current': {
			'business': {
				'id': membership.business_id,
				'name': membership.business.name,
			},
			'role': membership.role,
			'service': context['service'],
		},
		'subscription': {
			'plan': context['plan'],
			'status': context['status'],
		},
		'services': {
			'available': service_catalog,
			'enabled': context['enabled_services'],
			'default': context['service'],
		},
		'features': context['features'],
		'permissions': permissions,
	}


class LoginView(APIView):
	permission_classes = [AllowAny]
	authentication_classes: list = []

	def post(self, request: Request) -> Response:
		serializer = LoginSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		email = serializer.validated_data['email'].lower()
		password = serializer.validated_data['password']

		try:
			user = User.objects.get(email__iexact=email)
		except User.DoesNotExist:
			return Response({'detail': 'Credenciales inválidas'}, status=status.HTTP_400_BAD_REQUEST)

		if not user.is_active:
			return Response({'detail': 'Usuario inactivo'}, status=status.HTTP_400_BAD_REQUEST)

		authenticated_user = authenticate(request=request, username=user.get_username(), password=password)
		if authenticated_user is None:
			return Response({'detail': 'Credenciales inválidas'}, status=status.HTTP_400_BAD_REQUEST)

		membership = _ensure_membership(authenticated_user)
		refresh = RefreshToken.for_user(authenticated_user)
		response = Response({'status': 'ok'})
		_set_auth_cookies(response, refresh)
		_set_business_cookie(response, membership.business_id)
		return response


class RegisterView(APIView):
	permission_classes = [AllowAny]
	authentication_classes: list = []

	def post(self, request: Request) -> Response:
		serializer = RegisterSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		email = serializer.validated_data['email'].lower()
		password = serializer.validated_data['password']

		# Verificar si el usuario ya existe
		if User.objects.filter(email__iexact=email).exists():
			return Response({'detail': 'El email ya está registrado'}, status=status.HTTP_400_BAD_REQUEST)

		# Crear usuario
		user = User.objects.create_user(
			username=email,
			email=email,
			password=password,
		)

		return Response({
			'status': 'created',
			'user': {
				'id': user.id,
				'email': user.email,
			}
		}, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
	permission_classes = [AllowAny]
	authentication_classes: list = []

	def post(self, _request: Request) -> Response:
		response = Response({'status': 'logged_out'})
		_clear_session_cookies(response)
		return response


class RefreshView(APIView):
	permission_classes = [AllowAny]
	authentication_classes: list = []

	def post(self, request: Request) -> Response:
		raw_refresh = request.COOKIES.get('refresh_token')
		if not raw_refresh:
			response = Response({'detail': 'Refresh token faltante'}, status=status.HTTP_401_UNAUTHORIZED)
			_clear_session_cookies(response)
			return response

		try:
			refresh = RefreshToken(raw_refresh)
			user = User.objects.get(id=refresh['user_id'])
		except (TokenError, User.DoesNotExist, KeyError):
			response = Response({'detail': 'Refresh token inválido'}, status=status.HTTP_401_UNAUTHORIZED)
			_clear_session_cookies(response)
			return response

		new_refresh = RefreshToken.for_user(user)
		response = Response({'status': 'refreshed'})
		_set_auth_cookies(response, new_refresh)
		return response


class MeView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request: Request) -> Response:
		memberships = list_user_memberships(request.user)
		if not memberships:
			membership = _ensure_membership(request.user)
			memberships = [membership]
		else:
			membership = select_membership(memberships, request.COOKIES.get(BUSINESS_COOKIE_NAME)) or memberships[0]
		payload = _session_payload(request.user, membership, memberships)
		response = Response(payload)
		cookie_business = request.COOKIES.get(BUSINESS_COOKIE_NAME)
		if cookie_business != str(membership.business_id):
			_set_business_cookie(response, membership.business_id)
		return response


class SwitchBusinessSerializer(serializers.Serializer):
	business_id = serializers.IntegerField()


class SwitchBusinessView(APIView):
	permission_classes = [IsAuthenticated]

	def post(self, request: Request) -> Response:
		serializer = SwitchBusinessSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		memberships = list_user_memberships(request.user)
		if not memberships:
			membership = _ensure_membership(request.user)
			memberships = [membership]
		business_id = serializer.validated_data['business_id']
		membership = next((member for member in memberships if member.business_id == business_id), None)
		if membership is None:
			return Response({'detail': 'No perteneces a este negocio.'}, status=status.HTTP_404_NOT_FOUND)
		payload = _session_payload(request.user, membership, memberships)
		response = Response(payload)
		_set_business_cookie(response, membership.business_id)
		return response

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
from apps.accounts.models import AccessAuditLog, AccountProfile
from apps.accounts.rbac import permissions_for_service
from apps.accounts.services import EmailService
from apps.business.context import build_business_context
from apps.business.models import Business, Subscription, BusinessPlan
from apps.business.service_catalog import serialize_catalog
from .models import Membership
from .serializers import (
    ForgotPasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    VerifyEmailSerializer,
)


logger = __import__('logging').getLogger(__name__)

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
	"""
	Ensure the user has at least one Business + Membership.

	BIRTH PATH CLOSURE (Phase 3):
	  - No legacy Subscription is created here — access is gated by billing.
	  - A newly created Business starts with status='onboarding'; it will be
	    set to 'active' only by subscription_activator after a confirmed payment.
	  - Existing memberships are returned as-is regardless of subscription state.

	TODO (legacy cleanup): The branch that auto-created Subscription for an
	existing business without one has been removed.  Any existing business rows
	without a Subscription will surface as source='none' via runtime resolver,
	which correctly sets access_allowed=False until billing completes.
	"""
	membership = (
		Membership.objects.select_related('business')
		.filter(user=user)
		.first()
	)
	if membership:
		return membership

	# Brand-new user — create business in onboarding state.  No Subscription.
	business_name = user.get_full_name() or user.email or user.get_username()
	business = Business.objects.create(
		name=f"{business_name} HQ",
		status='onboarding',
	)
	membership = Membership.objects.create(user=user, business=business, role='owner')
	logger.info(
		"[_ensure_membership] Created business=%s status=onboarding user=%s — "
		"no subscription created; billing required before access is granted.",
		business.pk, user.pk,
	)
	return membership


def _session_payload(user: User, membership: Membership, memberships: List[Membership]) -> Dict[str, object]:
	context = build_business_context(membership.business)
	service_catalog = serialize_catalog()
	permissions = permissions_for_service(context['service'], membership.role)
	profile = getattr(user, 'account_profile', None)
	return {
		'user': {
			'id': user.id,
			'email': user.email,
			'name': user.get_full_name() or user.get_username(),
			'email_verified': profile.email_verified if profile else False,
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
				# B.2: expose business lifecycle status for onboarding routing.
				# 'onboarding' → redirect to subscription setup.
				# 'active' → normal app access.
				'status': membership.business.status,
			},
			'role': membership.role,
			'service': context['service'],
		},
		'subscription': {
			'plan': context['plan'],
			'status': context['status'],
			# source field: 'v2' | 'legacy' | 'none' — for debugging and
			# gradual-migration observability.  Non-breaking addition.
			'source': context.get('_subscription_source', 'unknown'),
			# Enforcement fields: allow frontend to act on subscription state.
			'access_allowed': context.get('access_allowed', False),
			'reason_code': context.get('reason_code', 'no_subscription'),
			'grace_until': context.get('grace_until'),
			'access_until': context.get('access_until'),
			'show_renewal_prompt': context.get('show_renewal_prompt', False),
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
		response = Response({'status': 'ok', 'onboarding': membership.business.status == 'onboarding'})
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

		# Ensure AccountProfile exists (signal creates it, but be defensive)
		profile, _ = AccountProfile.objects.get_or_create(user=user)

		# Generate verification token and send email (non-blocking — failure is logged)
		token = profile.generate_verification_token()
		email_sent = EmailService.send_verification_email(user, token)

		return Response({
			'status': 'created',
			'user': {
				'id': user.id,
				'email': user.email,
			},
			'verification_email_sent': email_sent,
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


# ─────────────────────────────────────────────────────────────────────────────
# Email Verification
# ─────────────────────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
	x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
	if x_forwarded_for:
		return x_forwarded_for.split(',')[0].strip()
	return request.META.get('REMOTE_ADDR', '')


class VerifyEmailView(APIView):
	"""
	POST /api/v1/auth/verify-email/
	Body: { "token": "<plaintext token from email link>" }

	Verifies the email address for an unverified account.
	Returns 200 on success, 400 on invalid/expired token.
	Fires ACCESS_DENIED audit log on invalid token attempt.
	"""
	permission_classes = [AllowAny]
	authentication_classes: list = []

	def post(self, request: Request) -> Response:
		serializer = VerifyEmailSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		token = serializer.validated_data['token']

		profile = (
			AccountProfile.objects
			.select_related('user')
			.filter(email_verification_token_hash__isnull=False)
			.first()
		)
		# We must find the profile by trying all with a set hash — but hashing first
		# avoids full-table scan because we indexed the hash column.
		from apps.accounts.models import AccountProfile as AP
		import hashlib
		token_hash = hashlib.sha256(token.encode()).hexdigest()
		try:
			profile = AP.objects.select_related('user').get(
				email_verification_token_hash=token_hash
			)
		except AP.DoesNotExist:
			return Response(
				{'detail': 'El enlace de verificación no es válido o ya expiró.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		if not profile.verify_email_token(token):
			return Response(
				{'detail': 'El enlace de verificación ha expirado. Solicitá uno nuevo.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		# Audit
		try:
			business = profile.user.memberships.filter(
				role='owner'
			).select_related('business').first()
			if business:
				AccessAuditLog.objects.create(
					action='EMAIL_VERIFIED',
					actor=profile.user,
					target_user=profile.user,
					business=business.business,
					details={'email': profile.user.email},
					ip_address=_get_client_ip(request),
					user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
				)
		except Exception:
			logger.exception("[VerifyEmailView] Could not write audit log for user=%s", profile.user_id)

		return Response({'status': 'verified', 'email': profile.user.email})


class ResendVerificationView(APIView):
	"""
	POST /api/v1/auth/resend-verification/
	Requires authentication (user must be logged in).
	Generates a new verification token and resends the email.
	"""
	permission_classes = [IsAuthenticated]

	def post(self, request: Request) -> Response:
		user = request.user
		profile, _ = AccountProfile.objects.get_or_create(user=user)

		if profile.email_verified:
			return Response({'detail': 'El email ya está verificado.'}, status=status.HTTP_400_BAD_REQUEST)

		token = profile.generate_verification_token()
		sent = EmailService.send_verification_email(user, token)

		return Response({
			'status': 'sent' if sent else 'queued',
			'message': 'Se envió un nuevo correo de verificación.' if sent else 'Verificación solicitada.',
		})


# ─────────────────────────────────────────────────────────────────────────────
# Self-service Password Recovery
# ─────────────────────────────────────────────────────────────────────────────

class ForgotPasswordView(APIView):
	"""
	POST /api/v1/auth/forgot-password/
	Body: { "email": "user@example.com" }

	Always returns 200 regardless of whether the email exists (prevents enumeration).
	Sends a reset link to the email if an account is found.
	"""
	permission_classes = [AllowAny]
	authentication_classes: list = []

	def post(self, request: Request) -> Response:
		serializer = ForgotPasswordSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		email = serializer.validated_data['email'].lower()

		# Silently succeed whether or not the email exists (anti-enumeration)
		try:
			user = User.objects.get(email__iexact=email, is_active=True)
			profile, _ = AccountProfile.objects.get_or_create(user=user)
			token = profile.generate_password_reset_token()
			EmailService.send_password_reset_email(user, token)

			# Audit — best-effort (don't fail the request if no business)
			try:
				membership = user.memberships.filter(role='owner').select_related('business').first()
				if membership:
					AccessAuditLog.objects.create(
						action='PASSWORD_RESET_CONFIRMED',  # "requested" intent
						actor=user,
						target_user=user,
						business=membership.business,
						details={'source': 'self_service', 'email': email},
						ip_address=_get_client_ip(request),
						user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
					)
			except Exception:
				logger.exception("[ForgotPasswordView] Audit log failed for user=%s", user.pk)

		except User.DoesNotExist:
			# Do not reveal that the email doesn't exist
			pass

		return Response({
			'status': 'ok',
			'message': 'Si el email está registrado, recibirás un enlace para restablecer tu contraseña.',
		})


class ResetPasswordView(APIView):
	"""
	POST /api/v1/auth/reset-password/
	Body: { "token": "<plaintext token>", "new_password": "..." }

	Validates the password-reset token and changes the password.
	The token is single-use and expires after PASSWORD_RESET_TOKEN_HOURS hours.
	"""
	permission_classes = [AllowAny]
	authentication_classes: list = []

	def post(self, request: Request) -> Response:
		serializer = ResetPasswordSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		token = serializer.validated_data['token']
		new_password = serializer.validated_data['new_password']

		import hashlib
		token_hash = hashlib.sha256(token.encode()).hexdigest()

		try:
			profile = (
				AccountProfile.objects
				.select_related('user')
				.get(password_reset_token_hash=token_hash)
			)
		except AccountProfile.DoesNotExist:
			return Response(
				{'detail': 'El enlace para restablecer la contraseña no es válido o ya expiró.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		if not profile.verify_password_reset_token(token):
			return Response(
				{'detail': 'El enlace para restablecer la contraseña ha expirado. Solicitá uno nuevo.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		user = profile.user
		user.set_password(new_password)
		user.save(update_fields=['password'])

		# Audit
		try:
			membership = user.memberships.filter(role='owner').select_related('business').first()
			if membership:
				AccessAuditLog.objects.create(
					action='PASSWORD_RESET',
					actor=user,
					target_user=user,
					business=membership.business,
					details={'source': 'self_service'},
					ip_address=_get_client_ip(request),
					user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
				)
		except Exception:
			logger.exception("[ResetPasswordView] Audit log failed for user=%s", user.pk)

		return Response({'status': 'ok', 'message': 'Tu contraseña fue restablecida exitosamente.'})


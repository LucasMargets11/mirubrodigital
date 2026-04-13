from __future__ import annotations

import ipaddress
from typing import Dict, List

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
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
from apps.accounts import auth_rate_limiter
from apps.accounts import security_events
from apps.accounts.models import AccessAuditLog, AccountProfile
from apps.accounts.rbac import permissions_for_service
from apps.accounts.services import EmailService
from apps.accounts.tasks import send_verification_email_task
from apps.accounts.throttles import (
    ForgotPasswordThrottle,
    GoogleAuthThrottle,
    LoginThrottle,
    RefreshTokenThrottle,
    RegisterThrottle,
    ResetPasswordThrottle,
    VerifyEmailThrottle,
)
from apps.business.context import build_business_context
from apps.business.models import Business, Subscription, BusinessPlan
from apps.business.service_catalog import serialize_catalog
from .models import Membership
from .serializers import (
    ForgotPasswordSerializer,
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
			'account_mode': profile.account_mode if profile else 'owner_managed',
			'must_change_password': profile.must_change_password if profile else False,
			'auth_provider': profile.auth_provider if profile else 'email',
			'has_google_linked': bool(profile.google_sub) if profile else False,
			'has_password': user.has_usable_password(),
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
	throttle_classes = [LoginThrottle]

	def post(self, request: Request) -> Response:
		# Accept either email or username field for backward compatibility.
		# Internal users log in with username; owners log in with email.
		identifier = (
			request.data.get('email', '')
			or request.data.get('username', '')
		).strip()
		password = request.data.get('password', '')

		if not identifier or not password:
			return Response({'detail': 'Credenciales inválidas'}, status=status.HTTP_400_BAD_REQUEST)

		# ── 3D rate limiter (IP + identifier + combo) ──────────────────
		client_ip = _get_client_ip(request)
		rl_result = auth_rate_limiter.check_rate_limit(client_ip, identifier)
		if not rl_result.allowed:
			security_events.ratelimit_triggered(ip=client_ip, email=identifier, reason=rl_result.reason)
			return Response(
				{'detail': rl_result.reason},
				status=status.HTTP_429_TOO_MANY_REQUESTS,
				headers={'Retry-After': str(rl_result.retry_after)},
			)

		# Use custom backend which tries email first, then username.
		authenticated_user = authenticate(request=request, username=identifier, password=password)
		if authenticated_user is None:
			auth_rate_limiter.record_failed_attempt(client_ip, identifier)
			security_events.login_failed(email=identifier, ip=client_ip)
			return Response({'detail': 'Credenciales inválidas'}, status=status.HTTP_400_BAD_REQUEST)

		if not authenticated_user.is_active:
			auth_rate_limiter.record_failed_attempt(client_ip, identifier)
			security_events.login_failed(email=identifier, ip=client_ip, reason='inactive_user')
			return Response({'detail': 'Credenciales inválidas'}, status=status.HTTP_400_BAD_REQUEST)

		auth_rate_limiter.reset_on_success(client_ip, identifier)
		membership = _ensure_membership(authenticated_user)
		refresh = RefreshToken.for_user(authenticated_user)
		response = Response({'status': 'ok', 'onboarding': membership.business.status == 'onboarding'})
		_set_auth_cookies(response, refresh)
		_set_business_cookie(response, membership.business_id)
		security_events.login_success(user_id=authenticated_user.pk, email=authenticated_user.email, ip=client_ip)
		return response


class RegisterView(APIView):
	permission_classes = [AllowAny]
	authentication_classes: list = []
	throttle_classes = [RegisterThrottle]

	# Anti-enumeration: both branches return 201 with the same shape.
	_SAFE_RESPONSE = {
		'status': 'created',
		'message': 'Revisa tu email para verificar tu cuenta.',
	}

	def post(self, request: Request) -> Response:
		serializer = RegisterSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		email = serializer.validated_data['email'].lower()
		password = serializer.validated_data['password']

		# Anti-enumeration: if the email already exists, return the exact
		# same HTTP status and payload as a successful registration.  No
		# verification email is sent (the existing user is not affected).
		if User.objects.filter(email__iexact=email).exists():
			logger.info('[RegisterView] Suppressed duplicate registration for email=%s', email)
			return Response(self._SAFE_RESPONSE, status=status.HTTP_201_CREATED)

		try:
			with transaction.atomic():
				user = User.objects.create_user(
					username=email,
					email=email,
					password=password,
				)

				# Ensure AccountProfile exists (signal creates it, but be defensive)
				profile, _ = AccountProfile.objects.get_or_create(user=user)

				# Generate token inside atomic so it's committed with the user.
				token = profile.generate_verification_token()
				# Enqueue Celery task after commit — no sync work in the request.
				# This closes the timing side-channel: both the "existing email"
				# and "new user" paths return immediately with the same cost.
				transaction.on_commit(
					lambda: send_verification_email_task.delay(user.id, token)
				)
		except IntegrityError:
			# Concurrent request created the same user between our exists()
			# check and create_user(). Return the safe response to maintain
			# anti-enumeration and avoid 500.
			logger.info('[RegisterView] IntegrityError (race) for email=%s', email)
			return Response(self._SAFE_RESPONSE, status=status.HTTP_201_CREATED)

		return Response(self._SAFE_RESPONSE, status=status.HTTP_201_CREATED)



class LogoutView(APIView):
	permission_classes = [AllowAny]
	authentication_classes: list = []

	def post(self, request: Request) -> Response:
		# Revoke the refresh token server-side BEFORE clearing cookies.
		# Gracefully handles: no cookie, expired token, already-blacklisted token.
		raw_refresh = request.COOKIES.get('refresh_token')
		user_id = None
		if raw_refresh:
			try:
				token = RefreshToken(raw_refresh)
				user_id = token.get('user_id')
				token.blacklist()
			except TokenError:
				pass

		security_events.logout_success(user_id=user_id, ip=_get_client_ip(request))
		response = Response({'status': 'logged_out'})
		_clear_session_cookies(response)
		return response


class RefreshView(APIView):
	permission_classes = [AllowAny]
	authentication_classes: list = []
	throttle_classes = [RefreshTokenThrottle]

	def post(self, request: Request) -> Response:
		client_ip = _get_client_ip(request)
		raw_refresh = request.COOKIES.get('refresh_token')
		if not raw_refresh:
			security_events.refresh_failed(ip=client_ip, reason='missing_cookie')
			response = Response({'detail': 'Refresh token faltante'}, status=status.HTTP_401_UNAUTHORIZED)
			_clear_session_cookies(response)
			return response

		try:
			refresh = RefreshToken(raw_refresh)
			user = User.objects.get(id=refresh['user_id'])
		except (TokenError, User.DoesNotExist, KeyError):
			security_events.refresh_failed(ip=client_ip, reason='invalid_token')
			response = Response({'detail': 'Refresh token inválido'}, status=status.HTTP_401_UNAUTHORIZED)
			_clear_session_cookies(response)
			return response

		# Blacklist the old refresh token so it cannot be replayed.
		# This manual call IS required: our view uses RefreshToken.for_user()
		# to issue a new token, which bypasses SimpleJWT's native rotation
		# path (set_jti/set_exp on the same token object).  The native
		# BLACKLIST_AFTER_ROTATION only fires inside TokenRefreshSerializer,
		# which we don't use because we read tokens from httpOnly cookies.
		try:
			refresh.blacklist()
		except TokenError:
			pass

		new_refresh = RefreshToken.for_user(user)
		response = Response({'status': 'refreshed'})
		_set_auth_cookies(response, new_refresh)
		security_events.refresh_success(user_id=user.pk, ip=client_ip)
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

def _normalize_xff_entry(raw: str) -> str:
	"""Normalize an IP extracted from X-Forwarded-For (strip port, brackets)."""
	raw = raw.strip()
	if raw.startswith('['):
		bracket_end = raw.find(']')
		return raw[1:bracket_end] if bracket_end != -1 else raw[1:]
	if raw.count(':') == 1:
		return raw.rsplit(':', 1)[0]
	return raw


def _get_client_ip(request: Request) -> str:
	"""
	Extract the real client IP from behind trusted reverse proxies.

	Counts from the RIGHT of X-Forwarded-For by TRUSTED_PROXY_DEPTH.
	The leftmost entry is client-controlled and MUST NOT be trusted.
	Falls back to REMOTE_ADDR when XFF is absent or malformed.
	"""
	depth = getattr(settings, 'TRUSTED_PROXY_DEPTH', 1)
	xff = request.META.get('HTTP_X_FORWARDED_FOR')
	if xff:
		parts = [p.strip() for p in xff.split(',')]
		if len(parts) >= depth:
			raw = parts[-depth]
			ip_str = _normalize_xff_entry(raw)
			try:
				ipaddress.ip_address(ip_str)
				return ip_str
			except ValueError:
				logger.warning(
					'Invalid IP in X-Forwarded-For at depth -%d: %r', depth, raw,
				)
		else:
			logger.warning(
				'X-Forwarded-For has %d entries but TRUSTED_PROXY_DEPTH=%d; '
				'falling back to REMOTE_ADDR', len(parts), depth,
			)
	return request.META.get('REMOTE_ADDR', '127.0.0.1')


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
	throttle_classes = [VerifyEmailThrottle]

	def post(self, request: Request) -> Response:
		serializer = VerifyEmailSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		token = serializer.validated_data['token']

		# Look up the profile by hashed token (indexed column; avoids full-table scan).
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
	Generates a new verification token and resends the email via Celery.
	"""
	permission_classes = [IsAuthenticated]

	def post(self, request: Request) -> Response:
		user = request.user
		profile, _ = AccountProfile.objects.get_or_create(user=user)

		if profile.email_verified:
			return Response({'detail': 'El email ya está verificado.'}, status=status.HTTP_400_BAD_REQUEST)

		token = profile.generate_verification_token()
		send_verification_email_task.delay(user.id, token)

		return Response({
			'status': 'queued',
			'message': 'Se envió un nuevo correo de verificación.',
		})


# ─────────────────────────────────────────────────────────────────────────────
# Google OAuth
# ─────────────────────────────────────────────────────────────────────────────

class GoogleAuthView(APIView):
	"""
	POST /api/v1/auth/google/
	Body: { "credential": "<Google ID token>" }

	Validates the ID token via google-auth, then:
	  1. Lookup by google_sub → login.
	  2. Lookup by email + link google_sub → login.
	  3. No user → create with auth_provider='google', email_verified=True, no password.
	  4. email_verified=false from Google → reject 400.
	  5. Inactive user → reject 403.
	Emits JWT cookies identical to LoginView.
	"""
	permission_classes = [AllowAny]
	authentication_classes: list = []
	throttle_classes = [GoogleAuthThrottle]

	def post(self, request: Request) -> Response:
		credential = (request.data.get('credential') or '').strip()
		if not credential:
			return Response(
				{'detail': 'Token de Google requerido.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		from apps.accounts.google_oauth_service import GoogleOAuthService

		result = GoogleOAuthService.verify_token(credential)
		if not result.valid:
			return Response(
				{'detail': 'Token de Google inválido o expirado.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		payload = result.payload

		# Google must have verified the email
		if not payload.email_verified:
			return Response(
				{'detail': 'El email de Google no está verificado.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		client_ip = _get_client_ip(request)
		is_new_user = False
		user = None

		# 1. Lookup by google_sub (fastest, unique index)
		try:
			profile = AccountProfile.objects.select_related('user').get(google_sub=payload.sub)
			user = profile.user
		except AccountProfile.DoesNotExist:
			pass

		# 2. Lookup by email and link google_sub
		if user is None:
			try:
				user = User.objects.get(email__iexact=payload.email)
				profile, _ = AccountProfile.objects.get_or_create(user=user)
				if not profile.google_sub:
					profile.google_sub = payload.sub
					update_fields = ['google_sub']
					if not profile.email_verified:
						profile.email_verified = True
						update_fields.append('email_verified')
					profile.save(update_fields=update_fields)
					logger.info('[GoogleAuthView] Linked google_sub=%s to existing user=%s', payload.sub, user.pk)
			except User.DoesNotExist:
				user = None

		# 3. Create new user
		if user is None:
			is_new_user = True
			try:
				with transaction.atomic():
					user = User.objects.create_user(
						username=payload.email,
						email=payload.email,
						first_name=payload.given_name[:30] if payload.given_name else '',
						last_name=payload.family_name[:150] if payload.family_name else '',
					)
					user.set_unusable_password()
					user.save(update_fields=['password'])

					profile, _ = AccountProfile.objects.get_or_create(user=user)
					profile.auth_provider = 'google'
					profile.google_sub = payload.sub
					profile.email_verified = True
					profile.save(update_fields=['auth_provider', 'google_sub', 'email_verified'])
			except IntegrityError:
				# Race condition: concurrent request created the user.
				logger.info('[GoogleAuthView] IntegrityError (race) for email=%s, falling back to login', payload.email)
				user = User.objects.get(email__iexact=payload.email)
				profile, _ = AccountProfile.objects.get_or_create(user=user)
				if not profile.google_sub:
					profile.google_sub = payload.sub
					profile.save(update_fields=['google_sub'])
				is_new_user = False

			logger.info('[GoogleAuthView] Created new user=%s via Google OAuth', user.pk)

		# 4. Check active
		if not user.is_active:
			return Response(
				{'detail': 'Cuenta suspendida.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		# 5. Common path: ensure membership + emit cookies
		membership = _ensure_membership(user)
		refresh = RefreshToken.for_user(user)

		response = Response({
			'status': 'ok',
			'onboarding': membership.business.status == 'onboarding',
			'is_new_user': is_new_user,
		})
		_set_auth_cookies(response, refresh)
		_set_business_cookie(response, membership.business_id)
		security_events.login_success(user_id=user.pk, email=user.email, ip=client_ip)
		return response


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
	throttle_classes = [ForgotPasswordThrottle]

	def post(self, request: Request) -> Response:
		serializer = ForgotPasswordSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		email = serializer.validated_data['email'].lower()

		# Silently succeed whether or not the email exists (anti-enumeration)
		try:
			user = User.objects.get(email__iexact=email, is_active=True)
			profile, _ = AccountProfile.objects.get_or_create(user=user)

			# Owner-managed accounts cannot self-reset — return the same
			# anti-enumeration response without generating a token.
			if not profile.can_self_reset():
				return Response({
					'status': 'ok',
					'message': 'Si el email está registrado, recibirás un enlace para restablecer tu contraseña.',
				})

			token = profile.generate_password_reset_token()
			EmailService.send_password_reset_email(user, token)

			# Audit — best-effort (don't fail the request if no business)
			try:
				membership = user.memberships.filter(role='owner').select_related('business').first()
				if membership:
					AccessAuditLog.objects.create(
						action='PASSWORD_RESET_REQUESTED',
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
	throttle_classes = [ResetPasswordThrottle]

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

		# Only personal accounts may self-reset via token
		if profile.account_mode != AccountProfile.AccountMode.PERSONAL:
			return Response(
				{'detail': 'Tu cuenta es gestionada por el administrador. Contactá al dueño del negocio.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		user = profile.user
		user.set_password(new_password)
		user.save(update_fields=['password'])

		# Clear must_change_password after successful self-reset
		if profile.must_change_password:
			profile.must_change_password = False
			profile.save(update_fields=['must_change_password'])

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


# ─────────────────────────────────────────────────────────────────────────────
# Authenticated Password Change (personal accounts)
# ─────────────────────────────────────────────────────────────────────────────

class ChangePasswordView(APIView):
	"""
	POST /api/v1/auth/change-password/
	Body: { "current_password": "...", "new_password": "..." }

	Allows personal-mode users to change their own password.
	Owner-managed accounts are rejected.
	"""
	permission_classes = [IsAuthenticated]

	def post(self, request: Request) -> Response:
		current_password = request.data.get('current_password', '')
		new_password = request.data.get('new_password', '')

		if not current_password or not new_password:
			return Response(
				{'detail': 'current_password y new_password son requeridos.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		if len(new_password) < 8:
			return Response(
				{'detail': 'La nueva contraseña debe tener al menos 8 caracteres.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		user = request.user
		profile = AccountProfile.objects.filter(user=user).first()

		if not profile or not profile.can_change_password():
			return Response(
				{'detail': 'Tu cuenta es gestionada por el administrador. No podés cambiar la contraseña.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		if not user.check_password(current_password):
			return Response(
				{'detail': 'La contraseña actual es incorrecta.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		user.set_password(new_password)
		user.save(update_fields=['password'])

		# Clear must_change_password
		if profile.must_change_password:
			profile.must_change_password = False
			profile.save(update_fields=['must_change_password'])

		# Re-issue tokens so the user stays logged in
		refresh = RefreshToken.for_user(user)
		response = Response({'status': 'ok', 'message': 'Contraseña actualizada exitosamente.'})
		_set_auth_cookies(response, refresh)

		# Audit
		try:
			membership = user.memberships.select_related('business').first()
			if membership:
				AccessAuditLog.objects.create(
					action='PASSWORD_CHANGED',
					actor=user,
					target_user=user,
					business=membership.business,
					details={'source': 'self_change'},
					ip_address=_get_client_ip(request),
					user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
				)
		except Exception:
			logger.exception("[ChangePasswordView] Audit log failed for user=%s", user.pk)

		return response


class ForceChangePasswordView(APIView):
	"""
	POST /api/v1/auth/force-change-password/
	Body: { "current_password": "...", "new_password": "..." }

	Used when must_change_password=True. The user is forced to change their
	password on the next login. Same logic as ChangePasswordView but
	requires must_change_password flag to be set.
	"""
	permission_classes = [IsAuthenticated]

	def post(self, request: Request) -> Response:
		current_password = request.data.get('current_password', '')
		new_password = request.data.get('new_password', '')

		if not current_password or not new_password:
			return Response(
				{'detail': 'current_password y new_password son requeridos.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		if len(new_password) < 8:
			return Response(
				{'detail': 'La nueva contraseña debe tener al menos 8 caracteres.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		user = request.user
		profile = AccountProfile.objects.filter(user=user).first()

		if not profile or not profile.must_change_password:
			return Response(
				{'detail': 'No se requiere cambio de contraseña.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		if not user.check_password(current_password):
			return Response(
				{'detail': 'La contraseña actual es incorrecta.'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		user.set_password(new_password)
		user.save(update_fields=['password'])

		profile.must_change_password = False
		profile.save(update_fields=['must_change_password'])

		# Re-issue tokens
		refresh = RefreshToken.for_user(user)
		response = Response({'status': 'ok', 'message': 'Contraseña actualizada exitosamente.'})
		_set_auth_cookies(response, refresh)

		# Audit
		try:
			membership = user.memberships.select_related('business').first()
			if membership:
				AccessAuditLog.objects.create(
					action='PASSWORD_FORCE_CHANGED',
					actor=user,
					target_user=user,
					business=membership.business,
					details={'source': 'force_change'},
					ip_address=_get_client_ip(request),
					user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
				)
		except Exception:
			logger.exception("[ForceChangePasswordView] Audit log failed for user=%s", user.pk)

		return response


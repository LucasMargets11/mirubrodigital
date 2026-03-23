"""
Platform admin authentication views (Phase 1.1 hardening).

Implements a separate admin login flow with:
  - Custom rate limiting (IP, email, IP+email)
  - Anti-enumeration (generic error messages, artificial delay)
  - Two-step auth: password → MFA challenge → OTP verify → JWT
  - TOTP enrollment and recovery code management
  - IP allowlist support
  - Comprehensive audit logging

All auth responses are intentionally generic to prevent user enumeration.
"""
import ipaddress
import logging
import time

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.admin_mfa import (
    check_otp_attempts,
    create_mfa_challenge,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    generate_totp_secret,
    get_provisioning_uri,
    hash_recovery_code,
    is_otp_used,
    mark_otp_used,
    record_otp_failure,
    reset_otp_attempts,
    verify_mfa_challenge,
    verify_recovery_code,
    verify_totp,
)
from apps.accounts.admin_rate_limiter import (
    check_rate_limit,
    record_failed_attempt,
    reset_on_success,
)
from apps.accounts.models import AccessAuditLog, AccountProfile
from apps.accounts.platform_permissions import IsPlatformStaff

logger = logging.getLogger(__name__)

User = get_user_model()

# ── Shared constants ─────────────────────────────────────────────────────────

GENERIC_ERROR = 'Credenciales inválidas o acceso temporalmente restringido.'

# Shorter JWT lifetime for admin sessions
ADMIN_ACCESS_TOKEN_MINUTES = int(getattr(settings, 'ADMIN_ACCESS_TOKEN_MINUTES', 15))
ADMIN_REFRESH_TOKEN_HOURS = int(getattr(settings, 'ADMIN_REFRESH_TOKEN_HOURS', 4))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalize_xff_entry(raw: str) -> str:
    """
    Normalize an IP string extracted from X-Forwarded-For.

    Handles:
      - IPv4 with port: ``1.2.3.4:8080`` → ``1.2.3.4``
      - IPv6 with brackets: ``[::1]`` → ``::1``
      - IPv6 with brackets + port: ``[::1]:8080`` → ``::1``
      - Bare IPv6 / bare IPv4: returned as-is (already valid)
    """
    raw = raw.strip()

    # Bracketed IPv6: [::1] or [::1]:port
    if raw.startswith('['):
        bracket_end = raw.find(']')
        if bracket_end != -1:
            return raw[1:bracket_end]
        return raw[1:]  # malformed, best-effort

    # Exactly one colon → IPv4:port (IPv6 always has ≥2 colons)
    if raw.count(':') == 1:
        return raw.rsplit(':', 1)[0]

    return raw


def _get_client_ip(request: Request) -> str:
    """
    Extract the real client IP from behind trusted reverse proxies.

    Each trusted proxy **appends** one entry to ``X-Forwarded-For``.
    A malicious client can prepend arbitrary values, so we count from
    the **right** by ``TRUSTED_PROXY_DEPTH`` positions — the leftmost
    entry added by a trusted proxy is the real client IP.

    ::

        ┌─────────────────────────────────────────────────────────┐
        │ Topology              Depth   XFF (→ = appended)        │
        │ ─────────────────────────────────────────────────────── │
        │ ALB only              1       spoofed, real→            │
        │                                        ^^^^             │
        │                                        xff[-1]          │
        │                                                         │
        │ CloudFront + ALB      2       spoofed, real→, cf-edge→  │
        │                                        ^^^^             │
        │                                        xff[-2]          │
        └─────────────────────────────────────────────────────────┘

    Falls back to ``REMOTE_ADDR`` when XFF is absent, has fewer
    entries than the expected depth, or contains an invalid IP.
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
                    'Invalid IP in X-Forwarded-For at depth -%d: %r',
                    depth,
                    raw,
                )
        else:
            logger.warning(
                'X-Forwarded-For has %d entries but TRUSTED_PROXY_DEPTH=%d; '
                'falling back to REMOTE_ADDR',
                len(parts),
                depth,
            )

    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def _user_agent(request: Request) -> str:
    return (request.META.get('HTTP_USER_AGENT') or '')[:500]


def _check_ip_allowlist(ip: str) -> bool:
    """Check if IP is in the admin allowlist. Empty list = all allowed."""
    allowlist = getattr(settings, 'ADMIN_IP_ALLOWLIST', [])
    if not allowlist:
        return True
    try:
        addr = ipaddress.ip_address(ip)
        for entry in allowlist:
            try:
                if '/' in entry:
                    if addr in ipaddress.ip_network(entry, strict=False):
                        return True
                else:
                    if addr == ipaddress.ip_address(entry):
                        return True
            except ValueError:
                continue
    except ValueError:
        return False
    return False


def _artificial_delay():
    """Add a small delay to prevent timing-based enumeration."""
    delay = getattr(settings, 'ADMIN_LOGIN_FAILURE_DELAY_SECONDS', 0.5)
    if delay > 0:
        time.sleep(delay)


def _set_admin_auth_cookies(response: Response, refresh_token: RefreshToken) -> None:
    """Set JWT cookies with potentially shorter lifetime for admin sessions."""
    access_token = refresh_token.access_token
    response.set_cookie(
        'access_token',
        str(access_token),
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        domain=settings.AUTH_COOKIE_DOMAIN or None,
        max_age=ADMIN_ACCESS_TOKEN_MINUTES * 60,
        path=settings.AUTH_COOKIE_PATH,
    )
    response.set_cookie(
        'refresh_token',
        str(refresh_token),
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        domain=settings.AUTH_COOKIE_DOMAIN or None,
        max_age=ADMIN_REFRESH_TOKEN_HOURS * 3600,
        path=settings.AUTH_COOKIE_PATH,
    )


def _audit(action: str, request: Request, user=None, **details_kwargs):
    """Best-effort audit log for admin auth events."""
    try:
        AccessAuditLog.objects.create(
            action=action,
            actor=user if user and user.is_authenticated else None,
            target_user=user if user and user.is_authenticated else None,
            business=None,
            details=details_kwargs,
            ip_address=_get_client_ip(request),
            user_agent=_user_agent(request),
            actor_type=AccessAuditLog.ActorType.USER,
        )
    except Exception:
        logger.exception("Failed to write admin auth audit log: %s", action)


# ── Serializers ──────────────────────────────────────────────────────────────

class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class AdminMFAVerifySerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    otp_code = serializers.CharField(max_length=8)


class AdminMFARecoverySerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    recovery_code = serializers.CharField(max_length=16)


# ── Step 1: Password Authentication ─────────────────────────────────────────

class AdminLoginView(APIView):
    """
    POST /api/v1/platform-admin/auth/login/

    Step 1 of admin login. Validates email+password against platform staff.
    If MFA is enrolled:  returns mfa_required=True + mfa_token for step 2.
    If MFA not enrolled (bootstrap): completes login and issues JWT.

    All error responses are generic to prevent enumeration.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'admin_auth'

    def post(self, request: Request) -> Response:
        ip = _get_client_ip(request)

        # IP allowlist check
        if not _check_ip_allowlist(ip):
            _audit('ADMIN_LOGIN_BLOCKED_IP', request, reason='ip_not_in_allowlist')
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AdminLoginSerializer(data=request.data)
        if not serializer.is_valid():
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data['email'].strip().lower()
        password = serializer.validated_data['password']

        # Rate limit check (before any DB work)
        rl = check_rate_limit(ip, email)
        if not rl.allowed:
            _audit(
                'ADMIN_LOGIN_THROTTLED' if rl.dimension == 'ip' else 'ADMIN_LOGIN_COOLDOWN',
                request,
                email=email,
                dimension=rl.dimension,
                retry_after=rl.retry_after,
            )
            resp = Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            resp['Retry-After'] = str(rl.retry_after)
            return resp

        # Authenticate (uses existing UsernameOrEmailBackend)
        user = authenticate(request=request, username=email, password=password)

        if user is None:
            # User doesn't exist OR wrong password — record failure
            record_failed_attempt(ip, email)
            _audit('ADMIN_LOGIN_FAILED', request, email=email, reason='invalid_credentials')
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.is_active:
            record_failed_attempt(ip, email)
            _audit('ADMIN_LOGIN_FAILED', request, user=user, reason='inactive_user')
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check platform staff status — same generic error
        profile = getattr(user, 'account_profile', None)
        if profile is None or not profile.is_platform_staff:
            record_failed_attempt(ip, email)
            _audit('ADMIN_LOGIN_FAILED', request, user=user, reason='not_platform_staff')
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Password is valid and user is platform staff.
        # Check MFA status.
        if profile.mfa_enabled:
            # MFA required — issue challenge token
            mfa_token = create_mfa_challenge(user.id)
            _audit('ADMIN_MFA_REQUIRED', request, user=user)
            return Response({
                'mfa_required': True,
                'mfa_token': mfa_token,
            })

        # MFA not enrolled — check bootstrap mode
        bootstrap = getattr(settings, 'MFA_BOOTSTRAP_ENABLED', False)

        # Runtime guard: even with bootstrap=true, refuse if all *other*
        # platform staff already have MFA. This prevents bootstrap from
        # staying open indefinitely after the initial enrollment window.
        if bootstrap:
            enrolled_count = AccountProfile.objects.filter(
                is_platform_staff=True, mfa_enabled=True,
            ).count()
            if enrolled_count > 0:
                # At least one admin has already enrolled MFA.
                # This user should enroll through the normal invite/reset
                # flow, not bootstrap.
                bootstrap = False
                logger.warning(
                    'MFA bootstrap auto-disabled: %d admin(s) already enrolled. '
                    'User %s must be enrolled by an existing admin. '
                    'Set MFA_BOOTSTRAP_ENABLED=false in env.',
                    enrolled_count,
                    email,
                )

        if not bootstrap:
            # MFA is required but not enrolled, and bootstrap is disabled
            _audit('ADMIN_LOGIN_FAILED', request, user=user, reason='mfa_not_enrolled')
            _artificial_delay()
            return Response(
                {'detail': 'MFA obligatorio no configurado. Contactá al administrador.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Bootstrap mode: allow login without MFA for initial enrollment
        reset_on_success(ip, email)
        refresh = RefreshToken.for_user(user)
        _audit('ADMIN_LOGIN_SUCCESS', request, user=user, mfa='bootstrap')

        response = Response({
            'status': 'ok',
            'mfa_required': False,
            'mfa_enrolled': False,
        })
        _set_admin_auth_cookies(response, refresh)
        return response


# ── Step 2: MFA OTP Verification ────────────────────────────────────────────

class AdminMFAVerifyView(APIView):
    """
    POST /api/v1/platform-admin/auth/mfa-verify/

    Step 2 of admin login. Verifies MFA challenge token + OTP code.
    On success, issues JWT cookies and completes the login.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'admin_mfa'

    def post(self, request: Request) -> Response:
        serializer = AdminMFAVerifySerializer(data=request.data)
        if not serializer.is_valid():
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mfa_token = serializer.validated_data['mfa_token']
        otp_code = serializer.validated_data['otp_code']
        ip = _get_client_ip(request)

        # Verify challenge token (single-use)
        user_id = verify_mfa_challenge(mfa_token)
        if user_id is None:
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.select_related('account_profile').get(id=user_id)
        except User.DoesNotExist:
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile = user.account_profile

        # Check OTP attempt limit
        allowed, retry_after = check_otp_attempts(user_id)
        if not allowed:
            _audit('ADMIN_MFA_FAILED', request, user=user, reason='otp_locked_out')
            resp = Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            resp['Retry-After'] = str(retry_after)
            return resp

        # Check OTP replay
        if is_otp_used(user_id, otp_code):
            record_otp_failure(user_id)
            _audit('ADMIN_MFA_FAILED', request, user=user, reason='otp_replayed')
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Decrypt secret and verify OTP
        try:
            secret = decrypt_secret(profile.mfa_secret_encrypted)
        except Exception:
            _audit('ADMIN_MFA_FAILED', request, user=user, reason='decrypt_error')
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not verify_totp(secret, otp_code):
            record_otp_failure(user_id)
            _audit('ADMIN_MFA_FAILED', request, user=user, reason='invalid_otp')
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # OTP valid — mark used, reset counters, issue JWT
        mark_otp_used(user_id, otp_code)
        reset_otp_attempts(user_id)
        reset_on_success(ip, user.email)

        refresh = RefreshToken.for_user(user)
        _audit('ADMIN_LOGIN_SUCCESS', request, user=user, mfa='totp')
        _audit('ADMIN_MFA_SUCCESS', request, user=user)

        response = Response({
            'status': 'ok',
            'mfa_required': False,
            'mfa_enrolled': True,
        })
        _set_admin_auth_cookies(response, refresh)
        return response


# ── Step 2 (alt): Recovery Code ─────────────────────────────────────────────

class AdminMFARecoveryView(APIView):
    """
    POST /api/v1/platform-admin/auth/mfa-recovery/

    Alternative step 2: use a single-use recovery code instead of OTP.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'admin_mfa'

    def post(self, request: Request) -> Response:
        serializer = AdminMFARecoverySerializer(data=request.data)
        if not serializer.is_valid():
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mfa_token = serializer.validated_data['mfa_token']
        recovery_code = serializer.validated_data['recovery_code']
        ip = _get_client_ip(request)

        user_id = verify_mfa_challenge(mfa_token)
        if user_id is None:
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.select_related('account_profile').get(id=user_id)
        except User.DoesNotExist:
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile = user.account_profile
        hashed_codes = profile.mfa_recovery_codes or []

        matched_idx = verify_recovery_code(recovery_code, hashed_codes)
        if matched_idx is None:
            record_otp_failure(user_id)
            _audit('ADMIN_MFA_FAILED', request, user=user, reason='invalid_recovery_code')
            _artificial_delay()
            return Response(
                {'detail': GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Consume the recovery code (remove from list)
        hashed_codes.pop(matched_idx)
        profile.mfa_recovery_codes = hashed_codes
        profile.save(update_fields=['mfa_recovery_codes', 'updated_at'])

        remaining = len(hashed_codes)
        reset_otp_attempts(user_id)
        reset_on_success(ip, user.email)

        refresh = RefreshToken.for_user(user)
        _audit('ADMIN_MFA_RECOVERY_USED', request, user=user, remaining_codes=remaining)
        _audit('ADMIN_LOGIN_SUCCESS', request, user=user, mfa='recovery_code')

        response = Response({
            'status': 'ok',
            'recovery_codes_remaining': remaining,
        })
        _set_admin_auth_cookies(response, refresh)
        return response


# ── MFA Enrollment ───────────────────────────────────────────────────────────

class AdminMFAEnrollView(APIView):
    """
    POST /api/v1/platform-admin/auth/mfa-enroll/

    Start TOTP enrollment. Returns secret, provisioning URI, and recovery codes.
    Requires authenticated platform staff who hasn't enrolled yet.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def post(self, request: Request) -> Response:
        profile = request.user.account_profile

        if profile.mfa_enabled:
            return Response(
                {'detail': 'MFA ya está habilitado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate TOTP secret
        secret = generate_totp_secret()
        provisioning_uri = get_provisioning_uri(secret, request.user.email)

        # Generate recovery codes
        recovery_codes = generate_recovery_codes()

        # Store encrypted secret and hashed recovery codes (not yet confirmed)
        profile.mfa_secret_encrypted = encrypt_secret(secret)
        profile.mfa_recovery_codes = [hash_recovery_code(c) for c in recovery_codes]
        profile.save(update_fields=['mfa_secret_encrypted', 'mfa_recovery_codes', 'updated_at'])

        return Response({
            'secret': secret,
            'provisioning_uri': provisioning_uri,
            'recovery_codes': recovery_codes,
            'message': 'Escaneá el QR y enviá un código OTP para confirmar.',
        })


class AdminMFAConfirmSerializer(serializers.Serializer):
    otp_code = serializers.CharField(max_length=6, min_length=6)


class AdminMFAConfirmView(APIView):
    """
    POST /api/v1/platform-admin/auth/mfa-confirm/

    Confirm TOTP enrollment by verifying a code from the user's authenticator app.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def post(self, request: Request) -> Response:
        profile = request.user.account_profile

        if profile.mfa_enabled:
            return Response(
                {'detail': 'MFA ya está habilitado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not profile.mfa_secret_encrypted:
            return Response(
                {'detail': 'Primero iniciá el enrollment de MFA.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminMFAConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp_code = serializer.validated_data['otp_code']

        try:
            secret = decrypt_secret(profile.mfa_secret_encrypted)
        except Exception:
            return Response(
                {'detail': 'Error interno al verificar MFA.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not verify_totp(secret, otp_code):
            return Response(
                {'detail': 'Código OTP incorrecto. Verificá la hora en tu dispositivo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile.mfa_enabled = True
        profile.mfa_enrolled_at = timezone.now()
        profile.save(update_fields=['mfa_enabled', 'mfa_enrolled_at', 'updated_at'])

        _audit('ADMIN_MFA_ENABLED', request, user=request.user)

        return Response({
            'status': 'ok',
            'message': 'MFA activado correctamente.',
        })


# ── MFA Disable / Reset (requires reauth) ───────────────────────────────────

class AdminMFADisableSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)


class AdminMFADisableView(APIView):
    """
    POST /api/v1/platform-admin/auth/mfa-disable/

    Disable MFA for the current user. Requires password confirmation.
    Only superadmins can do this.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def post(self, request: Request) -> Response:
        profile = request.user.account_profile

        # Only superadmins can disable their own MFA
        if profile.internal_role != 'superadmin':
            return Response(
                {'detail': 'Solo superadmins pueden desactivar MFA.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AdminMFADisableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Verify password (reauth)
        if not request.user.check_password(serializer.validated_data['password']):
            _audit('ADMIN_MFA_FAILED', request, user=request.user, reason='reauth_failed')
            return Response(
                {'detail': 'Contraseña incorrecta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile.mfa_enabled = False
        profile.mfa_secret_encrypted = None
        profile.mfa_recovery_codes = None
        profile.mfa_enrolled_at = None
        profile.save(update_fields=[
            'mfa_enabled', 'mfa_secret_encrypted', 'mfa_recovery_codes',
            'mfa_enrolled_at', 'updated_at',
        ])

        _audit('ADMIN_MFA_DISABLED', request, user=request.user)

        return Response({
            'status': 'ok',
            'message': 'MFA desactivado. Recordá re-habilitarlo lo antes posible.',
        })


# ── Admin Logout ─────────────────────────────────────────────────────────────

class AdminLogoutView(APIView):
    """
    POST /api/v1/platform-admin/auth/logout/

    Clears admin auth cookies.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request) -> Response:
        response = Response({'status': 'logged_out'})
        for cookie in ('access_token', 'refresh_token'):
            response.delete_cookie(
                cookie,
                domain=settings.AUTH_COOKIE_DOMAIN or None,
                path=settings.AUTH_COOKIE_PATH,
            )
        return response

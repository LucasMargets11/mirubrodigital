from typing import Optional

from django.contrib.auth.models import AnonymousUser
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.exceptions import InvalidToken, TokenBackendError, TokenError

from django.conf import settings


class CookieJWTAuthentication(JWTAuthentication):
  """Allow JWT authentication via Authorization header or httpOnly cookies."""

  def authenticate(self, request):  # type: ignore[override]
    header = self.get_header(request)
    if header is not None:
      raw_token = self.get_raw_token(header)
    else:
      raw_token = request.COOKIES.get('access_token')

    if raw_token is None:
      return None

    validated_token = self.get_validated_token(raw_token)
    return self.get_user(validated_token), validated_token


# ── Employee operative authentication ─────────────────────────────────────────


class EmployeeIdentity:
    """
    Lightweight identity object for an authenticated EmployeeProfile.

    Returned as the "user" by EmployeeTokenAuthentication so that DRF's
    request.user is populated and request.user.is_authenticated returns True,
    without creating a fake django.contrib.auth.User.

    Views that need the employee object should read request.employee directly.
    """
    is_authenticated = True
    is_anonymous     = False
    is_staff         = False
    is_superuser     = False

    def __init__(self, employee, business):
        self.employee = employee
        self.business = business
        # pk / id used by some DRF internals
        self.pk = None

    def __str__(self) -> str:
        return f"EmployeeIdentity({self.employee.employee_code}@{self.business.id})"


class EmployeeTokenAuthentication(BaseAuthentication):
    """
    Authenticates requests using a short-lived employee JWT.

    The token is issued by EmployeeLoginView and passed via the
    ``X-Employee-Token: <token>`` header.  It contains:
        actor_type    = 'employee'
        employee_id   = '<uuid>'
        business_id   = <int>

    On success:
        request.user     = EmployeeIdentity instance
        request.employee = EmployeeProfile instance
        request.business = Business instance

    Returns None (not None, None) when the header is absent so that other
    authenticators (CookieJWTAuthentication) can still run.
    """
    HEADER = 'HTTP_X_EMPLOYEE_TOKEN'

    def authenticate(self, request):
        raw_token = request.META.get(self.HEADER)
        if not raw_token:
            return None

        try:
            backend = TokenBackend(
                algorithm=settings.SIMPLE_JWT.get('ALGORITHM', 'HS256'),
                signing_key=settings.SIMPLE_JWT.get('SIGNING_KEY', settings.SECRET_KEY),
            )
            payload = backend.decode(raw_token, verify=True)
        except (TokenError, TokenBackendError) as e:
            raise exceptions.AuthenticationFailed(f'Employee token invalid: {e}')

        if payload.get('actor_type') != 'employee':
            raise exceptions.AuthenticationFailed('Not an employee token.')

        employee_id = payload.get('employee_id')
        business_id = payload.get('business_id')

        if not employee_id or not business_id:
            raise exceptions.AuthenticationFailed('Malformed employee token.')

        try:
            from apps.accounts.models import EmployeeProfile
            employee = EmployeeProfile.objects.select_related('business').get(
                id=employee_id,
                business_id=business_id,
                status=EmployeeProfile.Status.ACTIVE,
            )
        except EmployeeProfile.DoesNotExist:
            raise exceptions.AuthenticationFailed('Employee not found or not active.')

        identity = EmployeeIdentity(employee=employee, business=employee.business)
        # Attach to request for convenience
        request.employee = employee
        request.business = employee.business
        return (identity, payload)

    def authenticate_header(self, request) -> str:
        return 'X-Employee-Token'


# ── Employee-aware rate throttle ──────────────────────────────────────────────


class EmployeeScopedThrottle(ScopedRateThrottle):
    """
    ScopedRateThrottle adapted for EmployeeIdentity requests.

    For requests authenticated via EmployeeTokenAuthentication, uses the
    employee UUID as the rate-limit identifier (per-employee, not per-IP).
    For unauthenticated requests (e.g. the login endpoint), falls back to
    the client IP address — same behaviour as the base class.
    """

    def get_cache_key(self, request, view):
        scope = getattr(view, self.scope_attr, None)
        if not scope:
            return None

        employee = getattr(request, 'employee', None)
        if employee is not None:
            ident = str(employee.pk)
        else:
            # Anonymous or regular User — use IP
            ident = self.get_ident(request)

        return self.cache_format % {'scope': scope, 'ident': ident}

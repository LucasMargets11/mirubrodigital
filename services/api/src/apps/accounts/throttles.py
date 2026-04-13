"""
DRF throttle classes for public authentication endpoints.

Each sensitive auth endpoint gets its own throttle class (not a shared scope)
so rates can be tuned independently without risk of cross-contamination.

All classes inherit from FailOpenAnonThrottle, which wraps AnonRateThrottle
with a try/except on allow_request() so that a Redis outage degrades to
fail-open instead of returning 500.

Rates are read from REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] so they can
be tuned via Django settings without touching code.
"""
import logging

from django.core.exceptions import ImproperlyConfigured
from rest_framework.throttling import AnonRateThrottle

logger = logging.getLogger(__name__)


class FailOpenAnonThrottle(AnonRateThrottle):
    """AnonRateThrottle that degrades to allow-all when the cache backend is down.

    DRF's SimpleRateThrottle.allow_request() calls cache.get/set without
    exception handling.  If Redis is unavailable, the unhandled exception
    propagates through check_throttles() and Django returns 500.

    This wrapper catches any exception from the parent, logs it with the
    keyword RATE_LIMIT_REDIS_UNAVAILABLE (for CloudWatch alarming), and
    returns True (allow the request).
    """

    def get_rate(self):
        """Read throttle rate from live settings instead of the stale class-level snapshot.

        DRF's SimpleRateThrottle stores DEFAULT_THROTTLE_RATES as a class
        attribute at import time.  If settings change at runtime (or during
        tests via override_settings), the class attribute is never refreshed.
        Reading from api_settings on every call ensures we always use the
        current configuration.
        """
        from rest_framework.settings import api_settings

        rates = api_settings.DEFAULT_THROTTLE_RATES or {}
        if self.scope not in rates:
            raise ImproperlyConfigured(
                f"No default throttle rate set for '{self.scope}' scope"
            )
        return rates[self.scope]

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.error(
                'RATE_LIMIT_REDIS_UNAVAILABLE throttle=%s', self.scope,
            )
            return True


class LoginThrottle(FailOpenAnonThrottle):
    """IP-based throttle for POST /api/v1/auth/login/.

    Default: 15/minute — generous enough for normal use, but caps automated
    attacks before they hit the expensive password-hashing path.
    """
    scope = 'auth_login'


class RegisterThrottle(FailOpenAnonThrottle):
    """IP-based throttle for POST /api/v1/auth/register/.

    Default: 5/minute — legitimate users register once; higher rates signal
    automated account creation.
    """
    scope = 'auth_register'


class ForgotPasswordThrottle(FailOpenAnonThrottle):
    """IP-based throttle for POST /api/v1/auth/forgot-password/.

    Default: 5/minute — caps email sending and token generation.
    """
    scope = 'auth_forgot_password'


class ResetPasswordThrottle(FailOpenAnonThrottle):
    """IP-based throttle for POST /api/v1/auth/reset-password/.

    Default: 5/minute — limits token-guessing attempts.
    """
    scope = 'auth_reset_password'


class VerifyEmailThrottle(FailOpenAnonThrottle):
    """IP-based throttle for POST /api/v1/auth/verify-email/.

    Default: 5/minute — limits token-guessing attempts.
    """
    scope = 'auth_verify_email'


class RefreshTokenThrottle(FailOpenAnonThrottle):
    """IP-based throttle for POST /api/v1/auth/refresh/.

    Default: 30/minute — needs more headroom because legitimate SPAs
    refresh transparently on every page load.
    """
    scope = 'auth_refresh'


class GoogleAuthThrottle(FailOpenAnonThrottle):
    """IP-based throttle for POST /api/v1/auth/google/.

    Default: 10/minute — generous for normal use, caps token-replay attacks.
    """
    scope = 'auth_google'

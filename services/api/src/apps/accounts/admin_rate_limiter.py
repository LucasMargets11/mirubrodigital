"""
Cache-based rate limiter for platform admin authentication.

Uses Django's cache framework (Redis in production) to track login attempts
across three independent dimensions:
  - IP address
  - Normalized email
  - IP + email combination

Implements progressive cooldowns (not permanent lockout) to prevent:
  - Brute-force attacks
  - Credential stuffing
  - Denial-of-service via account lockout

All thresholds and windows are configurable via Django settings.
"""
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ── Settings with defaults ───────────────────────────────────────────────────
# All are overridable via Django settings / environment variables.

def _s(name: str, default):
    return getattr(settings, name, default)


def _get_limits():
    """Return current rate-limit settings (read each call for test overrideability)."""
    return {
        # IP + email combination
        'ip_email_max': _s('ADMIN_LOGIN_IP_EMAIL_MAX_ATTEMPTS', 5),
        'ip_email_window': _s('ADMIN_LOGIN_IP_EMAIL_WINDOW_SECONDS', 15 * 60),
        'ip_email_cooldown': _s('ADMIN_LOGIN_IP_EMAIL_COOLDOWN_SECONDS', 15 * 60),

        # Email global (across all IPs)
        'email_max': _s('ADMIN_LOGIN_EMAIL_MAX_ATTEMPTS', 10),
        'email_window': _s('ADMIN_LOGIN_EMAIL_WINDOW_SECONDS', 30 * 60),
        'email_cooldown': _s('ADMIN_LOGIN_EMAIL_COOLDOWN_SECONDS', 30 * 60),

        # IP global (across all emails)
        'ip_max': _s('ADMIN_LOGIN_IP_MAX_ATTEMPTS', 20),
        'ip_window': _s('ADMIN_LOGIN_IP_WINDOW_SECONDS', 10 * 60),
        'ip_cooldown': _s('ADMIN_LOGIN_IP_COOLDOWN_SECONDS', 10 * 60),
    }


# ── Key helpers ──────────────────────────────────────────────────────────────

_PREFIX = 'admin_rl'


def _normalize_email(email: str) -> str:
    """Lowercase + hash email for cache key safety."""
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _key_ip(ip: str) -> str:
    return f'{_PREFIX}:ip:{ip}'


def _key_email(email_hash: str) -> str:
    return f'{_PREFIX}:em:{email_hash}'


def _key_ip_email(ip: str, email_hash: str) -> str:
    return f'{_PREFIX}:ie:{ip}:{email_hash}'


def _cooldown_key(base_key: str) -> str:
    return f'{base_key}:cd'


# ── Counter operations ───────────────────────────────────────────────────────

def _increment(key: str, window: int) -> int:
    """Increment counter for key. Returns new count."""
    try:
        new_val = cache.incr(key)
    except ValueError:
        # Key doesn't exist — create with TTL
        cache.set(key, 1, timeout=window)
        new_val = 1
    return new_val


def _get_count(key: str) -> int:
    return cache.get(key, 0)


def _set_cooldown(key: str, cooldown_seconds: int) -> None:
    """Set a cooldown marker with expiration."""
    cd_key = _cooldown_key(key)
    cache.set(cd_key, int(time.time()) + cooldown_seconds, timeout=cooldown_seconds)


def _get_cooldown_remaining(key: str) -> int:
    """Returns seconds remaining on cooldown, or 0 if not under cooldown."""
    cd_key = _cooldown_key(key)
    expires_at = cache.get(cd_key)
    if expires_at is None:
        return 0
    remaining = int(expires_at) - int(time.time())
    return max(0, remaining)


def _reset_key(key: str) -> None:
    """Remove counter and cooldown for a key."""
    cache.delete(key)
    cache.delete(_cooldown_key(key))


# ── Public API ───────────────────────────────────────────────────────────────

@dataclass
class RateLimitResult:
    allowed: bool
    reason: str = ''
    retry_after: int = 0  # seconds
    dimension: str = ''   # 'ip', 'email', 'ip_email'


def check_rate_limit(ip: str, email: str) -> RateLimitResult:
    """
    Check whether a login attempt from ip/email is allowed.
    Does NOT increment counters — call record_failed_attempt() on failure.
    """
    limits = _get_limits()
    email_hash = _normalize_email(email)

    # Check cooldowns first (cheapest check)
    for key, dim, label in [
        (_key_ip_email(ip, email_hash), 'ip_email', 'IP+cuenta'),
        (_key_email(email_hash), 'email', 'cuenta'),
        (_key_ip(ip), 'ip', 'IP'),
    ]:
        remaining = _get_cooldown_remaining(key)
        if remaining > 0:
            return RateLimitResult(
                allowed=False,
                reason=f'Cooldown activo ({label})',
                retry_after=remaining,
                dimension=dim,
            )

    # Check counters (still within window, not yet in cooldown)
    ip_email_key = _key_ip_email(ip, email_hash)
    if _get_count(ip_email_key) >= limits['ip_email_max']:
        return RateLimitResult(
            allowed=False,
            reason='Demasiados intentos para esta IP+cuenta',
            retry_after=limits['ip_email_cooldown'],
            dimension='ip_email',
        )

    email_key = _key_email(email_hash)
    if _get_count(email_key) >= limits['email_max']:
        return RateLimitResult(
            allowed=False,
            reason='Demasiados intentos para esta cuenta',
            retry_after=limits['email_cooldown'],
            dimension='email',
        )

    ip_key = _key_ip(ip)
    if _get_count(ip_key) >= limits['ip_max']:
        return RateLimitResult(
            allowed=False,
            reason='Demasiados intentos desde esta IP',
            retry_after=limits['ip_cooldown'],
            dimension='ip',
        )

    return RateLimitResult(allowed=True)


def record_failed_attempt(ip: str, email: str) -> Optional[RateLimitResult]:
    """
    Record a failed login attempt. Increments all three counters.
    If any threshold is breached, sets a cooldown and returns the result.
    Returns None if no threshold was breached.
    """
    limits = _get_limits()
    email_hash = _normalize_email(email)

    # Increment all dimensions
    ie_count = _increment(_key_ip_email(ip, email_hash), limits['ip_email_window'])
    em_count = _increment(_key_email(email_hash), limits['email_window'])
    ip_count = _increment(_key_ip(ip), limits['ip_window'])

    # Check thresholds and set cooldowns
    if ie_count >= limits['ip_email_max']:
        _set_cooldown(_key_ip_email(ip, email_hash), limits['ip_email_cooldown'])
        return RateLimitResult(
            allowed=False,
            reason='Límite IP+cuenta alcanzado',
            retry_after=limits['ip_email_cooldown'],
            dimension='ip_email',
        )

    if em_count >= limits['email_max']:
        _set_cooldown(_key_email(email_hash), limits['email_cooldown'])
        return RateLimitResult(
            allowed=False,
            reason='Límite por cuenta alcanzado',
            retry_after=limits['email_cooldown'],
            dimension='email',
        )

    if ip_count >= limits['ip_max']:
        _set_cooldown(_key_ip(ip), limits['ip_cooldown'])
        return RateLimitResult(
            allowed=False,
            reason='Límite por IP alcanzado',
            retry_after=limits['ip_cooldown'],
            dimension='ip',
        )

    return None


def reset_on_success(ip: str, email: str) -> None:
    """Reset IP+email and email counters (not global IP) on successful login."""
    email_hash = _normalize_email(email)
    _reset_key(_key_ip_email(ip, email_hash))
    _reset_key(_key_email(email_hash))
    # Note: global IP counter is NOT reset on success — an attacker rotating
    # through valid accounts should not reset the IP counter.

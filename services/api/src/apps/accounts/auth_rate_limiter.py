"""
Cache-based 3-dimensional rate limiter for owner/public login.

Mirrors the architecture of admin_rate_limiter.py but with higher thresholds
suitable for a public-facing login endpoint that serves normal SaaS users.

Dimensions:
  1. IP + identifier   — stops a single IP targeting a single account
  2. Identifier (email) — stops credential stuffing across many IPs
  3. IP                 — stops a single IP spraying across many accounts

All thresholds, windows, and cooldowns are read from Django settings at call
time so they can be overridden via environment variables or in tests.

Key design decisions:
  - Progressive cooldowns, NOT permanent lockout (prevents DoS via lockout)
  - IP counter is NOT reset on success (prevents counter-reset abuse)
  - IP+identifier and identifier counters ARE reset on success
  - All cache keys have TTLs — no risk of unbounded Redis growth
  - Cooldown is stored as a separate key with timestamp for accurate Retry-After
"""
import hashlib
import logging
import time
import unicodedata
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ── Settings with defaults ───────────────────────────────────────────────────

def _s(name: str, default):
    return getattr(settings, name, default)


def _get_limits():
    """Return current rate-limit settings (read each call for test overrideability)."""
    return {
        # IP + identifier combination
        'ip_ident_max': _s('AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS', 10),
        'ip_ident_window': _s('AUTH_LOGIN_IP_IDENT_WINDOW_SECONDS', 15 * 60),
        'ip_ident_cooldown': _s('AUTH_LOGIN_IP_IDENT_COOLDOWN_SECONDS', 15 * 60),

        # Identifier global (across all IPs)
        'ident_max': _s('AUTH_LOGIN_IDENT_MAX_ATTEMPTS', 20),
        'ident_window': _s('AUTH_LOGIN_IDENT_WINDOW_SECONDS', 30 * 60),
        'ident_cooldown': _s('AUTH_LOGIN_IDENT_COOLDOWN_SECONDS', 30 * 60),

        # IP global (across all identifiers)
        'ip_max': _s('AUTH_LOGIN_IP_MAX_ATTEMPTS', 50),
        'ip_window': _s('AUTH_LOGIN_IP_WINDOW_SECONDS', 10 * 60),
        'ip_cooldown': _s('AUTH_LOGIN_IP_COOLDOWN_SECONDS', 10 * 60),
    }


# ── Key helpers ──────────────────────────────────────────────────────────────

_PREFIX = 'auth_rl'


def _hash_identifier(identifier: str) -> str:
    """NFKC-normalize + lowercase + hash identifier for cache key safety.

    NFKC normalization ensures that equivalent Unicode representations
    (e.g. NFC vs NFD forms of 'café') hash to the same key, preventing
    bypass via Unicode variation.
    """
    normalized = unicodedata.normalize('NFKC', identifier.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _key_ip(ip: str) -> str:
    return f'{_PREFIX}:ip:{ip}'


def _key_ident(ident_hash: str) -> str:
    return f'{_PREFIX}:id:{ident_hash}'


def _key_ip_ident(ip: str, ident_hash: str) -> str:
    return f'{_PREFIX}:ii:{ip}:{ident_hash}'


def _cooldown_key(base_key: str) -> str:
    return f'{base_key}:cd'


# ── Counter operations ───────────────────────────────────────────────────────

def _increment(key: str, window: int) -> int:
    """Increment counter for key. Returns new count. Fail-open on error."""
    try:
        new_val = cache.incr(key)
    except ValueError:
        try:
            cache.set(key, 1, timeout=window)
        except Exception:
            logger.error('RATE_LIMIT_REDIS_UNAVAILABLE increment/set key=%s', key)
            return 0
        new_val = 1
    except Exception:
        logger.error('RATE_LIMIT_REDIS_UNAVAILABLE increment key=%s', key)
        return 0
    return new_val


def _get_count(key: str) -> int:
    try:
        return cache.get(key, 0)
    except Exception:
        logger.error('RATE_LIMIT_REDIS_UNAVAILABLE get key=%s', key)
        return 0


def _set_cooldown(key: str, cooldown_seconds: int) -> None:
    """Set a cooldown marker with expiration."""
    cd_key = _cooldown_key(key)
    try:
        cache.set(cd_key, int(time.time()) + cooldown_seconds, timeout=cooldown_seconds)
    except Exception:
        logger.error('RATE_LIMIT_REDIS_UNAVAILABLE set_cooldown key=%s', cd_key)


def _get_cooldown_remaining(key: str) -> int:
    """Returns seconds remaining on cooldown, or 0 if not under cooldown."""
    cd_key = _cooldown_key(key)
    try:
        expires_at = cache.get(cd_key)
    except Exception:
        logger.error('RATE_LIMIT_REDIS_UNAVAILABLE get_cooldown key=%s', cd_key)
        return 0
    if expires_at is None:
        return 0
    remaining = int(expires_at) - int(time.time())
    return max(0, remaining)


def _reset_key(key: str) -> None:
    """Remove counter and cooldown for a key."""
    try:
        cache.delete(key)
        cache.delete(_cooldown_key(key))
    except Exception:
        logger.error('RATE_LIMIT_REDIS_UNAVAILABLE reset key=%s', key)


# ── Public API ───────────────────────────────────────────────────────────────

@dataclass
class RateLimitResult:
    allowed: bool
    reason: str = ''
    retry_after: int = 0   # seconds
    dimension: str = ''     # 'ip', 'ident', 'ip_ident'


def check_rate_limit(ip: str, identifier: str) -> RateLimitResult:
    """
    Check whether a login attempt from ip/identifier is allowed.
    Does NOT increment counters — call record_failed_attempt() on failure.
    """
    limits = _get_limits()
    ident_hash = _hash_identifier(identifier)

    # Check cooldowns first (cheapest check)
    for key, dim in [
        (_key_ip_ident(ip, ident_hash), 'ip_ident'),
        (_key_ident(ident_hash), 'ident'),
        (_key_ip(ip), 'ip'),
    ]:
        remaining = _get_cooldown_remaining(key)
        if remaining > 0:
            return RateLimitResult(
                allowed=False,
                reason='Demasiados intentos. Intenta de nuevo más tarde.',
                retry_after=remaining,
                dimension=dim,
            )

    # Check counters
    ip_ident_key = _key_ip_ident(ip, ident_hash)
    if _get_count(ip_ident_key) >= limits['ip_ident_max']:
        return RateLimitResult(
            allowed=False,
            reason='Demasiados intentos. Intenta de nuevo más tarde.',
            retry_after=limits['ip_ident_cooldown'],
            dimension='ip_ident',
        )

    ident_key = _key_ident(ident_hash)
    if _get_count(ident_key) >= limits['ident_max']:
        return RateLimitResult(
            allowed=False,
            reason='Demasiados intentos. Intenta de nuevo más tarde.',
            retry_after=limits['ident_cooldown'],
            dimension='ident',
        )

    ip_key = _key_ip(ip)
    if _get_count(ip_key) >= limits['ip_max']:
        return RateLimitResult(
            allowed=False,
            reason='Demasiados intentos. Intenta de nuevo más tarde.',
            retry_after=limits['ip_cooldown'],
            dimension='ip',
        )

    return RateLimitResult(allowed=True)


def record_failed_attempt(ip: str, identifier: str) -> Optional[RateLimitResult]:
    """
    Record a failed login attempt. Increments all three counters.
    If any threshold is breached, sets a cooldown and returns the result.
    Returns None if no threshold was breached yet.
    """
    limits = _get_limits()
    ident_hash = _hash_identifier(identifier)

    # Increment all dimensions
    ii_count = _increment(_key_ip_ident(ip, ident_hash), limits['ip_ident_window'])
    id_count = _increment(_key_ident(ident_hash), limits['ident_window'])
    ip_count = _increment(_key_ip(ip), limits['ip_window'])

    logger.info(
        '[auth_rate_limiter] Failed attempt ip=%s ident=%s counts: ii=%d id=%d ip=%d',
        ip, ident_hash, ii_count, id_count, ip_count,
    )

    # Check thresholds and set cooldowns (most specific first)
    if ii_count >= limits['ip_ident_max']:
        _set_cooldown(_key_ip_ident(ip, ident_hash), limits['ip_ident_cooldown'])
        return RateLimitResult(
            allowed=False,
            reason='Demasiados intentos. Intenta de nuevo más tarde.',
            retry_after=limits['ip_ident_cooldown'],
            dimension='ip_ident',
        )

    if id_count >= limits['ident_max']:
        _set_cooldown(_key_ident(ident_hash), limits['ident_cooldown'])
        return RateLimitResult(
            allowed=False,
            reason='Demasiados intentos. Intenta de nuevo más tarde.',
            retry_after=limits['ident_cooldown'],
            dimension='ident',
        )

    if ip_count >= limits['ip_max']:
        _set_cooldown(_key_ip(ip), limits['ip_cooldown'])
        return RateLimitResult(
            allowed=False,
            reason='Demasiados intentos. Intenta de nuevo más tarde.',
            retry_after=limits['ip_cooldown'],
            dimension='ip',
        )

    return None


def reset_on_success(ip: str, identifier: str) -> None:
    """
    Reset IP+identifier and identifier counters on successful login.

    The global IP counter is intentionally NOT reset — an attacker rotating
    through valid accounts should not be able to reset the per-IP counter.
    """
    ident_hash = _hash_identifier(identifier)
    _reset_key(_key_ip_ident(ip, ident_hash))
    _reset_key(_key_ident(ident_hash))

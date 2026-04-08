# Code Citations

## License: LGPL-2.1
https://github.com/mnesarco/fcapi/blob/8434ea5371a926e1eb87acb5a837ab7d40afe749/fpo.py

```
All 6 files are clean and complete. Here's the final PR-ready output:

---

## 1. Árbol de archivos afectados

```
services/api/src/
├── config/
│   └── settings.py                          # DEBUG=False, NUM_PROXIES, throttle rates, 3D limits
├── apps/accounts/
│   ├── throttles.py                         # 6 DRF AnonRateThrottle subclasses
│   ├── auth_rate_limiter.py                 # 3D rate limiter (IP×ident, ident, IP)
│   ├── views.py                             # _get_client_ip hardened, anti-enum register, throttle wiring
│   └── tests/
│       └── test_auth_phase1_security.py     # 25+ tests: throttle, anti-enum, 3D, XFF, Redis fail-open
infra/terraform/
└── waf.tf                                   # WAF rule for /api/v1/auth/ (100/5min per IP)
```

## 2. Código completo de cada archivo

### 2.1 `services/api/src/apps/accounts/throttles.py`

```python
"""
DRF throttle classes for public authentication endpoints.

Each sensitive auth endpoint gets its own throttle class (not a shared scope)
so rates can be tuned independently without risk of cross-contamination.

All classes inherit from AnonRateThrottle, which keys on the client IP
extracted from REMOTE_ADDR / X-Forwarded-For.  This provides a fast first
layer of defense; the deeper 3D rate limiter (auth_rate_limiter.py) adds
per-identifier and per-combo protection inside the view logic.

Rates are read from REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] so they can
be tuned via Django settings without touching code.
"""
from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/login/.

    Default: 15/minute — generous enough for normal use, but caps automated
    attacks before they hit the expensive password-hashing path.
    """
    scope = 'auth_login'


class RegisterThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/register/.

    Default: 5/minute — legitimate users register once; higher rates signal
    automated account creation.
    """
    scope = 'auth_register'


class ForgotPasswordThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/forgot-password/.

    Default: 5/minute — caps email sending and token generation.
    """
    scope = 'auth_forgot_password'


class ResetPasswordThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/reset-password/.

    Default: 5/minute — limits token-guessing attempts.
    """
    scope = 'auth_reset_password'


class VerifyEmailThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/verify-email/.

    Default: 5/minute — limits token-guessing attempts.
    """
    scope = 'auth_verify_email'


class RefreshTokenThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/refresh/.

    Default: 30/minute — needs more headroom because legitimate SPAs
    refresh transparently on every page load.
    """
    scope = 'auth_refresh'
```

**Key points:**
- Each scope maps to a `DEFAULT_THROTTLE_RATES` key in settings
- `AnonRateThrottle.get_ident()` uses `NUM_PROXIES` from REST_FRAMEWORK settings to select the correct XFF entry
- Classes are applied per-view via `throttle_classes = [...]` — not globally

---

### 2.2 `services/api/src/apps/accounts/auth_rate_limiter.py`

```python
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
  - FAIL-OPEN: all cache operations are wrapped in try/except; if Redis is
    down, login continues and errors are logged with keyword
    RATE_LIMIT_REDIS_UNAVAILABLE for CloudWatch alarming.
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
    reason: str
```


## License: LGPL-2.1
https://github.com/mnesarco/fcapi/blob/8434ea5371a926e1eb87acb5a837ab7d40afe749/fpo.py

```
All 6 files are clean and complete. Here's the final PR-ready output:

---

## 1. Árbol de archivos afectados

```
services/api/src/
├── config/
│   └── settings.py                          # DEBUG=False, NUM_PROXIES, throttle rates, 3D limits
├── apps/accounts/
│   ├── throttles.py                         # 6 DRF AnonRateThrottle subclasses
│   ├── auth_rate_limiter.py                 # 3D rate limiter (IP×ident, ident, IP)
│   ├── views.py                             # _get_client_ip hardened, anti-enum register, throttle wiring
│   └── tests/
│       └── test_auth_phase1_security.py     # 25+ tests: throttle, anti-enum, 3D, XFF, Redis fail-open
infra/terraform/
└── waf.tf                                   # WAF rule for /api/v1/auth/ (100/5min per IP)
```

## 2. Código completo de cada archivo

### 2.1 `services/api/src/apps/accounts/throttles.py`

```python
"""
DRF throttle classes for public authentication endpoints.

Each sensitive auth endpoint gets its own throttle class (not a shared scope)
so rates can be tuned independently without risk of cross-contamination.

All classes inherit from AnonRateThrottle, which keys on the client IP
extracted from REMOTE_ADDR / X-Forwarded-For.  This provides a fast first
layer of defense; the deeper 3D rate limiter (auth_rate_limiter.py) adds
per-identifier and per-combo protection inside the view logic.

Rates are read from REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] so they can
be tuned via Django settings without touching code.
"""
from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/login/.

    Default: 15/minute — generous enough for normal use, but caps automated
    attacks before they hit the expensive password-hashing path.
    """
    scope = 'auth_login'


class RegisterThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/register/.

    Default: 5/minute — legitimate users register once; higher rates signal
    automated account creation.
    """
    scope = 'auth_register'


class ForgotPasswordThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/forgot-password/.

    Default: 5/minute — caps email sending and token generation.
    """
    scope = 'auth_forgot_password'


class ResetPasswordThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/reset-password/.

    Default: 5/minute — limits token-guessing attempts.
    """
    scope = 'auth_reset_password'


class VerifyEmailThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/verify-email/.

    Default: 5/minute — limits token-guessing attempts.
    """
    scope = 'auth_verify_email'


class RefreshTokenThrottle(AnonRateThrottle):
    """IP-based throttle for POST /api/v1/auth/refresh/.

    Default: 30/minute — needs more headroom because legitimate SPAs
    refresh transparently on every page load.
    """
    scope = 'auth_refresh'
```

**Key points:**
- Each scope maps to a `DEFAULT_THROTTLE_RATES` key in settings
- `AnonRateThrottle.get_ident()` uses `NUM_PROXIES` from REST_FRAMEWORK settings to select the correct XFF entry
- Classes are applied per-view via `throttle_classes = [...]` — not globally

---

### 2.2 `services/api/src/apps/accounts/auth_rate_limiter.py`

```python
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
  - FAIL-OPEN: all cache operations are wrapped in try/except; if Redis is
    down, login continues and errors are logged with keyword
    RATE_LIMIT_REDIS_UNAVAILABLE for CloudWatch alarming.
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
    reason: str
```


"""
TOTP-based MFA for platform admin users.

Implements:
  - TOTP secret generation and encrypted storage
  - QR code provisioning URI
  - OTP verification with drift tolerance
  - Single-use recovery codes (hashed)
  - Strict OTP attempt limiting
  - Bootstrap mode for first superadmin enrollment

All secrets are encrypted at rest using Fernet (AES-128-CBC).
"""
import hashlib
import hmac
import logging
import secrets
from typing import Optional

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ── Encryption helpers ───────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    """Get Fernet instance from settings. Key must be 32 url-safe base64 bytes."""
    key = getattr(settings, 'MFA_ENCRYPTION_KEY', None)
    if not key:
        raise RuntimeError(
            'MFA_ENCRYPTION_KEY is not set. Generate one with: '
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a TOTP secret for database storage."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a TOTP secret from database storage."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt TOTP secret — key mismatch or corruption")
        raise


# ── TOTP operations ──────────────────────────────────────────────────────────

ISSUER_NAME = 'MiRubro Admin'
OTP_DIGITS = 6
OTP_INTERVAL = 30  # seconds
OTP_VALID_WINDOW = 1  # ±1 period tolerance for clock drift


def generate_totp_secret() -> str:
    """Generate a new TOTP secret (plaintext, 32-char base32)."""
    return pyotp.random_base32(length=32)


def get_provisioning_uri(secret: str, email: str) -> str:
    """Generate otpauth:// URI for QR code scanning."""
    totp = pyotp.TOTP(secret, digits=OTP_DIGITS, interval=OTP_INTERVAL)
    return totp.provisioning_uri(name=email, issuer_name=ISSUER_NAME)


def verify_totp(secret: str, otp_code: str) -> bool:
    """
    Verify an OTP code against the secret.
    Uses time-based window to tolerate minor clock drift.
    """
    if not otp_code or not otp_code.isdigit() or len(otp_code) != OTP_DIGITS:
        return False
    totp = pyotp.TOTP(secret, digits=OTP_DIGITS, interval=OTP_INTERVAL)
    return totp.verify(otp_code, valid_window=OTP_VALID_WINDOW)


# ── OTP anti-replay ─────────────────────────────────────────────────────────

def _otp_used_key(user_id: int, otp_code: str) -> str:
    """Cache key to prevent OTP replay within the validity window."""
    return f'mfa_used:{user_id}:{otp_code}'


def mark_otp_used(user_id: int, otp_code: str) -> None:
    """Mark an OTP as used to prevent replay."""
    cache.set(
        _otp_used_key(user_id, otp_code),
        True,
        timeout=OTP_INTERVAL * (OTP_VALID_WINDOW + 2),
    )


def is_otp_used(user_id: int, otp_code: str) -> bool:
    """Check if this OTP was already used (replay prevention)."""
    return cache.get(_otp_used_key(user_id, otp_code)) is not None


# ── OTP attempt limiting ────────────────────────────────────────────────────

_OTP_ATTEMPT_PREFIX = 'mfa_att'


def _otp_attempt_key(user_id: int) -> str:
    return f'{_OTP_ATTEMPT_PREFIX}:{user_id}'


def get_otp_max_attempts() -> int:
    return getattr(settings, 'MFA_OTP_MAX_ATTEMPTS', 5)


def get_otp_lockout_seconds() -> int:
    return getattr(settings, 'MFA_OTP_LOCKOUT_SECONDS', 15 * 60)


def check_otp_attempts(user_id: int) -> tuple[bool, int]:
    """
    Check if user has exceeded OTP attempt limit.
    Returns (allowed, retry_after_seconds).
    """
    key = _otp_attempt_key(user_id)
    count = cache.get(key, 0)
    if count >= get_otp_max_attempts():
        ttl = cache.ttl(key) if hasattr(cache, 'ttl') else get_otp_lockout_seconds()
        return False, max(ttl, 0)
    return True, 0


def record_otp_failure(user_id: int) -> None:
    """Increment OTP failure counter."""
    key = _otp_attempt_key(user_id)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=get_otp_lockout_seconds())


def reset_otp_attempts(user_id: int) -> None:
    """Reset OTP failure counter on success."""
    cache.delete(_otp_attempt_key(user_id))


# ── Recovery codes ───────────────────────────────────────────────────────────

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 8  # 8 alphanumeric characters


def generate_recovery_codes() -> list[str]:
    """Generate a set of single-use recovery codes (plaintext)."""
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        code = secrets.token_hex(RECOVERY_CODE_LENGTH // 2).upper()
        codes.append(code)
    return codes


def hash_recovery_code(code: str) -> str:
    """Hash a recovery code for storage."""
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def verify_recovery_code(code: str, hashed_codes: list[str]) -> Optional[int]:
    """
    Check if a recovery code matches any stored hash.
    Returns the index of the matching code, or None.
    Uses constant-time comparison.
    """
    code_hash = hash_recovery_code(code)
    for idx, stored_hash in enumerate(hashed_codes):
        if hmac.compare_digest(code_hash, stored_hash):
            return idx
    return None


# ── MFA challenge tokens ────────────────────────────────────────────────────
# After password auth, we issue a short-lived challenge token that the client
# must present along with the OTP to complete login. This prevents the
# client from skipping the MFA step.

_MFA_CHALLENGE_PREFIX = 'mfa_ch'
MFA_CHALLENGE_TTL = int(getattr(settings, 'MFA_CHALLENGE_TTL_SECONDS', 5 * 60))


def create_mfa_challenge(user_id: int) -> str:
    """Create a short-lived MFA challenge token after password verification."""
    token = secrets.token_urlsafe(32)
    key = f'{_MFA_CHALLENGE_PREFIX}:{token}'
    cache.set(key, user_id, timeout=MFA_CHALLENGE_TTL)
    return token


def verify_mfa_challenge(token: str) -> Optional[int]:
    """
    Verify and consume an MFA challenge token.
    Returns user_id if valid, None otherwise.
    Single-use: deleted on verification.
    """
    key = f'{_MFA_CHALLENGE_PREFIX}:{token}'
    user_id = cache.get(key)
    if user_id is not None:
        cache.delete(key)
    return user_id

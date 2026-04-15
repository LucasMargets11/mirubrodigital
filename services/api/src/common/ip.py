"""
Shared IP hashing utility.

Provides privacy-safe IP hashing for rate limiting and deduplication
without storing raw IP addresses.
"""

from __future__ import annotations

import hashlib

from django.conf import settings


def hash_ip(request) -> str:
    """
    Extract the client IP from a Django/DRF request and return a SHA-256 hash.

    Checks ``X-Forwarded-For`` first (first entry), then falls back to
    ``REMOTE_ADDR``.  Never stores the raw IP.
    Uses a salt derived from SECRET_KEY to prevent rainbow-table reversal.

    Returns:
        Hex-encoded SHA-256 hash of the IP address.
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        ip = forwarded.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
    salt = getattr(settings, 'SECRET_KEY', '')[:16]
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()

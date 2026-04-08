"""
Shared QR code generation utility.

Extracted from apps.menu.views to be reusable across menu, reviews, and
any future domain that needs QR SVG generation.
"""

from __future__ import annotations

import base64
import io

import segno
from django.core.cache import cache


def build_qr_svg(url: str, *, cache_ttl: int = 60 * 60) -> str:
    """
    Generate a QR code as a base64-encoded SVG data URI.

    Args:
        url: The URL to encode in the QR code.
        cache_ttl: Cache time-to-live in seconds (default: 1 hour).

    Returns:
        A ``data:image/svg+xml;base64,...`` string.
    """
    cache_key = f"qr-svg:{url}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    qr = segno.make(url, micro=False)
    buffer = io.BytesIO()
    qr.save(buffer, kind='svg', scale=6, border=0)
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    data_uri = f"data:image/svg+xml;base64,{encoded}"
    cache.set(cache_key, data_uri, cache_ttl)
    return data_uri

"""
Admin service for QR de Reseñas configuration.

Provides helpers to read and update Business.slug and ReviewConfig fields
from the platform admin backoffice, without touching billing, entitlements,
plan, logo, carteles, or MercadoPago.
"""
from __future__ import annotations

import re

from django.db import transaction
from django.utils import timezone

from .models import ReviewConfig

# Slug must be lowercase letters, digits and hyphens only.
_SLUG_RE = re.compile(r'^[a-z0-9-]+$')


# ── Slug validation ────────────────────────────────────────────────────────

def validate_slug(value: str, exclude_business_id: int | None = None) -> str:
    """
    Validate and return a clean slug.

    Raises ValueError with a human-readable Spanish message on any violation.
    """
    from apps.business.models import Business

    if not value:
        raise ValueError('El slug es obligatorio.')

    cleaned = value.strip()

    if cleaned != cleaned.lower():
        raise ValueError('El slug debe estar en minúsculas. No se aceptan mayúsculas.')

    cleaned = cleaned.lower()  # normalise after explicit check

    if ' ' in cleaned:
        raise ValueError('El slug no puede contener espacios.')
    if "'" in cleaned or '\'' in cleaned:
        raise ValueError('El slug no puede contener apóstrofes.')
    if not _SLUG_RE.match(cleaned):
        raise ValueError(
            'El slug sólo puede contener letras minúsculas, números y guiones (-).'
        )
    if len(cleaned) > 80:
        raise ValueError('El slug no puede superar los 80 caracteres.')

    qs = Business.objects.filter(slug=cleaned)
    if exclude_business_id is not None:
        qs = qs.exclude(pk=exclude_business_id)
    if qs.exists():
        raise ValueError(f'El slug "{cleaned}" ya está en uso por otro negocio.')

    return cleaned


# ── Snapshot ───────────────────────────────────────────────────────────────

def get_admin_qr_reviews_config_snapshot(business) -> dict:
    """Return a full read-only snapshot of business + ReviewConfig state."""
    from django.conf import settings

    base_url = (
        getattr(settings, 'PUBLIC_MENU_BASE_URL', None)
        or getattr(settings, 'FRONTEND_URL', None)
        or 'https://www.mirubro.com'
    )
    slug = business.slug or ''
    public_url = f"{base_url.rstrip('/')}/r/{slug}/" if slug else ''

    try:
        cfg = business.review_config
        review_config_exists = True
    except ReviewConfig.DoesNotExist:
        cfg = None
        review_config_exists = False

    return {
        'business_id': business.id,
        'business_name': business.name,
        'business_slug': slug,
        'public_url': public_url,
        'service_type': business.service_type or business.default_service or '',
        'review_config_exists': review_config_exists,
        'enabled': cfg.enabled if cfg else False,
        'mode': cfg.mode if cfg else 'direct',
        'redirect_threshold': cfg.redirect_threshold if cfg else 4,
        'google_place_id': cfg.google_place_id if cfg else '',
        'google_place_name': cfg.google_place_name if cfg else '',
        'google_place_formatted_address': cfg.google_place_formatted_address if cfg else '',
        'google_review_url': cfg.google_review_url if cfg else '',
        'custom_redirect_url': cfg.custom_redirect_url if cfg else '',
        'google_place_updated_at': (
            cfg.google_place_updated_at.isoformat() if cfg and cfg.google_place_updated_at else None
        ),
    }


# ── Update ─────────────────────────────────────────────────────────────────

_ALLOWED_CONFIG_FIELDS = {
    'google_place_id',
    'google_place_name',
    'google_place_formatted_address',
    'google_review_url',
    'custom_redirect_url',
}


def update_admin_qr_reviews_config(business, data: dict, actor=None) -> dict:
    """
    Apply admin PATCH payload to Business.slug and/or ReviewConfig fields.

    Only the following keys are processed; everything else is silently ignored:
      - slug
      - google_place_id
      - google_place_name
      - google_place_formatted_address
      - google_review_url
      - custom_redirect_url

    Returns the updated snapshot.
    Raises ValueError for validation failures.
    Uses transaction.atomic() to guarantee consistency.
    """
    with transaction.atomic():
        # ── Slug ──────────────────────────────────────────────────────────
        if 'slug' in data:
            new_slug = validate_slug(data['slug'], exclude_business_id=business.id)
            business.slug = new_slug
            business.save(update_fields=['slug', 'updated_at'])

        # ── ReviewConfig fields ───────────────────────────────────────────
        config_updates = {k: v for k, v in data.items() if k in _ALLOWED_CONFIG_FIELDS}
        if config_updates:
            cfg, _ = ReviewConfig.objects.get_or_create(business=business)

            place_id_changed = (
                'google_place_id' in config_updates
                and config_updates['google_place_id'] != cfg.google_place_id
            )

            for field, value in config_updates.items():
                setattr(cfg, field, value)

            # Auto-stamp google_place_updated_at when place_id changes.
            if place_id_changed and hasattr(cfg, 'google_place_updated_at'):
                cfg.google_place_updated_at = timezone.now()

            update_fields_list = list(config_updates.keys()) + ['updated_at']
            if place_id_changed and hasattr(cfg, 'google_place_updated_at'):
                update_fields_list.append('google_place_updated_at')

            cfg.save(update_fields=update_fields_list)

    return get_admin_qr_reviews_config_snapshot(business)

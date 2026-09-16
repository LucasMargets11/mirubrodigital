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

from apps.accounts.models import AccessAuditLog
from apps.business.models import Business

from .entitlements import reviews_allowed
from .models import ReviewConfig

# Slug must be lowercase letters, digits and hyphens only.
_SLUG_RE = re.compile(r'^[a-z0-9-]+$')
_PUBLISHABLE_BUSINESS_STATUSES = frozenset({'active', 'trialing', 'past_due'})


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
    'enabled',
    'google_place_id',
    'google_place_name',
    'google_place_formatted_address',
    'google_review_url',
    'custom_redirect_url',
}


def _is_qr_reviews_business(business: Business) -> bool:
    canonical = business.service_type or ''
    legacy = business.default_service or ''
    return canonical == 'qr_reviews' or legacy == 'qr_reviews'


def _requested_values(business: Business, config: ReviewConfig | None, data: dict) -> dict:
    """Return audit values using the request field names."""
    values = {}
    for field in data:
        if field == 'slug':
            values[field] = business.slug
        elif config is not None:
            values[field] = getattr(config, field)
        elif field == 'enabled':
            values[field] = False
        else:
            values[field] = ''
    return values


def update_admin_qr_reviews_config(
    business,
    data: dict,
    actor=None,
    ip_address: str | None = None,
    user_agent: str = '',
) -> dict:
    """
    Apply admin PATCH payload to Business.slug and/or ReviewConfig fields.

    Only the following keys are processed; everything else is silently ignored:
      - slug
      - enabled
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
        # The business row serializes toggles for this tenant, including when
        # no ReviewConfig row exists yet and therefore cannot itself be locked.
        try:
            locked_business = Business.objects.select_for_update().get(
                pk=business.pk,
                parent__isnull=True,
            )
        except Business.DoesNotExist as exc:
            raise ValueError('Cliente no encontrado o no es un negocio raíz.') from exc

        if not _is_qr_reviews_business(locked_business):
            raise ValueError('Este negocio no es de tipo QR de Reseñas.')

        config = (
            ReviewConfig.objects.select_for_update()
            .filter(business=locked_business)
            .first()
        )
        before = _requested_values(locked_business, config, data)

        # Activation is the only direction gated by publishability and billing.
        # These checks deliberately run before any write in this transaction.
        if data.get('enabled') is True:
            if locked_business.status not in _PUBLISHABLE_BUSINESS_STATUSES:
                raise ValueError('El negocio no está en un estado publicable.')
            if not reviews_allowed(locked_business):
                raise ValueError('El negocio no tiene acceso vigente a QR de Reseñas.')

        # ── Slug ──────────────────────────────────────────────────────────
        if 'slug' in data:
            new_slug = validate_slug(data['slug'], exclude_business_id=locked_business.id)
            locked_business.slug = new_slug
            locked_business.save(update_fields=['slug', 'updated_at'])

        # ── ReviewConfig fields ───────────────────────────────────────────
        config_updates = {k: v for k, v in data.items() if k in _ALLOWED_CONFIG_FIELDS}
        if config_updates:
            if config is None and set(config_updates) == {'enabled'} and not data['enabled']:
                cfg = None
            elif config is None:
                cfg = ReviewConfig.objects.create(
                    business=locked_business,
                    enabled=config_updates.pop('enabled', False),
                )
            else:
                cfg = config

            if cfg is not None:
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

                if update_fields_list:
                    cfg.save(update_fields=update_fields_list)

            config = cfg

        after = _requested_values(locked_business, config, data)
        AccessAuditLog.objects.create(
            action='ADMIN_QR_REVIEWS_CONFIG_UPDATED',
            actor=actor,
            actor_type=AccessAuditLog.ActorType.USER,
            business=locked_business,
            details={'changed_fields': list(data.keys())},
            entity_type='review_config',
            entity_id=str(config.pk) if config is not None else '',
            before_json=before,
            after_json=after,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        snapshot = get_admin_qr_reviews_config_snapshot(locked_business)

    return snapshot

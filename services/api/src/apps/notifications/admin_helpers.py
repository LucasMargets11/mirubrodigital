"""
notifications/admin_helpers.py — Reutilizable helper para emails internos del panel ADMIN.

Uso:
    from apps.notifications.admin_helpers import queue_admin_transactional_email

    ok = queue_admin_transactional_email(
        recipient_category="support",
        subject="Nuevo ticket de soporte",
        context={"title": "...", "message": "..."},
        related_business=business_instance,
    )

Categorías soportadas:
    support        → settings.SUPPORT_EMAIL
    billing        → settings.BILLING_EMAIL
    operations     → settings.OPERATIONS_EMAIL
    platform_admin → settings.ADMIN_EMAIL

Reglas:
  - No propaga excepciones (best-effort).
  - Devuelve True si pudo encolar; False en cualquier error.
  - Siempre usa send_async=True por defecto.
  - Pasa por queue_transactional_email; nunca usa send_mail / EmailMessage.
  - Filtra claves de metadata sensibles antes de persistir.
"""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from apps.notifications.services import queue_transactional_email

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolución de destinatarios por categoría
# ---------------------------------------------------------------------------

_CATEGORY_SETTING: dict[str, str] = {
    "support": "SUPPORT_EMAIL",
    "billing": "BILLING_EMAIL",
    "operations": "OPERATIONS_EMAIL",
    "platform_admin": "ADMIN_EMAIL",
}

# ---------------------------------------------------------------------------
# Claves de metadata que NUNCA deben guardarse
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "token",
        "password",
        "pin",
        "raw_payload",
        "x_signature",
        "authorization",
    }
)


def _resolve_recipient(category: str) -> str | None:
    """
    Devuelve la dirección de email para la categoría dada,
    o None si la categoría es inválida o la setting está vacía.
    """
    setting_name = _CATEGORY_SETTING.get(category)
    if not setting_name:
        logger.warning(
            "queue_admin_transactional_email: categoría inválida '%s'. "
            "Categorías válidas: %s",
            category,
            ", ".join(sorted(_CATEGORY_SETTING)),
        )
        return None

    email = getattr(settings, setting_name, "").strip()
    if not email:
        logger.warning(
            "queue_admin_transactional_email: la setting '%s' está vacía o no "
            "configurada para la categoría '%s'.",
            setting_name,
            category,
        )
        return None

    return email


def _build_metadata(
    recipient_category: str,
    related_business: Any,
    related_user: Any,
    extra_metadata: dict | None,
) -> dict:
    """
    Construye metadata segura, filtrando claves sensibles.
    """
    meta: dict = {"admin_category": recipient_category}

    if related_business is not None:
        meta["related_business_id"] = str(related_business.pk)

    if related_user is not None:
        meta["related_user_id"] = str(related_user.pk)

    if extra_metadata:
        for key, value in extra_metadata.items():
            if key.lower() in _SENSITIVE_KEYS:
                logger.warning(
                    "queue_admin_transactional_email: clave sensible '%s' excluida de metadata.",
                    key,
                )
                continue
            meta[key] = value

    return meta


def queue_admin_transactional_email(
    *,
    recipient_category: str,
    subject: str,
    template_key: str = "admin_generic",
    context: dict | None = None,
    related_business: Any = None,
    related_user: Any = None,
    metadata: dict | None = None,
    send_async: bool = True,
) -> bool:
    """
    Encola un email interno para el panel ADMIN de MiRubro.

    Parámetros:
        recipient_category: "support" | "billing" | "operations" | "platform_admin"
        subject:            Asunto del email.
        template_key:       Clave de template. Por defecto "admin_generic".
        context:            Contexto extra para el template.
        related_business:   Instancia de Business (opcional, para asociar al EmailDelivery).
        related_user:       Instancia de User (opcional, para asociar al EmailDelivery).
        metadata:           Metadata adicional (claves sensibles son filtradas).
        send_async:         Si True (default), usa Celery; si False, envío sincrónico.

    Retorna:
        True  → EmailDelivery creado y encolado correctamente.
        False → No se pudo encolar (categoría inválida, setting vacía, excepción).
    """
    to_email = _resolve_recipient(recipient_category)
    if to_email is None:
        return False

    safe_metadata = _build_metadata(
        recipient_category=recipient_category,
        related_business=related_business,
        related_user=related_user,
        extra_metadata=metadata,
    )

    try:
        queue_transactional_email(
            to_email=to_email,
            subject=subject,
            template_key=template_key,
            context=context,
            business=related_business,
            user=related_user,
            metadata=safe_metadata,
            send_async=send_async,
        )
        return True
    except Exception:
        logger.exception(
            "queue_admin_transactional_email: error al encolar email para categoría '%s'.",
            recipient_category,
        )
        return False

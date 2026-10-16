"""
notifications/business_notifications.py — Notificaciones internas in-app por Business (Slice 6D).

Public API:
    RECIPIENT_ROLES                         → roles que ven TODOS los kinds
    KIND_VIEW_PERMISSIONS                   → kind → permiso RBAC que lo habilita
    can_view_business_notifications(m)      → bool (membership activa + rol)
    create_business_notification(...)       → (BusinessNotification, created)
    on_commit_safely(func, description=...) → corre `func` tras el commit; nunca propaga

Reglas:
  - Una fila por (business, dedupe_key): un evento repetido (webhook
    duplicado, reintento) nunca crea otra notificación.
  - Solo se crean DESPUÉS del commit de la transacción de negocio
    (`on_commit_safely`): un fallo acá no revierte nada ni hace fallar al
    caller; queda en el log (`logger.exception`).
  - `action_url` es siempre una ruta interna del panel (`/app/...`).
  - No envía emails ni mensajes externos.
  - `recipient_id` (LEADS 04B.3) vuelve el aviso personal: solo lo ve esa
    persona (ver `views._scoped`). Sin él, es del equipo como siempre.
"""
from __future__ import annotations

import logging
from typing import Callable

from django.db import transaction

from .models import BusinessNotification

logger = logging.getLogger(__name__)

# Política de destinatarios (Slice 6D): OWNER y ADMIN del Business ven todos
# los kinds (incluidos los financieros: pagos que requieren revisión).
RECIPIENT_ROLES = frozenset({"owner", "admin"})

# CUSTOMER 07C.1: además, un kind puede habilitarse para otros roles por RBAC.
# Un miembro fuera de RECIPIENT_ROLES ve SOLO los kinds cuyo permiso tiene
# (manager → `customer_reminder_due`). Un kind que no figura acá sigue siendo
# exclusivo de owner/admin. El estado de lectura (`read_at`) sigue siendo
# compartido por el Business.
KIND_VIEW_PERMISSIONS = {
    BusinessNotification.Kind.CUSTOMER_REMINDER_DUE: "view_customer_reminder_notifications",
    # AGENT 02B: handoff del agente → quien atiende leads (manager incluido).
    BusinessNotification.Kind.AGENT_LEAD_HANDOFF: "view_leads",
    # LEADS 04B.3: aviso personal al nuevo asignado de un Lead.
    BusinessNotification.Kind.LEAD_ASSIGNED: "view_leads",
}

_INTERNAL_URL_PREFIX = "/app/"


def can_view_business_notifications(membership) -> bool:
    if membership is None:
        return False
    status = getattr(membership, "status", "active")
    return status == "active" and membership.role in RECIPIENT_ROLES


def _safe_action_url(url: str) -> str:
    """Solo rutas internas del panel; cualquier otra cosa se descarta."""
    url = (url or "").strip()
    if not url.startswith(_INTERNAL_URL_PREFIX) or "//" in url or "\\" in url:
        if url:
            logger.warning("[BusinessNotification] action_url descartada (no interna)")
        return ""
    return url[:500]


def create_business_notification(
    *,
    business_id,
    kind: str,
    dedupe_key: str,
    title: str,
    message: str = "",
    severity: str = BusinessNotification.Severity.INFO,
    action_url: str = "",
    related_object_type: str = "",
    related_object_id: str = "",
    metadata: dict | None = None,
    recipient_id=None,
) -> tuple[BusinessNotification, bool]:
    """Get-or-create idempotente por (business, dedupe_key).

    `get_or_create` ya resuelve la carrera de dos inserts concurrentes: el
    perdedor recibe IntegrityError de la constraint única y re-lee la fila.
    """
    if not dedupe_key:
        raise ValueError("dedupe_key is required")
    notification, created = BusinessNotification.objects.get_or_create(
        business_id=business_id,
        dedupe_key=dedupe_key[:128],
        defaults={
            "kind": kind,
            "severity": severity,
            "title": title[:200],
            "message": message,
            "action_url": _safe_action_url(action_url),
            "related_object_type": related_object_type[:64],
            "related_object_id": str(related_object_id)[:64],
            "metadata": metadata or {},
            "recipient_id": recipient_id,
        },
    )
    if created:
        logger.info(
            "[BusinessNotification] created kind=%s business=%s id=%s",
            kind, business_id, notification.pk,
        )
    return notification, created


def on_commit_safely(func: Callable[[], object], *, description: str) -> None:
    """Programa `func` para después del commit de la transacción actual.

    Fuera de una transacción corre en el acto. Cualquier excepción se
    registra y se traga: una notificación nunca compromete ni hace fallar la
    operación que la originó.
    """

    def _run():
        try:
            func()
        except Exception:
            logger.exception("[BusinessNotification] failed: %s", description)

    transaction.on_commit(_run)

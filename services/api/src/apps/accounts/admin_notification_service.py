"""
admin_notification_service.py — helpers for creating AdminNotification records.

Public API
----------
create_admin_notification(
    *, notif_type, title, severity="info", message="",
    target_role="", target_user=None, business=None,
    related_object_type="", related_object_id="",
    action_url="", metadata=None, dedupe_window_seconds=None
) -> AdminNotification | None

Design constraints
------------------
- Best-effort: any unexpected exception is caught, logged, and None is returned.
  Callers (billing hooks, signal handlers, etc.) must never crash because a
  notification failed to persist.
- NO send_mail / NO EmailMessage — purely DB writes.
- Metadata sanitization: sensitive keys are stripped before saving.
- Optional deduplication: if dedupe_window_seconds is set AND related_object_id
  is non-empty, a SHA-256-derived dedupe_key is computed and the function
  returns None if an unread/read notification with that key already exists
  within the window. It creates a fresh one if the earlier record is
  resolved or archived.
"""
import hashlib
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

# Keys that must never appear in notification metadata.
_SENSITIVE_META_KEYS = frozenset({
    'token',
    'password',
    'pin',
    'secret',
    'authorization',
    'x_signature',
    'raw_payload_json',
    'headers',
    'access_token',
    'refresh_token',
})


def _sanitize_metadata(raw: dict) -> dict:
    """Remove sensitive keys from metadata before persisting."""
    return {k: v for k, v in raw.items() if k not in _SENSITIVE_META_KEYS}


def _compute_dedupe_key(notif_type: str, related_object_type: str, related_object_id: str) -> str:
    """Return SHA-256[:64] of 'notif_type:related_object_type:related_object_id'."""
    raw = f'{notif_type}:{related_object_type}:{related_object_id}'
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def create_admin_notification(
    *,
    notif_type: str,
    title: str,
    severity: str = 'info',
    message: str = '',
    target_role: str = '',
    target_user=None,
    business=None,
    related_object_type: str = '',
    related_object_id: str = '',
    action_url: str = '',
    metadata: dict | None = None,
    dedupe_window_seconds: int | None = None,
):
    """
    Create and persist an AdminNotification.

    Returns the saved AdminNotification instance, or None if:
      - An unexpected exception occurs (logged at ERROR level).
      - Deduplication logic decides a duplicate already exists.
    """
    # Deferred import to avoid circular import at module load time.
    from apps.accounts.admin_notification import AdminNotification

    try:
        clean_metadata = _sanitize_metadata(metadata or {})

        dedupe_key = ''

        # ── Deduplication ─────────────────────────────────────────────────
        if dedupe_window_seconds is not None and related_object_id:
            dedupe_key = _compute_dedupe_key(notif_type, related_object_type, related_object_id)
            window_start = timezone.now() - timezone.timedelta(seconds=dedupe_window_seconds)

            existing = (
                AdminNotification.objects
                .filter(
                    dedupe_key=dedupe_key,
                    created_at__gte=window_start,
                    status__in=[
                        AdminNotification.Status.UNREAD,
                        AdminNotification.Status.READ,
                    ],
                )
                .first()
            )
            if existing is not None:
                return None
            # If all earlier records with this key are resolved/archived, fall through
            # and create a new one.

        # ── Create ────────────────────────────────────────────────────────
        notification = AdminNotification(
            notif_type=notif_type,
            title=title,
            severity=severity,
            message=message,
            target_role=target_role,
            target_user=target_user,
            business=business,
            related_object_type=related_object_type,
            related_object_id=related_object_id,
            action_url=action_url,
            dedupe_key=dedupe_key,
            metadata=clean_metadata,
        )
        notification.save()
        return notification

    except Exception:
        logger.error(
            'create_admin_notification failed',
            exc_info=True,
            extra={
                'notif_type': notif_type,
                'title': title,
            },
        )
        return None

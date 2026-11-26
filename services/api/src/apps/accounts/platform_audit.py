"""
Lightweight audit service for platform admin actions.

Wraps AccessAuditLog creation for internal backoffice operations.
Reuses the existing AccessAuditLog model — no separate table needed.
"""
import logging

from apps.accounts.models import AccessAuditLog

logger = logging.getLogger(__name__)


def log_platform_action(
    *,
    action: str,
    actor,
    entity_type: str = '',
    entity_id: str = '',
    details: dict | None = None,
    ip_address: str | None = None,
    user_agent: str = '',
    target_user=None,
    business=None,
):
    """
    Record a platform admin action in the AccessAuditLog.

    For platform-level actions that don't relate to a specific business,
    `business` can be None — we pass the first membership's business or skip.
    """
    try:
        biz = business
        if biz is None and actor and hasattr(actor, 'memberships'):
            first = actor.memberships.first()
            if first:
                biz = first.business

        # business is required by the model's FK, so if we still don't have one, skip
        if biz is None:
            logger.warning(
                "log_platform_action skipped: no business context for action=%s actor=%s",
                action, actor,
            )
            return None

        return AccessAuditLog.objects.create(
            action=action,
            actor=actor,
            actor_type=AccessAuditLog.ActorType.USER,
            target_user=target_user,
            business=biz,
            details=details or {},
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else '',
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except Exception:
        logger.exception("Failed to log platform action: %s", action)
        return None


def record_platform_action(
    *,
    action: str,
    actor,
    business,
    entity_type: str = '',
    entity_id: str = '',
    details: dict | None = None,
    target_user=None,
):
    """
    PROD-02F4: MANDATORY variant of ``log_platform_action``.

    Never swallows errors and never falls back to another business: any
    failure propagates so the caller's transaction (e.g. client provisioning)
    rolls back with it. Use it only inside ``transaction.atomic()`` when the
    operation must not exist without its audit row.
    """
    if business is None or actor is None:
        raise ValueError(f'record_platform_action({action}) requires actor and business.')
    return AccessAuditLog.objects.create(
        action=action,
        actor=actor,
        actor_type=AccessAuditLog.ActorType.USER,
        target_user=target_user,
        business=business,
        details=details or {},
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else '',
    )

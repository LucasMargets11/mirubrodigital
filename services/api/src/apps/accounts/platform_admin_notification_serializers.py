"""
Serializers for platform admin notification endpoints.

MVP: exposes all public fields; deliberately excludes metadata,
dedupe_key, target_role, and target_user.
"""
from apps.accounts.admin_notification import AdminNotification


def serialize_notification(n: AdminNotification) -> dict:
    """Return the public representation of a single AdminNotification."""
    return {
        'id': str(n.id),
        'notif_type': n.notif_type,
        'severity': n.severity,
        'title': n.title,
        'message': n.message,
        'status': n.status,
        'action_url': n.action_url,
        'business_id': n.business_id,
        'business_name': n.business.name if n.business else None,
        'related_object_type': n.related_object_type,
        'related_object_id': n.related_object_id,
        'created_at': n.created_at.isoformat() if n.created_at else None,
        'read_at': n.read_at.isoformat() if n.read_at else None,
        'resolved_at': n.resolved_at.isoformat() if n.resolved_at else None,
        'archived_at': n.archived_at.isoformat() if n.archived_at else None,
    }

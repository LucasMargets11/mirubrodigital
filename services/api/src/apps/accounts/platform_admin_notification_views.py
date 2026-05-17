"""
Platform admin views — In-app Notification Center (PR-ADMIN-10C).

Endpoints under /api/v1/platform-admin/notifications/

Role matrix:
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ Endpoint                              │ Method │ superadmin │ operations │ support_agent │ content_admin │
├───────────────────────────────────────┼────────┼────────────┼────────────┼───────────────┼───────────────┤
│ notifications/                        │  GET   │  all       │  scoped    │  scoped       │  scoped       │
│ notifications/unread-count/           │  GET   │  all       │  scoped    │  scoped       │  scoped       │
│ notifications/<id>/read/              │  POST  │  any       │  scoped    │  scoped       │  scoped       │
│ notifications/<id>/archive/           │  POST  │  any       │  scoped    │  scoped       │  scoped       │
│ notifications/<id>/resolve/           │  POST  │  any       │  scoped    │  scoped       │  scoped       │
└───────────────────────────────────────┴────────┴────────────┴────────────┴───────────────┴───────────────┘

Scoping rules:
  superadmin     → all notifications (no filter)
  other roles    → target_role=<own_role> OR target_user=<self>
  broadcast (target_role='') → only visible to superadmin

No send_mail. No EmailMessage. No modification of create_admin_notification.
"""
import math

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.admin_notification import AdminNotification
from apps.accounts.platform_admin_notification_serializers import serialize_notification
from apps.accounts.platform_permissions import IsPlatformStaff

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Valid choice sets (computed once at import time)
_VALID_STATUSES  = {c[0] for c in AdminNotification.Status.choices}
_VALID_SEVERITIES = {c[0] for c in AdminNotification.Severity.choices}
_VALID_TYPES     = {c[0] for c in AdminNotification.NotifType.choices}


# ── Scoping helper ────────────────────────────────────────────────────────────

def _visible_notifications_for(user) -> 'QuerySet[AdminNotification]':
    """
    Return the base queryset of notifications visible to this staff user.

    superadmin → all
    everyone else → target_role=<own_role> OR target_user=<self>
    """
    profile = getattr(user, 'account_profile', None)
    internal_role = (profile.internal_role or '') if profile else ''

    if internal_role == 'superadmin':
        return AdminNotification.objects.all()

    return AdminNotification.objects.filter(
        Q(target_user=user) | Q(target_role=internal_role, target_role__gt='')
    )


# ── List ──────────────────────────────────────────────────────────────────────

class AdminNotificationListView(APIView):
    """
    GET /api/v1/platform-admin/notifications/

    Query params:
      status=unread|read|resolved|archived   (default: all except archived)
      severity=info|success|warning|critical
      type=<notif_type>
      page=1
      page_size=20
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request: Request) -> Response:
        qs = _visible_notifications_for(request.user).select_related('business')

        # ── Filter: status ────────────────────────────────────────────────
        status_param = request.query_params.get('status', '').strip()
        if status_param:
            if status_param not in _VALID_STATUSES:
                return Response(
                    {'error': f'status inválido. Valores aceptados: {sorted(_VALID_STATUSES)}'},
                    status=400,
                )
            qs = qs.filter(status=status_param)
        else:
            # Default: exclude archived
            qs = qs.exclude(status=AdminNotification.Status.ARCHIVED)

        # ── Filter: severity ──────────────────────────────────────────────
        severity_param = request.query_params.get('severity', '').strip()
        if severity_param:
            if severity_param not in _VALID_SEVERITIES:
                return Response(
                    {'error': f'severity inválida. Valores aceptados: {sorted(_VALID_SEVERITIES)}'},
                    status=400,
                )
            qs = qs.filter(severity=severity_param)

        # ── Filter: type ──────────────────────────────────────────────────
        type_param = request.query_params.get('type', '').strip()
        if type_param:
            if type_param not in _VALID_TYPES:
                return Response(
                    {'error': f'type inválido. Valores aceptados: {sorted(_VALID_TYPES)}'},
                    status=400,
                )
            qs = qs.filter(notif_type=type_param)

        # ── Ordering ──────────────────────────────────────────────────────
        qs = qs.order_by('-created_at')

        # ── Pagination ────────────────────────────────────────────────────
        total = qs.count()

        # Compute unread_count on the visible (filtered-by-filters, but not by status
        # unless status was explicitly requested) base queryset.
        # For simplicity, count unread across the whole visible scope (ignoring filters).
        unread_count = _visible_notifications_for(request.user).filter(
            status=AdminNotification.Status.UNREAD
        ).count()

        try:
            page_size = min(MAX_PAGE_SIZE, max(1, int(request.query_params.get('page_size', DEFAULT_PAGE_SIZE))))
        except (ValueError, TypeError):
            page_size = DEFAULT_PAGE_SIZE

        total_pages = max(1, math.ceil(total / page_size))

        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        page = min(page, total_pages)

        offset = (page - 1) * page_size
        items = list(qs[offset: offset + page_size])

        return Response({
            'results': [serialize_notification(n) for n in items],
            'total': total,
            'unread_count': unread_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        })


# ── Unread count ──────────────────────────────────────────────────────────────

class AdminNotificationUnreadCountView(APIView):
    """
    GET /api/v1/platform-admin/notifications/unread-count/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def get(self, request: Request) -> Response:
        base_qs = _visible_notifications_for(request.user)
        unread_qs = base_qs.filter(status=AdminNotification.Status.UNREAD)

        count = unread_qs.count()
        critical_count = unread_qs.filter(severity=AdminNotification.Severity.CRITICAL).count()

        return Response({
            'count': count,
            'critical_count': critical_count,
        })


# ── Shared lookup helper ──────────────────────────────────────────────────────

def _get_notification_for_user(user, notification_id):
    """
    Return the AdminNotification if visible to this user, or None.
    """
    try:
        return _visible_notifications_for(user).get(pk=notification_id)
    except AdminNotification.DoesNotExist:
        return None


# ── Mark read ─────────────────────────────────────────────────────────────────

class AdminNotificationMarkReadView(APIView):
    """
    POST /api/v1/platform-admin/notifications/<notification_id>/read/
    Idempotent: unread → read. Already-read returns 200 unchanged.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def post(self, request: Request, notification_id) -> Response:
        n = _get_notification_for_user(request.user, notification_id)
        if n is None:
            return Response({'error': 'Notificación no encontrada.'}, status=404)

        n.mark_read()  # idempotent
        return Response(serialize_notification(n))


# ── Archive ───────────────────────────────────────────────────────────────────

class AdminNotificationArchiveView(APIView):
    """
    POST /api/v1/platform-admin/notifications/<notification_id>/archive/
    Idempotent: any status → archived.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def post(self, request: Request, notification_id) -> Response:
        n = _get_notification_for_user(request.user, notification_id)
        if n is None:
            return Response({'error': 'Notificación no encontrada.'}, status=404)

        n.mark_archived()  # idempotent
        return Response(serialize_notification(n))


# ── Resolve ───────────────────────────────────────────────────────────────────

class AdminNotificationResolveView(APIView):
    """
    POST /api/v1/platform-admin/notifications/<notification_id>/resolve/
    Idempotent: unread|read → resolved. Sets read_at if was unread.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff]

    def post(self, request: Request, notification_id) -> Response:
        n = _get_notification_for_user(request.user, notification_id)
        if n is None:
            return Response({'error': 'Notificación no encontrada.'}, status=404)

        # If still unread, stamp read_at first, then resolve.
        if n.status == AdminNotification.Status.UNREAD:
            n.mark_read()
        n.mark_resolved()  # idempotent
        return Response(serialize_notification(n))

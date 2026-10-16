"""API de notificaciones internas del Business (Slice 6D).

GET  /api/v1/notifications/business/             → últimas notificaciones + unread_count
POST /api/v1/notifications/business/<id>/read/   → marca como leída (idempotente)

Siempre filtrado por `request.business`: nunca se ven notificaciones de otro
negocio. Visibilidad por kind (CUSTOMER 07C.1):
  - miembros activos con rol en `RECIPIENT_ROLES` (owner/admin) → todos los kinds;
  - el resto → solo los kinds de `KIND_VIEW_PERMISSIONS` cuyo permiso RBAC
    tienen (manager → `customer_reminder_due`). Sin ninguno → 403.
Lista, `unread_count` y mark-as-read usan el mismo queryset visible: un kind
oculto no aparece, no cuenta y su `read/` responde 404 (igual que otro negocio).
Avisos personales (LEADS 04B.3, `recipient` informado): solo los ve su
destinatario, además de cumplir la regla por kind; para el resto son 404.
"""
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership, request_has_permission

from .business_notifications import KIND_VIEW_PERMISSIONS, can_view_business_notifications
from .models import BusinessNotification

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


ALL_KINDS = None


def _visible_kinds(request):
    """`ALL_KINDS` (sin filtro) para owner/admin; si no, el set de kinds habilitados por RBAC."""
    cached = getattr(request, '_business_notification_kinds', False)
    if cached is not False:
        return cached
    membership = getattr(request, 'membership', None)
    if can_view_business_notifications(membership):
        kinds = ALL_KINDS
    elif membership is None or getattr(membership, 'status', 'active') != 'active':
        kinds = frozenset()
    else:
        kinds = frozenset(
            kind for kind, permission in KIND_VIEW_PERMISSIONS.items()
            if request_has_permission(request, permission)
        )
    request._business_notification_kinds = kinds
    return kinds


class CanViewBusinessNotifications(BasePermission):
    message = 'Tu rol no puede ver las notificaciones del negocio.'

    def has_permission(self, request, view) -> bool:
        kinds = _visible_kinds(request)
        return kinds is ALL_KINDS or bool(kinds)


class BusinessNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessNotification
        fields = ['id', 'kind', 'severity', 'title', 'message', 'action_url', 'read_at', 'created_at']
        read_only_fields = fields


def _scoped(request):
    qs = BusinessNotification.objects.filter(business=request.business).filter(
        Q(recipient__isnull=True) | Q(recipient=request.user)
    )
    kinds = _visible_kinds(request)
    if kinds is not ALL_KINDS:
        qs = qs.filter(kind__in=kinds)
    return qs


class BusinessNotificationListView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, CanViewBusinessNotifications]

    def get(self, request):
        qs = _scoped(request)
        unread_count = qs.filter(read_at__isnull=True).count()
        if request.query_params.get('unread') in ('1', 'true'):
            qs = qs.filter(read_at__isnull=True)
        try:
            limit = int(request.query_params.get('limit', DEFAULT_LIMIT))
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT
        limit = max(1, min(limit, MAX_LIMIT))
        return Response({
            'results': BusinessNotificationSerializer(qs[:limit], many=True).data,
            'unread_count': unread_count,
        })


class BusinessNotificationReadView(APIView):
    permission_classes = [IsAuthenticated, HasBusinessMembership, CanViewBusinessNotifications]

    def post(self, request, pk):
        updated = _scoped(request).filter(pk=pk, read_at__isnull=True).update(read_at=timezone.now())
        if not updated and not _scoped(request).filter(pk=pk).exists():
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(BusinessNotificationSerializer(_scoped(request).get(pk=pk)).data)

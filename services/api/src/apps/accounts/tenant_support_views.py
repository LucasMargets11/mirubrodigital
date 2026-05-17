"""
Tenant-facing support ticket views.

Allows business owners to create, list, view, reply, close, and reopen
support tickets from the tenant portal. All queries are scoped to
``request.business`` (multi-tenant isolation).

Billing enforcement is bypassed so that support remains available even
when the subscription is suspended or canceled.
"""
from django.db.models import Count, Max, Q, Exists, OuterRef
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from apps.accounts.models import AccountProfile
from apps.accounts.permissions import HasBusinessMembership
from apps.accounts.platform_audit import log_platform_action
from apps.accounts.support_ticket import SupportTicket, TicketMessage
from apps.notifications.admin_helpers import queue_admin_transactional_email

PAGE_SIZE = 25
MAX_SUBJECT_LENGTH = 200
MAX_MESSAGE_LENGTH = 5000
MAX_OPEN_TICKETS_PER_BUSINESS = 10


# ── Permissions ───────────────────────────────────────────────────────────────

class IsOwnerRole(BasePermission):
    """Only allows users with role='owner' on the current membership."""
    message = 'Solo el dueño del negocio puede acceder a soporte.'

    def has_permission(self, request: Request, view) -> bool:
        membership = getattr(request, 'membership', None)
        if membership is None:
            return False
        return membership.role == 'owner'


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_staff_user(user) -> bool:
    """Return True if the user is platform staff."""
    profile = getattr(user, 'account_profile', None)
    if profile is None:
        return False
    return profile.is_platform_staff


def _serialize_ticket_row(t) -> dict:
    """Tenant-safe ticket row for list view."""
    return {
        'id': str(t.id),
        'reference': t.reference,
        'subject': t.subject,
        'status': t.status,
        'category': t.category,
        'created_at': t.created_at.isoformat() if t.created_at else None,
        'updated_at': t.updated_at.isoformat() if t.updated_at else None,
        'has_staff_reply': bool(getattr(t, 'has_staff_reply', False)),
        'last_reply_at': (
            getattr(t, 'last_reply_at', None).isoformat()
            if getattr(t, 'last_reply_at', None)
            else None
        ),
    }


def _serialize_message_tenant(m) -> dict:
    """Serialize a message for the tenant view — anonymise staff authors."""
    author = m.author
    if author is None:
        author_name = 'Sistema'
        is_from_staff = False
    elif _is_staff_user(author):
        author_name = 'Soporte Mi Rubro'
        is_from_staff = True
    else:
        author_name = author.get_full_name() or author.email
        is_from_staff = False

    return {
        'id': str(m.id),
        'body': m.body,
        'created_at': m.created_at.isoformat() if m.created_at else None,
        'is_from_staff': is_from_staff,
        'author_name': author_name,
    }


def _build_admin_ticket_url(ticket_id: str) -> str:
    """Build the admin panel URL for a given ticket."""
    base = getattr(settings, 'ADMIN_FRONTEND_URL', '').rstrip('/')
    return f"{base}/soporte/{ticket_id}"


def _queue_ticket_created_email(ticket, user) -> None:
    """Best-effort: enqueue internal admin email for a new tenant ticket."""
    try:
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Nuevo ticket de soporte en MiRubro",
            template_key="admin_support_ticket_created",
            context={
                "ticket_reference": ticket.reference,
                "ticket_subject": ticket.subject,
                "ticket_category": ticket.category,
                "ticket_priority": ticket.priority,
                "business_name": ticket.business.name,
                "contact_email": ticket.contact_email,
                "created_at": ticket.created_at.strftime("%d/%m/%Y %H:%M") if ticket.created_at else "",
                "admin_url": _build_admin_ticket_url(str(ticket.id)),
            },
            related_business=ticket.business,
            related_user=user,
            metadata={
                "event_type": "admin_support_ticket_created",
                "ticket_id": str(ticket.id),
                "ticket_reference": ticket.reference,
                "ticket_category": ticket.category,
                "ticket_priority": ticket.priority,
                "related_business_id": str(ticket.business_id),
            },
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_queue_ticket_created_email: error inesperado para ticket %s", ticket.id
        )


def _notify_admin_ticket_created(ticket) -> None:
    """Best-effort: create admin in-app notification for a new tenant-created support ticket."""
    # Guard: only notify for tickets originated from the tenant portal.
    if getattr(ticket, 'origin', None) != SupportTicket.ORIGIN_TENANT:
        return
    try:
        from apps.accounts.admin_notification_service import create_admin_notification
        create_admin_notification(
            notif_type='support_ticket_created',
            severity='warning',
            target_role='support_agent',
            title='Nuevo ticket de soporte',
            message=f'{ticket.business.name} creó un nuevo ticket: {ticket.subject}',
            business=ticket.business,
            related_object_type='support_ticket',
            related_object_id=str(ticket.id),
            action_url=f'/admin/soporte/{ticket.id}',
            metadata={
                'ticket_reference': ticket.reference,
                'ticket_priority': ticket.priority,
                'ticket_category': ticket.category,
            },
        )
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).exception(
            '_notify_admin_ticket_created: error inesperado para ticket %s', ticket.id,
        )


def _log_tenant_action(action, user, ticket, details=None, request=None):
    """Convenience wrapper around log_platform_action for tenant actions."""
    log_platform_action(
        action=action,
        actor=user,
        entity_type='support_ticket',
        entity_id=str(ticket.id),
        business=ticket.business,
        details=details or {},
        ip_address=request.META.get('REMOTE_ADDR') if request else None,
        user_agent=request.META.get('HTTP_USER_AGENT', '') if request else '',
    )


# ── Views ─────────────────────────────────────────────────────────────────────

class TenantTicketListCreateView(APIView):
    """
    GET  /api/v1/support/tickets/          — list tickets for current business
    POST /api/v1/support/tickets/          — create a new ticket
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, IsOwnerRole]
    billing_enforcement_bypass = True

    def get(self, request: Request) -> Response:
        qs = (
            SupportTicket.objects
            .filter(business=request.business)
            .annotate(
                last_reply_at=Max('messages__created_at'),
                has_staff_reply=Exists(
                    TicketMessage.objects.filter(
                        ticket=OuterRef('pk'),
                        is_system=False,
                        author__account_profile__is_platform_staff=True,
                    )
                ),
            )
        )

        # Optional status filter
        status_filter = request.query_params.get('status', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        qs = qs.order_by('-updated_at')

        # Pagination
        total = qs.count()
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, total_pages)
        offset = (page - 1) * PAGE_SIZE

        tickets = list(qs[offset:offset + PAGE_SIZE])

        return Response({
            'results': [_serialize_ticket_row(t) for t in tickets],
            'total': total,
            'page': page,
            'page_size': PAGE_SIZE,
            'total_pages': total_pages,
        })

    def post(self, request: Request) -> Response:
        # Anti-spam: max open tickets per business
        open_count = SupportTicket.objects.filter(
            business=request.business,
            status__in=[
                SupportTicket.STATUS_OPEN,
                SupportTicket.STATUS_IN_PROGRESS,
                SupportTicket.STATUS_WAITING,
            ],
        ).count()
        if open_count >= MAX_OPEN_TICKETS_PER_BUSINESS:
            return Response(
                {'detail': f'Límite de {MAX_OPEN_TICKETS_PER_BUSINESS} tickets abiertos alcanzado. Cerrá o esperá resolución de tickets existentes.'},
                status=400,
            )

        subject = (request.data.get('subject') or '').strip()
        if not subject:
            return Response({'detail': 'subject es requerido.'}, status=400)
        if len(subject) > MAX_SUBJECT_LENGTH:
            return Response({'detail': f'subject demasiado largo (máx {MAX_SUBJECT_LENGTH}).'}, status=400)

        category = (request.data.get('category') or 'other').strip()
        valid_categories = {c[0] for c in SupportTicket.CATEGORY_CHOICES}
        if category not in valid_categories:
            category = 'other'

        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'detail': 'body es requerido.'}, status=400)
        if len(body) > MAX_MESSAGE_LENGTH:
            return Response({'detail': f'body demasiado largo (máx {MAX_MESSAGE_LENGTH}).'}, status=400)

        contact_email = (request.data.get('contact_email') or request.user.email or '').strip()

        ticket = SupportTicket(
            subject=subject,
            business=request.business,
            category=category,
            contact_email=contact_email,
            created_by=request.user,
            origin=SupportTicket.ORIGIN_TENANT,
        )
        ticket.save()

        TicketMessage.objects.create(
            ticket=ticket,
            author=request.user,
            body=body,
        )

        _log_tenant_action(
            'TENANT_TICKET_CREATED', request.user, ticket,
            details={'reference': ticket.reference, 'category': category},
            request=request,
        )

        _queue_ticket_created_email(ticket, request.user)
        _notify_admin_ticket_created(ticket)

        return Response({
            'id': str(ticket.id),
            'reference': ticket.reference,
        }, status=201)


class TenantTicketDetailView(APIView):
    """
    GET /api/v1/support/tickets/<ticket_id>/
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, IsOwnerRole]
    billing_enforcement_bypass = True

    def get(self, request: Request, ticket_id: str) -> Response:
        ticket = get_object_or_404(
            SupportTicket.objects.select_related('business'),
            id=ticket_id,
            business=request.business,
        )

        # Exclude system messages from tenant view
        messages = list(
            ticket.messages
            .filter(is_system=False)
            .select_related('author', 'author__account_profile')
            .order_by('created_at')[:200]
        )

        can_close = ticket.status not in (SupportTicket.STATUS_CLOSED,)
        can_reopen = ticket.status == SupportTicket.STATUS_CLOSED

        return Response({
            'id': str(ticket.id),
            'reference': ticket.reference,
            'subject': ticket.subject,
            'status': ticket.status,
            'category': ticket.category,
            'created_at': ticket.created_at.isoformat() if ticket.created_at else None,
            'updated_at': ticket.updated_at.isoformat() if ticket.updated_at else None,
            'messages': [_serialize_message_tenant(m) for m in messages],
            'can_close': can_close,
            'can_reopen': can_reopen,
        })


class TenantTicketReplyView(APIView):
    """
    POST /api/v1/support/tickets/<ticket_id>/reply/
    Body: { body }
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, IsOwnerRole]
    billing_enforcement_bypass = True

    def post(self, request: Request, ticket_id: str) -> Response:
        ticket = get_object_or_404(
            SupportTicket.objects.select_related('business'),
            id=ticket_id,
            business=request.business,
        )

        if ticket.status == SupportTicket.STATUS_CLOSED:
            return Response({'detail': 'No podés responder en un ticket cerrado.'}, status=400)

        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'detail': 'body es requerido.'}, status=400)
        if len(body) > MAX_MESSAGE_LENGTH:
            return Response({'detail': f'body demasiado largo (máx {MAX_MESSAGE_LENGTH}).'}, status=400)

        msg = TicketMessage.objects.create(
            ticket=ticket,
            author=request.user,
            body=body,
        )

        # Auto-reopen: if owner replies while waiting or resolved, revert to open
        if ticket.status in (SupportTicket.STATUS_WAITING, SupportTicket.STATUS_RESOLVED):
            old_status = ticket.status
            ticket.status = SupportTicket.STATUS_OPEN
            ticket.save(update_fields=['status', 'updated_at'])
            # System message visible only to admin
            TicketMessage.objects.create(
                ticket=ticket,
                author=request.user,
                body=f'Ticket reabierto automáticamente por respuesta del cliente (estado anterior: {old_status}).',
                is_system=True,
            )

        _log_tenant_action(
            'TENANT_TICKET_REPLIED', request.user, ticket,
            details={'message_id': str(msg.id)},
            request=request,
        )

        return Response(_serialize_message_tenant(msg), status=201)


class TenantTicketCloseReopenView(APIView):
    """
    POST /api/v1/support/tickets/<ticket_id>/close/
    Body: { "action": "close" } or { "action": "reopen" }
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership, IsOwnerRole]
    billing_enforcement_bypass = True

    def post(self, request: Request, ticket_id: str) -> Response:
        ticket = get_object_or_404(
            SupportTicket.objects.select_related('business'),
            id=ticket_id,
            business=request.business,
        )

        action = (request.data.get('action') or '').strip().lower()

        if action == 'close':
            if ticket.status == SupportTicket.STATUS_CLOSED:
                return Response({'detail': 'El ticket ya está cerrado.'}, status=400)

            old_status = ticket.status
            ticket.status = SupportTicket.STATUS_CLOSED
            ticket.closed_at = timezone.now()
            ticket.save(update_fields=['status', 'closed_at', 'updated_at'])

            TicketMessage.objects.create(
                ticket=ticket,
                author=request.user,
                body=f'Ticket cerrado por el cliente (estado anterior: {old_status}).',
                is_system=True,
            )

            _log_tenant_action(
                'TENANT_TICKET_CLOSED', request.user, ticket,
                details={'previous_status': old_status},
                request=request,
            )

            return Response({
                'id': str(ticket.id),
                'status': ticket.status,
                'closed_at': ticket.closed_at.isoformat(),
            })

        elif action == 'reopen':
            if ticket.status != SupportTicket.STATUS_CLOSED:
                return Response({'detail': 'Solo se puede reabrir un ticket cerrado.'}, status=400)

            ticket.status = SupportTicket.STATUS_OPEN
            ticket.closed_at = None
            ticket.save(update_fields=['status', 'closed_at', 'updated_at'])

            TicketMessage.objects.create(
                ticket=ticket,
                author=request.user,
                body='Ticket reabierto por el cliente.',
                is_system=True,
            )

            _log_tenant_action(
                'TENANT_TICKET_REOPENED', request.user, ticket,
                request=request,
            )

            return Response({
                'id': str(ticket.id),
                'status': ticket.status,
            })

        else:
            return Response(
                {'detail': 'action debe ser "close" o "reopen".'},
                status=400,
            )

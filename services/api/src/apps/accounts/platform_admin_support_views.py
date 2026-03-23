"""
Platform admin views — Support Tickets (Phase 3).

CRUD for internal support tickets + threaded messages.
Cross-linked to Business (client), SubscriptionV2, payments, and notes.
Role matrix — every endpoint requires IsAuthenticated + IsPlatformStaff + HasInternalRole:
┌─────────────────────────────────────────────────────────────────────────┐
│ Endpoint                    │ Method │ superadmin │ operations │ support_agent │
├─────────────────────────────┼────────┼────────────┼────────────┼───────────────┤
│ tickets/                    │  GET   │     ✓      │     ✓      │      ✓        │
│ tickets/create/             │  POST  │     ✓      │     ✓      │      ✓        │
│ tickets/kpis/               │  GET   │     ✓      │     ✓      │      ✓        │
│ tickets/<id>/               │  GET   │     ✓      │     ✓      │      ✓        │
│ tickets/<id>/update/        │ PATCH  │     ✓      │     ✓      │      ✓        │
│ tickets/<id>/messages/      │  POST  │     ✓      │     ✓      │      ✓        │
│ staff/                      │  GET   │     ✓      │     ✓      │      ✓        │
└─────────────────────────────┴────────┴────────────┴────────────┴───────────────┘"""
from django.db.models import Q, Count, Max
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.platform_permissions import IsPlatformStaff, HasInternalRole
from apps.accounts.platform_audit import log_platform_action
from apps.accounts.support_ticket import SupportTicket, TicketMessage

PAGE_SIZE = 25
MAX_SUBJECT_LENGTH = 200
MAX_MESSAGE_LENGTH = 5000


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_ticket_row(t) -> dict:
    return {
        'id': str(t.id),
        'reference': t.reference,
        'subject': t.subject,
        'status': t.status,
        'priority': t.priority,
        'category': t.category,
        'business_id': t.business_id,
        'business_name': t.business.name if t.business else '—',
        'assigned_to_email': t.assigned_to.email if t.assigned_to else None,
        'assigned_to_name': t.assigned_to.get_full_name() if t.assigned_to else None,
        'contact_email': t.contact_email,
        'message_count': getattr(t, 'message_count', 0),
        'last_message_at': (
            getattr(t, 'last_message_at', None).isoformat()
            if getattr(t, 'last_message_at', None)
            else None
        ),
        'created_at': t.created_at.isoformat() if t.created_at else None,
        'updated_at': t.updated_at.isoformat() if t.updated_at else None,
    }


def _serialize_message(m) -> dict:
    return {
        'id': str(m.id),
        'body': m.body,
        'is_system': m.is_system,
        'author_email': m.author.email if m.author else 'Sistema',
        'author_name': m.author.get_full_name() if m.author else 'Sistema',
        'created_at': m.created_at.isoformat() if m.created_at else None,
    }


def _add_system_message(ticket, actor, text: str):
    """Create an auto-generated system message for status/assignment changes."""
    TicketMessage.objects.create(
        ticket=ticket,
        author=actor,
        body=text,
        is_system=True,
    )


# ── List ──────────────────────────────────────────────────────────────────────

class AdminTicketListView(APIView):
    """
    GET /api/v1/platform-admin/tickets/
    Query params: search, status, priority, category, assigned_to, page, sort
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations', 'support_agent']

    def get(self, request: Request) -> Response:
        qs = (
            SupportTicket.objects
            .select_related('business', 'assigned_to')
            .annotate(
                message_count=Count('messages'),
                last_message_at=Max('messages__created_at'),
            )
        )

        # ── Filters ──────────────────────────────────────────────────────
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(reference__icontains=search)
                | Q(subject__icontains=search)
                | Q(business__name__icontains=search)
                | Q(contact_email__icontains=search)
            )

        status = request.query_params.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        priority = request.query_params.get('priority', '').strip()
        if priority:
            qs = qs.filter(priority=priority)

        category = request.query_params.get('category', '').strip()
        if category:
            qs = qs.filter(category=category)

        assigned = request.query_params.get('assigned_to', '').strip()
        if assigned == 'me':
            qs = qs.filter(assigned_to=request.user)
        elif assigned == 'unassigned':
            qs = qs.filter(assigned_to__isnull=True)

        # ── Sort ─────────────────────────────────────────────────────────
        ALLOWED_SORTS = {
            'created_at', '-created_at',
            'updated_at', '-updated_at',
            'priority', '-priority',
            'status', '-status',
        }
        sort = request.query_params.get('sort', '-updated_at').strip()
        if sort not in ALLOWED_SORTS:
            sort = '-updated_at'
        qs = qs.order_by(sort)

        # ── Pagination ───────────────────────────────────────────────────
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


# ── KPIs ──────────────────────────────────────────────────────────────────────

class AdminTicketKPIsView(APIView):
    """
    GET /api/v1/platform-admin/tickets/kpis/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations', 'support_agent']

    def get(self, request: Request) -> Response:
        from django.db.models import Count as DjCount

        qs = SupportTicket.objects.all()
        status_counts = dict(
            qs.values_list('status')
            .annotate(c=DjCount('id'))
            .values_list('status', 'c')
        )
        priority_counts = dict(
            qs.exclude(status__in=['resolved', 'closed'])
            .values_list('priority')
            .annotate(c=DjCount('id'))
            .values_list('priority', 'c')
        )

        total = sum(status_counts.values())
        open_count = status_counts.get('open', 0) + status_counts.get('in_progress', 0) + status_counts.get('waiting_on_client', 0)
        unassigned = qs.filter(
            status__in=['open', 'in_progress', 'waiting_on_client'],
            assigned_to__isnull=True,
        ).count()

        return Response({
            'total': total,
            'open': open_count,
            'by_status': {
                'open': status_counts.get('open', 0),
                'in_progress': status_counts.get('in_progress', 0),
                'waiting_on_client': status_counts.get('waiting_on_client', 0),
                'resolved': status_counts.get('resolved', 0),
                'closed': status_counts.get('closed', 0),
            },
            'by_priority': {
                'urgent': priority_counts.get('urgent', 0),
                'high': priority_counts.get('high', 0),
                'medium': priority_counts.get('medium', 0),
                'low': priority_counts.get('low', 0),
            },
            'unassigned': unassigned,
        })


# ── Create ────────────────────────────────────────────────────────────────────

class AdminTicketCreateView(APIView):
    """
    POST /api/v1/platform-admin/tickets/create/
    Body: { subject, business_id, category?, priority?, subscription_id?, contact_email?, body? }
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations', 'support_agent']

    def post(self, request: Request) -> Response:
        subject = (request.data.get('subject') or '').strip()
        if not subject:
            return Response({'detail': 'subject es requerido.'}, status=400)
        if len(subject) > MAX_SUBJECT_LENGTH:
            return Response({'detail': f'subject demasiado largo (máx {MAX_SUBJECT_LENGTH}).'}, status=400)

        # Validate business
        business_id = request.data.get('business_id')
        if not business_id:
            return Response({'detail': 'business_id es requerido.'}, status=400)
        from apps.business.models import Business
        business = Business.objects.filter(pk=business_id, parent__isnull=True).first()
        if not business:
            return Response({'detail': 'El cliente indicado no existe.'}, status=404)

        # Optional subscription
        subscription = None
        subscription_id = request.data.get('subscription_id')
        if subscription_id:
            from apps.billing.models import SubscriptionV2
            subscription = SubscriptionV2.objects.filter(pk=subscription_id, business=business).first()
            if not subscription:
                return Response({'detail': 'La suscripción indicada no existe o no pertenece al cliente.'}, status=404)

        category = (request.data.get('category') or 'other').strip()
        valid_categories = {c[0] for c in SupportTicket.CATEGORY_CHOICES}
        if category not in valid_categories:
            category = 'other'

        priority = (request.data.get('priority') or 'medium').strip()
        valid_priorities = {p[0] for p in SupportTicket.PRIORITY_CHOICES}
        if priority not in valid_priorities:
            priority = 'medium'

        contact_email = (request.data.get('contact_email') or '').strip()

        ticket = SupportTicket(
            subject=subject,
            business=business,
            subscription=subscription,
            category=category,
            priority=priority,
            contact_email=contact_email,
            created_by=request.user,
        )
        ticket.save()

        # Optional first message
        body = (request.data.get('body') or '').strip()
        if body:
            if len(body) > MAX_MESSAGE_LENGTH:
                body = body[:MAX_MESSAGE_LENGTH]
            TicketMessage.objects.create(
                ticket=ticket,
                author=request.user,
                body=body,
            )

        log_platform_action(
            action='ADMIN_TICKET_CREATED',
            actor=request.user,
            entity_type='support_ticket',
            entity_id=str(ticket.id),
            business=business,
            details={'reference': ticket.reference, 'category': category, 'priority': priority},
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        return Response({
            'id': str(ticket.id),
            'reference': ticket.reference,
        }, status=201)


# ── Detail ────────────────────────────────────────────────────────────────────

class AdminTicketDetailView(APIView):
    """
    GET  /api/v1/platform-admin/tickets/<ticket_id>/
    Full ticket detail with messages, cross-links to client & subscription.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations', 'support_agent']

    def get(self, request: Request, ticket_id: str) -> Response:
        ticket = (
            SupportTicket.objects
            .select_related('business', 'subscription', 'assigned_to', 'created_by')
            .filter(pk=ticket_id)
            .first()
        )
        if not ticket:
            return Response({'detail': 'Ticket no encontrado.'}, status=404)

        messages = list(
            ticket.messages
            .select_related('author')
            .order_by('created_at')[:200]
        )

        # Cross-links: recent payments & billing events from subscription
        recent_payments = []
        recent_events = []
        if ticket.subscription:
            from apps.billing.models import PaymentAttempt, BillingEvent
            recent_payments = list(
                PaymentAttempt.objects
                .filter(subscription=ticket.subscription)
                .order_by('-attempt_at')[:10]
            )
            recent_events = list(
                BillingEvent.objects
                .filter(subscription=ticket.subscription)
                .order_by('-received_at')[:10]
            )

        # Internal notes on the business
        from apps.accounts.admin_internal_note import AdminInternalNote
        business_notes = list(
            AdminInternalNote.objects
            .filter(target_type='business', target_id=str(ticket.business_id))
            .select_related('author')
            .order_by('-created_at')[:10]
        )

        # Audit log
        log_platform_action(
            action='ADMIN_TICKET_VIEWED',
            actor=request.user,
            entity_type='support_ticket',
            entity_id=str(ticket.id),
            business=ticket.business,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        sub = ticket.subscription
        return Response({
            'id': str(ticket.id),
            'reference': ticket.reference,
            'subject': ticket.subject,
            'status': ticket.status,
            'priority': ticket.priority,
            'category': ticket.category,
            'contact_email': ticket.contact_email,
            'created_at': ticket.created_at.isoformat() if ticket.created_at else None,
            'updated_at': ticket.updated_at.isoformat() if ticket.updated_at else None,
            'resolved_at': ticket.resolved_at.isoformat() if ticket.resolved_at else None,
            'closed_at': ticket.closed_at.isoformat() if ticket.closed_at else None,
            # Relations
            'business': {
                'id': ticket.business_id,
                'name': ticket.business.name,
                'slug': ticket.business.slug,
                'status': ticket.business.status,
            } if ticket.business else None,
            'subscription': {
                'id': str(sub.id),
                'plan_code': sub.plan_code,
                'status': sub.status,
                'provider': sub.provider,
                'current_period_end': sub.current_period_end.isoformat() if sub.current_period_end else None,
            } if sub else None,
            'assigned_to': {
                'id': ticket.assigned_to_id,
                'email': ticket.assigned_to.email,
                'name': ticket.assigned_to.get_full_name(),
            } if ticket.assigned_to else None,
            'created_by': {
                'id': ticket.created_by_id,
                'email': ticket.created_by.email,
                'name': ticket.created_by.get_full_name(),
            } if ticket.created_by else None,
            # Thread
            'messages': [_serialize_message(m) for m in messages],
            # Cross-links
            'recent_payments': [
                {
                    'id': str(p.id),
                    'amount': str(p.amount),
                    'currency': p.currency,
                    'status': p.status,
                    'attempt_at': p.attempt_at.isoformat() if p.attempt_at else None,
                }
                for p in recent_payments
            ],
            'recent_billing_events': [
                {
                    'id': str(e.id),
                    'event_type': e.event_type,
                    'status': e.processing_status,
                    'received_at': e.received_at.isoformat() if e.received_at else None,
                }
                for e in recent_events
            ],
            'business_notes': [
                {
                    'id': str(n.id),
                    'body': n.body,
                    'author_email': n.author.email if n.author else 'Sistema',
                    'author_name': n.author.get_full_name() if n.author else 'Sistema',
                    'created_at': n.created_at.isoformat() if n.created_at else None,
                }
                for n in business_notes
            ],
        })


# ── Update ────────────────────────────────────────────────────────────────────

class AdminTicketUpdateView(APIView):
    """
    PATCH /api/v1/platform-admin/tickets/<ticket_id>/update/
    Body (all optional): { status, priority, category, assigned_to_id, contact_email }
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations', 'support_agent']

    def patch(self, request: Request, ticket_id: str) -> Response:
        ticket = SupportTicket.objects.select_related('business', 'assigned_to').filter(pk=ticket_id).first()
        if not ticket:
            return Response({'detail': 'Ticket no encontrado.'}, status=404)

        changes = {}

        # Status
        new_status = (request.data.get('status') or '').strip()
        if new_status:
            valid_statuses = {s[0] for s in SupportTicket.STATUS_CHOICES}
            if new_status not in valid_statuses:
                return Response({'detail': f'status inválido. Opciones: {", ".join(sorted(valid_statuses))}'}, status=400)
            if new_status != ticket.status:
                old = ticket.status
                ticket.status = new_status
                changes['status'] = f'{old} → {new_status}'
                if new_status == 'resolved' and not ticket.resolved_at:
                    ticket.resolved_at = timezone.now()
                if new_status == 'closed' and not ticket.closed_at:
                    ticket.closed_at = timezone.now()

        # Priority
        new_priority = (request.data.get('priority') or '').strip()
        if new_priority:
            valid_priorities = {p[0] for p in SupportTicket.PRIORITY_CHOICES}
            if new_priority not in valid_priorities:
                return Response({'detail': f'priority inválida.'}, status=400)
            if new_priority != ticket.priority:
                old = ticket.priority
                ticket.priority = new_priority
                changes['priority'] = f'{old} → {new_priority}'

        # Category
        new_category = (request.data.get('category') or '').strip()
        if new_category:
            valid_categories = {c[0] for c in SupportTicket.CATEGORY_CHOICES}
            if new_category not in valid_categories:
                return Response({'detail': f'category inválida.'}, status=400)
            if new_category != ticket.category:
                old = ticket.category
                ticket.category = new_category
                changes['category'] = f'{old} → {new_category}'

        # Assignment
        assigned_to_id = request.data.get('assigned_to_id')
        if assigned_to_id is not None:
            if assigned_to_id == '' or assigned_to_id is False:
                # Unassign
                if ticket.assigned_to_id:
                    changes['assigned_to'] = f'{ticket.assigned_to.email} → sin asignar'
                    ticket.assigned_to = None
            else:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                agent = User.objects.filter(
                    pk=assigned_to_id,
                    account_profile__is_platform_staff=True,
                ).first()
                if not agent:
                    return Response({'detail': 'El agente indicado no existe o no es staff.'}, status=404)
                if ticket.assigned_to_id != agent.pk:
                    changes['assigned_to'] = f'→ {agent.email}'
                    ticket.assigned_to = agent

        # Contact email
        new_email = request.data.get('contact_email')
        if new_email is not None:
            ticket.contact_email = new_email.strip()

        if changes:
            ticket.save()
            # System message summarizing changes
            parts = [f'{k}: {v}' for k, v in changes.items()]
            _add_system_message(ticket, request.user, 'Actualización: ' + '; '.join(parts))

            log_platform_action(
                action='ADMIN_TICKET_UPDATED',
                actor=request.user,
                entity_type='support_ticket',
                entity_id=str(ticket.id),
                business=ticket.business,
                details=changes,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
        else:
            ticket.save()  # touch updated_at even if only contact_email changed

        return Response({
            'id': str(ticket.id),
            'status': ticket.status,
            'priority': ticket.priority,
            'category': ticket.category,
            'assigned_to_id': ticket.assigned_to_id,
            'changes': changes,
        })


# ── Messages ──────────────────────────────────────────────────────────────────

class AdminTicketMessageCreateView(APIView):
    """
    POST /api/v1/platform-admin/tickets/<ticket_id>/messages/
    Body: { body }
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations', 'support_agent']

    def post(self, request: Request, ticket_id: str) -> Response:
        ticket = SupportTicket.objects.select_related('business').filter(pk=ticket_id).first()
        if not ticket:
            return Response({'detail': 'Ticket no encontrado.'}, status=404)

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

        log_platform_action(
            action='ADMIN_TICKET_MESSAGE',
            actor=request.user,
            entity_type='support_ticket',
            entity_id=str(ticket.id),
            business=ticket.business,
            details={'message_id': str(msg.id)},
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        return Response(_serialize_message(msg), status=201)


# ── Staff list (for assignment dropdown) ──────────────────────────────────────

class AdminStaffListView(APIView):
    """
    GET /api/v1/platform-admin/staff/
    Returns platform staff users who can be assigned to tickets.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations', 'support_agent']

    def get(self, request: Request) -> Response:
        from apps.accounts.models import AccountProfile
        staff = (
            AccountProfile.objects
            .filter(is_platform_staff=True)
            .select_related('user')
            .order_by('user__first_name', 'user__email')
        )
        return Response({
            'results': [
                {
                    'id': s.user_id,
                    'email': s.user.email,
                    'name': s.user.get_full_name() or s.user.email,
                    'role': s.internal_role,
                }
                for s in staff
            ]
        })

"""
Platform admin views — Clients module.

Exposes Business (HQ) entities as "clients" for the internal backoffice.
Uses SubscriptionV2 as the canonical subscription source.
"""
import math

from django.contrib.auth import get_user_model
from django.db.models import (
    Count, Q, OuterRef, Subquery, CharField, Value, Case, When, F,
    BooleanField,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import AccessAuditLog
from apps.accounts.admin_internal_note import AdminInternalNote
from apps.accounts.platform_permissions import IsPlatformStaff, HasInternalRole
from apps.accounts.platform_audit import log_platform_action
from apps.accounts.support_ticket import SupportTicket
from apps.billing.models import SubscriptionV2, BillingEvent, PaymentAttempt
from apps.business.models import Business

User = get_user_model()

PAGE_SIZE = 25


# ══════════════════════════════════════════════════════════════════════════════
# Helper: admin status label for a Business
# ══════════════════════════════════════════════════════════════════════════════

def _admin_status_label(business: Business) -> str:
    """
    Return a normalized admin status string for a Business.
    Maps real Business.status values — does NOT invent new DB values.
    """
    mapping = {
        'onboarding': 'onboarding',
        'pending_activation': 'onboarding',
        'trialing': 'trialing',
        'active': 'active',
        'past_due': 'past_due',
        'suspended': 'suspended',
        'canceled': 'canceled',
    }
    return mapping.get(business.status, business.status)


def _subscription_admin_status(sub) -> str:
    """Map SubscriptionV2 status to admin label, adding scheduled_cancel."""
    if sub is None:
        return 'none'
    if sub.cancel_at_period_end and sub.status != 'canceled':
        return 'scheduled_cancel'
    return sub.status


def _risk_badges(business, latest_sub) -> list[str]:
    """Compute risk badges for a client row."""
    badges = []
    if business.status == 'past_due':
        badges.append('pago_atrasado')
    if latest_sub and latest_sub.cancel_at_period_end and latest_sub.status != 'canceled':
        badges.append('cancelacion_programada')
    if latest_sub and latest_sub.status == 'suspended':
        badges.append('suspendido')
    return badges


# ══════════════════════════════════════════════════════════════════════════════
# AdminClientListView
# ══════════════════════════════════════════════════════════════════════════════

class AdminClientListView(APIView):
    """
    GET /api/v1/platform-admin/clients/

    Paginated list of HQ businesses (clients).
    Query params: search, status, plan, trial, sort, page
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def get(self, request: Request) -> Response:
        qs = Business.objects.filter(parent__isnull=True).select_related()

        # ── Filters ──────────────────────────────────────────────────────
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(slug__icontains=search)
                | Q(id__icontains=search)
                | Q(memberships__user__email__icontains=search)
            ).distinct()

        status = request.query_params.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        plan = request.query_params.get('plan', '').strip()
        if plan:
            qs = qs.filter(subscriptions_v2__plan_code__icontains=plan, subscriptions_v2__status__in=['active', 'trialing', 'past_due'])

        trial = request.query_params.get('trial', '').strip()
        if trial == 'true':
            qs = qs.filter(status='trialing')
        elif trial == 'false':
            qs = qs.exclude(status='trialing')

        # ── Sorting ──────────────────────────────────────────────────────
        sort = request.query_params.get('sort', '-created_at')
        allowed_sorts = {
            'created_at', '-created_at', 'name', '-name',
            'updated_at', '-updated_at',
        }
        if sort not in allowed_sorts:
            sort = '-created_at'
        qs = qs.order_by(sort)

        # ── Pagination ───────────────────────────────────────────────────
        total = qs.count()
        page = max(int(request.query_params.get('page', 1)), 1)
        total_pages = max(math.ceil(total / PAGE_SIZE), 1)
        offset = (page - 1) * PAGE_SIZE
        businesses = list(qs[offset:offset + PAGE_SIZE])

        # ── Prefetch latest subscription per business ────────────────────
        biz_ids = [b.id for b in businesses]
        subs_by_biz = {}
        if biz_ids:
            subs = (
                SubscriptionV2.objects
                .filter(business_id__in=biz_ids)
                .exclude(status='canceled')
                .order_by('business_id', '-created_at')
            )
            for s in subs:
                if s.business_id not in subs_by_biz:
                    subs_by_biz[s.business_id] = s

        # ── Prefetch user counts ─────────────────────────────────────────
        from apps.accounts.models import Membership
        user_counts = dict(
            Membership.objects
            .filter(business_id__in=biz_ids, status='active')
            .values('business_id')
            .annotate(cnt=Count('id'))
            .values_list('business_id', 'cnt')
        )

        # ── Prefetch branch counts ───────────────────────────────────────
        branch_counts = dict(
            Business.objects
            .filter(parent_id__in=biz_ids)
            .values('parent_id')
            .annotate(cnt=Count('id'))
            .values_list('parent_id', 'cnt')
        )

        # ── Owner email ──────────────────────────────────────────────────
        owner_emails = {}
        owner_memberships = (
            Membership.objects
            .filter(business_id__in=biz_ids, role='owner', status='active')
            .select_related('user')
        )
        for m in owner_memberships:
            if m.business_id not in owner_emails:
                owner_emails[m.business_id] = m.user.email

        # ── Build response ───────────────────────────────────────────────
        results = []
        for biz in businesses:
            sub = subs_by_biz.get(biz.id)
            results.append({
                'id': biz.id,
                'name': biz.name,
                'slug': biz.slug or '',
                'email': owner_emails.get(biz.id, ''),
                'status': _admin_status_label(biz),
                'plan': sub.plan_code if sub else None,
                'subscription_status': _subscription_admin_status(sub),
                'created_at': biz.created_at.isoformat() if biz.created_at else None,
                'next_renewal': sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
                'user_count': user_counts.get(biz.id, 0),
                'branch_count': branch_counts.get(biz.id, 0),
                'risk_badges': _risk_badges(biz, sub),
                'service_type': biz.service_type or biz.default_service or '',
            })

        return Response({
            'results': results,
            'total': total,
            'page': page,
            'page_size': PAGE_SIZE,
            'total_pages': total_pages,
        })


# ══════════════════════════════════════════════════════════════════════════════
# AdminClientDetailView
# ══════════════════════════════════════════════════════════════════════════════

class AdminClientDetailView(APIView):
    """
    GET /api/v1/platform-admin/clients/<business_id>/

    Full detail view for a single client (Business HQ).
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def get(self, request: Request, business_id: int) -> Response:
        try:
            biz = Business.objects.get(pk=business_id, parent__isnull=True)
        except Business.DoesNotExist:
            return Response({'detail': 'Cliente no encontrado.'}, status=404)

        # ── Audit ─────────────────────────────────────────────────────────
        log_platform_action(
            action='ADMIN_CLIENT_VIEWED',
            actor=request.user,
            entity_type='business',
            entity_id=str(biz.id),
            business=biz,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        # ── Subscription (V2 canonical) ──────────────────────────────────
        latest_sub = (
            SubscriptionV2.objects
            .filter(business=biz)
            .exclude(status='canceled')
            .order_by('-created_at')
            .first()
        )
        # Fallback to any sub if all canceled
        if latest_sub is None:
            latest_sub = (
                SubscriptionV2.objects
                .filter(business=biz)
                .order_by('-created_at')
                .first()
            )

        sub_data = None
        if latest_sub:
            sub_data = {
                'id': str(latest_sub.id),
                'plan_code': latest_sub.plan_code,
                'status': latest_sub.status,
                'admin_status': _subscription_admin_status(latest_sub),
                'provider': latest_sub.provider,
                'provider_sub_id': latest_sub.provider_sub_id or '',
                'current_period_start': latest_sub.current_period_start.isoformat() if latest_sub.current_period_start else None,
                'current_period_end': latest_sub.current_period_end.isoformat() if latest_sub.current_period_end else None,
                'cancel_at_period_end': latest_sub.cancel_at_period_end,
                'cancel_requested_at': latest_sub.cancel_requested_at.isoformat() if latest_sub.cancel_requested_at else None,
                'canceled_at': latest_sub.canceled_at.isoformat() if latest_sub.canceled_at else None,
                'cancel_reason': latest_sub.cancel_reason or '',
                'trial_starts_at': latest_sub.trial_starts_at.isoformat() if latest_sub.trial_starts_at else None,
                'trial_ends_at': latest_sub.trial_ends_at.isoformat() if latest_sub.trial_ends_at else None,
                'is_active': latest_sub.is_active,
                'created_at': latest_sub.created_at.isoformat() if latest_sub.created_at else None,
            }

        # ── Owner / Members ──────────────────────────────────────────────
        from apps.accounts.models import Membership
        members = list(
            Membership.objects
            .filter(business=biz, status='active')
            .select_related('user')
            .order_by('role', 'created_at')
        )
        owner = next((m for m in members if m.role == 'owner'), None)
        member_list = [
            {
                'user_id': m.user_id,
                'email': m.user.email,
                'name': m.user.get_full_name() or m.user.get_username(),
                'role': m.role,
            }
            for m in members[:20]
        ]

        # ── Branch count ─────────────────────────────────────────────────
        branch_count = Business.objects.filter(parent=biz).count()

        # ── Recent payments ──────────────────────────────────────────────
        recent_payments = []
        if latest_sub:
            payments = (
                PaymentAttempt.objects
                .filter(subscription=latest_sub)
                .order_by('-attempt_at')[:10]
            )
            recent_payments = [
                {
                    'id': str(p.id),
                    'amount': str(p.amount),
                    'currency': p.currency,
                    'status': p.status,
                    'failure_reason': p.failure_reason or '',
                    'attempt_at': p.attempt_at.isoformat() if p.attempt_at else None,
                }
                for p in payments
            ]

        # ── Recent billing events ────────────────────────────────────────
        recent_events = []
        events_qs = BillingEvent.objects.filter(business=biz).order_by('-received_at')[:10]
        for ev in events_qs:
            recent_events.append({
                'id': str(ev.id),
                'event_type': ev.event_type,
                'status': ev.status,
                'received_at': ev.received_at.isoformat() if ev.received_at else None,
                'error_message': ev.error_message or '',
            })

        # ── Recent audit log ─────────────────────────────────────────────
        recent_audit = list(
            AccessAuditLog.objects
            .filter(business=biz)
            .order_by('-created_at')[:10]
            .values('id', 'action', 'actor__email', 'created_at', 'entity_type')
        )

        # ── Internal notes ───────────────────────────────────────────────
        notes = list(
            AdminInternalNote.objects
            .filter(target_type='business', target_id=str(biz.id))
            .select_related('author')
            .order_by('-created_at')[:20]
        )
        notes_data = [
            {
                'id': str(n.id),
                'body': n.body,
                'author_email': n.author.email if n.author else 'Sistema',
                'author_name': n.author.get_full_name() if n.author else 'Sistema',
                'created_at': n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ]

        # ── Billing profile ──────────────────────────────────────────────
        billing_profile = None
        bp = getattr(biz, 'billing_profile', None)
        if bp:
            billing_profile = {
                'legal_name': bp.legal_name or '',
                'tax_id': bp.tax_id or '',
                'vat_condition': bp.vat_condition or '',
                'email': bp.email or '',
                'phone': bp.phone or '',
            }

        # ── Support summary ──────────────────────────────────────────────
        biz_tickets = SupportTicket.objects.filter(business=biz)
        total_tickets = biz_tickets.count()
        open_tickets = biz_tickets.filter(
            status__in=[SupportTicket.STATUS_OPEN, SupportTicket.STATUS_IN_PROGRESS, SupportTicket.STATUS_WAITING],
        ).count()
        resolved_tickets = biz_tickets.filter(status=SupportTicket.STATUS_RESOLVED).count()

        recent_tickets_qs = biz_tickets.order_by('-created_at')[:5]
        recent_tickets_data = [
            {
                'id': str(t.id),
                'reference': t.reference,
                'subject': t.subject,
                'status': t.status,
                'priority': t.priority,
                'created_at': t.created_at.isoformat() if t.created_at else None,
                'updated_at': t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in recent_tickets_qs
        ]

        last_ticket = biz_tickets.order_by('-updated_at').first()
        support_summary = {
            'total_tickets': total_tickets,
            'open_tickets': open_tickets,
            'resolved_tickets': resolved_tickets,
            'last_ticket_at': last_ticket.updated_at.isoformat() if last_ticket and last_ticket.updated_at else None,
            'last_ticket_reference': last_ticket.reference if last_ticket else None,
            'recent_tickets': recent_tickets_data,
        }

        return Response({
            'id': biz.id,
            'name': biz.name,
            'slug': biz.slug or '',
            'status': _admin_status_label(biz),
            'service_type': biz.service_type or biz.default_service or '',
            'country': biz.country,
            'currency': biz.currency,
            'created_at': biz.created_at.isoformat() if biz.created_at else None,
            'activated_at': biz.activated_at.isoformat() if biz.activated_at else None,
            'trial_starts_at': biz.trial_starts_at.isoformat() if biz.trial_starts_at else None,
            'trial_ends_at': biz.trial_ends_at.isoformat() if biz.trial_ends_at else None,
            'owner': {
                'user_id': owner.user_id,
                'email': owner.user.email,
                'name': owner.user.get_full_name() or owner.user.get_username(),
            } if owner else None,
            'members': member_list,
            'member_count': len(members),
            'branch_count': branch_count,
            'subscription': sub_data,
            'risk_badges': _risk_badges(biz, latest_sub),
            'recent_payments': recent_payments,
            'recent_events': recent_events,
            'recent_audit': [
                {
                    'id': a['id'],
                    'action': a['action'],
                    'actor_email': a['actor__email'] or 'Sistema',
                    'created_at': a['created_at'].isoformat() if a['created_at'] else None,
                    'entity_type': a['entity_type'],
                }
                for a in recent_audit
            ],
            'notes': notes_data,
            'billing_profile': billing_profile,
            'support_summary': support_summary,
        })


# ══════════════════════════════════════════════════════════════════════════════
# AdminClientKPIsView
# ══════════════════════════════════════════════════════════════════════════════

class AdminClientKPIsView(APIView):
    """
    GET /api/v1/platform-admin/clients/kpis/

    KPIs for the clients module header.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def get(self, request: Request) -> Response:
        hq = Business.objects.filter(parent__isnull=True)

        active = hq.filter(status='active').count()
        trialing = hq.filter(status='trialing').count()
        past_due = hq.filter(status='past_due').count()
        canceled = hq.filter(status='canceled').count()
        total = hq.count()

        # Subscription stats
        scheduled_cancel = SubscriptionV2.objects.filter(
            cancel_at_period_end=True,
        ).exclude(status='canceled').count()

        # Plan distribution
        plan_distribution = list(
            SubscriptionV2.objects
            .filter(status__in=['active', 'trialing', 'past_due'])
            .values('plan_code')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Payment issues (any non-approved recent attempts)
        from django.utils import timezone as tz
        thirty_days_ago = tz.now() - tz.timedelta(days=30)
        payment_issues = PaymentAttempt.objects.filter(
            status__in=['rejected', 'chargeback'],
            attempt_at__gte=thirty_days_ago,
        ).count()

        return Response({
            'total_clients': total,
            'active': active,
            'trialing': trialing,
            'past_due': past_due,
            'canceled': canceled,
            'scheduled_cancel': scheduled_cancel,
            'payment_issues_30d': payment_issues,
            'plan_distribution': [
                {'plan': p['plan_code'], 'count': p['count']}
                for p in plan_distribution
            ],
        })

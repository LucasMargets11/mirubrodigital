"""
Aggregation service for the admin reporting / monitoring module (Phase 4).

Pure functions that perform efficient grouped queries across all domains:
clients, subscriptions, payments, tickets, webhooks, audit log.

Selective Redis caching on expensive aggregations (60s TTL).
"""
import logging
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.accounts.models import AccessAuditLog
from apps.billing.models import (
    BillingEvent,
    BillingInvoiceEvent,
    PaymentAttempt,
    SubscriptionV2,
    WebhookDelivery,
)
from apps.business.models import Business
from apps.accounts.support_ticket import SupportTicket

logger = logging.getLogger(__name__)

CACHE_TTL_KPIS = 60          # 60 seconds
CACHE_TTL_DISTRIBUTIONS = 60  # 60 seconds
CACHE_KEY_PREFIX = 'admin_report'


# ── Global KPIs ──────────────────────────────────────────────────────────────

def get_global_kpis() -> dict:
    """
    Platform-wide KPIs: clients, subscriptions, tickets, payments, users.
    Uses grouped COUNT queries (single query per domain).
    Cached for 60s.
    """
    cache_key = f'{CACHE_KEY_PREFIX}:kpis'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    # ── Clients (single grouped query) ──────────────────────────────────
    hq = Business.objects.filter(parent__isnull=True)
    client_counts = dict(
        hq.values_list('status')
        .annotate(c=Count('id'))
        .values_list('status', 'c')
    )
    total_clients = sum(client_counts.values())

    # ── Subscriptions (single grouped query) ─────────────────────────────
    sub_counts = dict(
        SubscriptionV2.objects
        .values_list('status')
        .annotate(c=Count('id'))
        .values_list('status', 'c')
    )
    total_subs = sum(sub_counts.values())
    scheduled_cancel = SubscriptionV2.objects.filter(
        cancel_at_period_end=True,
    ).exclude(status='canceled').count()

    # ── Tickets (single grouped query) ───────────────────────────────────
    ticket_counts = dict(
        SupportTicket.objects
        .values_list('status')
        .annotate(c=Count('id'))
        .values_list('status', 'c')
    )
    tickets_open = (
        ticket_counts.get('open', 0)
        + ticket_counts.get('in_progress', 0)
        + ticket_counts.get('waiting_on_client', 0)
    )
    tickets_unassigned = SupportTicket.objects.filter(
        status__in=['open', 'in_progress', 'waiting_on_client'],
        assigned_to__isnull=True,
    ).count()

    # ── Payments (30 days) ───────────────────────────────────────────────
    pay_counts = dict(
        PaymentAttempt.objects
        .filter(attempt_at__gte=thirty_days_ago)
        .values_list('status')
        .annotate(c=Count('id'))
        .values_list('status', 'c')
    )
    pay_revenue_30d = (
        PaymentAttempt.objects
        .filter(status='approved', attempt_at__gte=thirty_days_ago)
        .aggregate(total=Sum('amount'))['total']
    ) or 0

    # ── Users ────────────────────────────────────────────────────────────
    from django.contrib.auth import get_user_model
    User = get_user_model()
    total_users = User.objects.filter(is_active=True).count()

    result = {
        'clients': {
            'total': total_clients,
            'active': client_counts.get('active', 0),
            'trialing': client_counts.get('trialing', 0),
            'past_due': client_counts.get('past_due', 0),
            'suspended': client_counts.get('suspended', 0),
            'canceled': client_counts.get('canceled', 0),
            'onboarding': client_counts.get('onboarding', 0),
        },
        'subscriptions': {
            'total': total_subs,
            'active': sub_counts.get('active', 0),
            'trialing': sub_counts.get('trialing', 0),
            'past_due': sub_counts.get('past_due', 0),
            'suspended': sub_counts.get('suspended', 0),
            'canceled': sub_counts.get('canceled', 0),
            'checkout_pending': sub_counts.get('checkout_pending', 0),
            'scheduled_cancel': scheduled_cancel,
        },
        'tickets': {
            'total': sum(ticket_counts.values()),
            'open': tickets_open,
            'unassigned': tickets_unassigned,
            'by_status': {
                'open': ticket_counts.get('open', 0),
                'in_progress': ticket_counts.get('in_progress', 0),
                'waiting_on_client': ticket_counts.get('waiting_on_client', 0),
                'resolved': ticket_counts.get('resolved', 0),
                'closed': ticket_counts.get('closed', 0),
            },
        },
        'payments_30d': {
            'approved': pay_counts.get('approved', 0),
            'rejected': pay_counts.get('rejected', 0),
            'chargeback': pay_counts.get('chargeback', 0),
            'refunded': pay_counts.get('refunded', 0),
            'total_attempts': sum(pay_counts.values()),
            'revenue': str(pay_revenue_30d),
        },
        'total_users': total_users,
    }

    cache.set(cache_key, result, CACHE_TTL_KPIS)
    return result


# ── Distributions ────────────────────────────────────────────────────────────

def get_distributions() -> dict:
    """
    Plan, service type, and ticket category distributions.
    Cached for 60s.
    """
    cache_key = f'{CACHE_KEY_PREFIX}:distributions'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    active_statuses = ['active', 'trialing', 'past_due']

    # Plan distribution (non-terminal subs)
    plan_dist = list(
        SubscriptionV2.objects
        .filter(status__in=active_statuses)
        .values('plan_code')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Service type distribution (businesses)
    service_dist = list(
        Business.objects
        .filter(parent__isnull=True, status__in=active_statuses)
        .values('service_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Ticket category distribution (non-closed)
    ticket_cat_dist = list(
        SupportTicket.objects
        .exclude(status__in=['resolved', 'closed'])
        .values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Provider distribution
    provider_dist = list(
        SubscriptionV2.objects
        .filter(status__in=active_statuses)
        .values('provider')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    result = {
        'plan_distribution': plan_dist,
        'service_type_distribution': service_dist,
        'ticket_category_distribution': ticket_cat_dist,
        'provider_distribution': provider_dist,
    }

    cache.set(cache_key, result, CACHE_TTL_DISTRIBUTIONS)
    return result


# ── Operational Alerts ───────────────────────────────────────────────────────

def get_operational_alerts(severity: str | None = None) -> list[dict]:
    """
    Generate actionable operational alerts from live data.
    No caching — always real-time.

    severity: 'critical', 'warning', or None (all).
    """
    now = timezone.now()
    twenty_four_h_ago = now - timedelta(hours=24)
    alerts: list[dict] = []

    # 1. Past-due businesses
    past_due_biz = Business.objects.filter(
        parent__isnull=True, status='past_due',
    ).count()
    if past_due_biz > 0:
        alerts.append({
            'severity': 'critical',
            'category': 'billing',
            'title': f'{past_due_biz} negocio(s) con pago vencido',
            'description': 'Clientes en estado past_due que requieren seguimiento.',
            'count': past_due_biz,
            'link': '/admin/clientes?status=past_due',
        })

    # 2. Suspended subscriptions
    suspended_subs = SubscriptionV2.objects.filter(status='suspended').count()
    if suspended_subs > 0:
        alerts.append({
            'severity': 'critical',
            'category': 'billing',
            'title': f'{suspended_subs} suscripción(es) suspendida(s)',
            'description': 'Suscripciones suspendidas por falta de pago o acción administrativa.',
            'count': suspended_subs,
            'link': '/admin/suscripciones?status=suspended',
        })

    # 3. High retry count (>=2 retries, not canceled)
    high_retry = SubscriptionV2.objects.filter(
        retry_count__gte=2,
    ).exclude(status='canceled').count()
    if high_retry > 0:
        alerts.append({
            'severity': 'warning',
            'category': 'billing',
            'title': f'{high_retry} suscripción(es) con reintentos de cobro elevados',
            'description': 'Suscripciones con ≥2 reintentos fallidos de cobro.',
            'count': high_retry,
            'link': '/admin/suscripciones?risk=reintentos_cobro',
        })

    # 4. Scheduled cancellations
    sched_cancel = SubscriptionV2.objects.filter(
        cancel_at_period_end=True,
    ).exclude(status='canceled').count()
    if sched_cancel > 0:
        alerts.append({
            'severity': 'warning',
            'category': 'billing',
            'title': f'{sched_cancel} cancelación(es) programada(s)',
            'description': 'Suscripciones que se cancelarán al final del período actual.',
            'count': sched_cancel,
            'link': '/admin/suscripciones?risk=cancelacion_programada',
        })

    # 5. Unassigned urgent/high tickets
    urgent_unassigned = SupportTicket.objects.filter(
        status__in=['open', 'in_progress'],
        priority__in=['urgent', 'high'],
        assigned_to__isnull=True,
    ).count()
    if urgent_unassigned > 0:
        alerts.append({
            'severity': 'critical',
            'category': 'soporte',
            'title': f'{urgent_unassigned} ticket(s) urgente(s)/alto(s) sin asignar',
            'description': 'Tickets de prioridad urgente o alta pendientes de asignación.',
            'count': urgent_unassigned,
            'link': '/admin/soporte?priority=urgent&assigned=none',
        })

    # 6. Failed webhooks (last 24h)
    failed_webhooks = WebhookDelivery.objects.filter(
        processing_status__in=['failed', 'dead_letter'],
        received_at__gte=twenty_four_h_ago,
    ).count()
    if failed_webhooks > 0:
        alerts.append({
            'severity': 'warning',
            'category': 'sistema',
            'title': f'{failed_webhooks} webhook(s) fallido(s) en las últimas 24h',
            'description': 'Entregas de webhook con estado failed o dead_letter.',
            'count': failed_webhooks,
            'link': '/admin/suscripciones',
        })

    # 7. Billing events with errors (last 24h)
    error_events = BillingEvent.objects.filter(
        status='error',
        received_at__gte=twenty_four_h_ago,
    ).count()
    if error_events > 0:
        alerts.append({
            'severity': 'warning',
            'category': 'billing',
            'title': f'{error_events} evento(s) de billing con error en 24h',
            'description': 'Eventos de billing que no se procesaron correctamente.',
            'count': error_events,
            'link': '/admin/suscripciones',
        })

    # 8. Rejected payments (last 24h)
    rejected_24h = PaymentAttempt.objects.filter(
        status__in=['rejected', 'chargeback'],
        attempt_at__gte=twenty_four_h_ago,
    ).count()
    if rejected_24h > 0:
        alerts.append({
            'severity': 'warning',
            'category': 'billing',
            'title': f'{rejected_24h} pago(s) rechazado(s)/contracargo en 24h',
            'description': 'Intentos de pago rechazados o contracargos recientes.',
            'count': rejected_24h,
            'link': '/admin/suscripciones',
        })

    # Filter by severity if requested
    if severity:
        alerts = [a for a in alerts if a['severity'] == severity]

    # Sort: critical first, then warning
    severity_order = {'critical': 0, 'warning': 1, 'info': 2}
    alerts.sort(key=lambda a: severity_order.get(a['severity'], 9))

    return alerts


# ── Recent Activity ──────────────────────────────────────────────────────────

def get_recent_activity(limit: int = 15) -> list[dict]:
    """
    Last N audit-log entries. No caching.
    """
    entries = list(
        AccessAuditLog.objects
        .select_related('actor', 'business')
        .order_by('-created_at')[:limit]
        .values(
            'id', 'action', 'created_at',
            'actor__email', 'business__name',
            'entity_type', 'entity_id',
        )
    )
    return [
        {
            'id': e['id'],
            'action': e['action'],
            'actor_email': e['actor__email'] or 'Sistema',
            'business_name': e['business__name'] or '—',
            'entity_type': e['entity_type'],
            'entity_id': e['entity_id'],
            'created_at': e['created_at'].isoformat() if e['created_at'] else None,
        }
        for e in entries
    ]

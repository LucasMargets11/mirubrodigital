"""
Platform admin views — Subscriptions module.

Exposes SubscriptionV2 entities for the internal backoffice.
"""
import math

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.platform_permissions import IsPlatformStaff, HasInternalRole
from apps.accounts.platform_audit import log_platform_action
from apps.billing.models import (
    SubscriptionV2, BillingEvent, PaymentAttempt, BillingInvoiceEvent,
    WebhookDelivery,
)
from apps.billing.cancellation_service import (
    cancel_subscription_immediately,
    CancellationError,
    ADMIN_CANCELLABLE_STATUSES,
)
from apps.billing.mp_service import (
    MercadoPagoCancelError,
    MercadoPagoAuthError,
    ProviderSubscriptionNotFound,
)
from apps.business.models import Business

PAGE_SIZE = 25


def _sub_admin_status(sub: SubscriptionV2) -> str:
    """Admin-friendly subscription status with scheduled_cancel detection."""
    if sub.cancel_at_period_end and sub.status != 'canceled':
        return 'scheduled_cancel'
    return sub.status


def _compute_sub_risk_badges(sub: SubscriptionV2) -> list[str]:
    """Risk badges for a subscription row."""
    badges = []
    if sub.status == 'past_due':
        badges.append('pago_atrasado')
    if sub.cancel_at_period_end and sub.status != 'canceled':
        badges.append('cancelacion_programada')
    if sub.status == 'suspended':
        badges.append('suspendido')
    if sub.retry_count and sub.retry_count >= 2:
        badges.append('reintentos_cobro')
    return badges


# ══════════════════════════════════════════════════════════════════════════════
# AdminSubscriptionListView
# ══════════════════════════════════════════════════════════════════════════════

class AdminSubscriptionListView(APIView):
    """
    GET /api/v1/platform-admin/subscriptions/

    Paginated list of subscriptions (SubscriptionV2).
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def get(self, request: Request) -> Response:
        qs = SubscriptionV2.objects.select_related('business').order_by('-created_at')

        # ── Filters ──────────────────────────────────────────────────────
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(business__name__icontains=search)
                | Q(business__memberships__user__email__icontains=search)
                | Q(id__icontains=search)
                | Q(external_reference__icontains=search)
                | Q(provider_sub_id__icontains=search)
            ).distinct()

        status = request.query_params.get('status', '').strip()
        if status == 'scheduled_cancel':
            qs = qs.filter(cancel_at_period_end=True).exclude(status='canceled')
        elif status:
            qs = qs.filter(status=status)

        plan = request.query_params.get('plan', '').strip()
        if plan:
            qs = qs.filter(plan_code__icontains=plan)

        payment_issue = request.query_params.get('payment_issue', '').strip()
        if payment_issue == 'true':
            qs = qs.filter(status__in=['past_due', 'suspended'])

        # ── Sorting ──────────────────────────────────────────────────────
        sort = request.query_params.get('sort', '-created_at')
        allowed_sorts = {
            'created_at', '-created_at',
            'current_period_end', '-current_period_end',
            'status', '-status',
        }
        if sort not in allowed_sorts:
            sort = '-created_at'
        qs = qs.order_by(sort)

        # ── Pagination ───────────────────────────────────────────────────
        total = qs.count()
        page = max(int(request.query_params.get('page', 1)), 1)
        total_pages = max(math.ceil(total / PAGE_SIZE), 1)
        offset = (page - 1) * PAGE_SIZE
        subs = list(qs[offset:offset + PAGE_SIZE])

        # ── Build last event per subscription ────────────────────────────
        sub_ids = [s.id for s in subs]
        last_events = {}
        if sub_ids:
            events = (
                BillingEvent.objects
                .filter(subscription_id__in=sub_ids)
                .order_by('subscription_id', '-received_at')
            )
            for ev in events:
                if ev.subscription_id not in last_events:
                    last_events[ev.subscription_id] = {
                        'event_type': ev.event_type,
                        'received_at': ev.received_at.isoformat() if ev.received_at else None,
                    }

        results = []
        for sub in subs:
            results.append({
                'id': str(sub.id),
                'business_id': sub.business_id,
                'business_name': sub.business.name if sub.business else '',
                'plan_code': sub.plan_code,
                'status': sub.status,
                'admin_status': _sub_admin_status(sub),
                'provider': sub.provider,
                'provider_sub_id': sub.provider_sub_id or '',
                'current_period_end': sub.current_period_end.isoformat() if sub.current_period_end else None,
                'cancel_at_period_end': sub.cancel_at_period_end,
                'cancel_requested_at': sub.cancel_requested_at.isoformat() if sub.cancel_requested_at else None,
                'canceled_at': sub.canceled_at.isoformat() if sub.canceled_at else None,
                'is_active': sub.is_active,
                'retry_count': sub.retry_count,
                'created_at': sub.created_at.isoformat() if sub.created_at else None,
                'risk_badges': _compute_sub_risk_badges(sub),
                'last_event': last_events.get(sub.id),
            })

        return Response({
            'results': results,
            'total': total,
            'page': page,
            'page_size': PAGE_SIZE,
            'total_pages': total_pages,
        })


# ══════════════════════════════════════════════════════════════════════════════
# AdminSubscriptionDetailView
# ══════════════════════════════════════════════════════════════════════════════

class AdminSubscriptionDetailView(APIView):
    """
    GET /api/v1/platform-admin/subscriptions/<subscription_id>/

    Full detail for a single SubscriptionV2.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def get(self, request: Request, subscription_id: str) -> Response:
        try:
            sub = SubscriptionV2.objects.select_related('business').get(pk=subscription_id)
        except (SubscriptionV2.DoesNotExist, ValueError):
            return Response({'detail': 'Suscripción no encontrada.'}, status=404)

        biz = sub.business

        # ── Audit ─────────────────────────────────────────────────────────
        log_platform_action(
            action='ADMIN_SUBSCRIPTION_VIEWED',
            actor=request.user,
            entity_type='subscription_v2',
            entity_id=str(sub.id),
            business=biz,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )

        # ── Payments ─────────────────────────────────────────────────────
        payments = list(
            PaymentAttempt.objects
            .filter(subscription=sub)
            .order_by('-attempt_at')[:20]
        )
        payments_data = [
            {
                'id': str(p.id),
                'amount': str(p.amount),
                'currency': p.currency,
                'status': p.status,
                'failure_reason': p.failure_reason or '',
                'external_payment_id': p.external_payment_id or '',
                'attempt_at': p.attempt_at.isoformat() if p.attempt_at else None,
                'resolved_at': p.resolved_at.isoformat() if p.resolved_at else None,
            }
            for p in payments
        ]

        # ── Billing events ───────────────────────────────────────────────
        events = list(
            BillingEvent.objects
            .filter(subscription=sub)
            .order_by('-received_at')[:20]
        )
        events_data = [
            {
                'id': str(ev.id),
                'event_type': ev.event_type,
                'status': ev.status,
                'received_at': ev.received_at.isoformat() if ev.received_at else None,
                'processed_at': ev.processed_at.isoformat() if ev.processed_at else None,
                'error_message': ev.error_message or '',
            }
            for ev in events
        ]

        # ── Invoice events ───────────────────────────────────────────────
        invoice_events = list(
            BillingInvoiceEvent.objects
            .filter(subscription=sub)
            .order_by('-created_at')[:10]
        )
        invoices_data = [
            {
                'id': str(ie.id),
                'amount': str(ie.amount),
                'currency': ie.currency,
                'provider_status': ie.provider_status or '',
                'paid_at': ie.paid_at.isoformat() if ie.paid_at else None,
                'created_at': ie.created_at.isoformat() if ie.created_at else None,
            }
            for ie in invoice_events
        ]

        # ── Webhook deliveries (recent) ──────────────────────────────────
        webhook_errors = list(
            WebhookDelivery.objects
            .filter(
                processing_status__in=['failed', 'dead_letter'],
                body_json__preapproval_id=sub.provider_sub_id,
            )
            .order_by('-received_at')[:5]
        ) if sub.provider_sub_id else []
        webhook_data = [
            {
                'id': str(w.id),
                'topic': w.topic,
                'action': w.action,
                'processing_status': w.processing_status,
                'error_message': w.error_message or '',
                'received_at': w.received_at.isoformat() if w.received_at else None,
            }
            for w in webhook_errors
        ]

        # ── Internal notes ───────────────────────────────────────────────
        from apps.accounts.admin_internal_note import AdminInternalNote
        notes = list(
            AdminInternalNote.objects
            .filter(target_type='subscription_v2', target_id=str(sub.id))
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

        return Response({
            'id': str(sub.id),
            'business': {
                'id': biz.id,
                'name': biz.name,
                'slug': biz.slug or '',
                'status': biz.status,
            } if biz else None,
            'plan_code': sub.plan_code,
            'service_type': sub.service_type,
            'status': sub.status,
            'admin_status': _sub_admin_status(sub),
            'provider': sub.provider,
            'provider_sub_id': sub.provider_sub_id or '',
            'external_reference': sub.external_reference,
            'is_active': sub.is_active,
            'trial_starts_at': sub.trial_starts_at.isoformat() if sub.trial_starts_at else None,
            'trial_ends_at': sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
            'current_period_start': sub.current_period_start.isoformat() if sub.current_period_start else None,
            'current_period_end': sub.current_period_end.isoformat() if sub.current_period_end else None,
            'grace_until': sub.grace_until.isoformat() if sub.grace_until else None,
            'retry_count': sub.retry_count,
            'cancel_at_period_end': sub.cancel_at_period_end,
            'cancel_requested_at': sub.cancel_requested_at.isoformat() if sub.cancel_requested_at else None,
            'cancel_reason': sub.cancel_reason or '',
            'canceled_at': sub.canceled_at.isoformat() if sub.canceled_at else None,
            'canceled_by_email': sub.canceled_by.email if sub.canceled_by else None,
            'canceled_by_name': sub.canceled_by.get_full_name() if sub.canceled_by else None,
            # True when an admin can trigger immediate cancellation from the panel.
            'can_cancel': sub.status in ADMIN_CANCELLABLE_STATUSES,
            'price_snapshot': sub.price_snapshot,
            'created_at': sub.created_at.isoformat() if sub.created_at else None,
            'updated_at': sub.updated_at.isoformat() if sub.updated_at else None,
            'risk_badges': _compute_sub_risk_badges(sub),
            'payments': payments_data,
            'events': events_data,
            'invoice_events': invoices_data,
            'webhook_errors': webhook_data,
            'notes': notes_data,
        })


# ══════════════════════════════════════════════════════════════════════════════
# AdminSubscriptionKPIsView
# ══════════════════════════════════════════════════════════════════════════════

class AdminSubscriptionKPIsView(APIView):
    """
    GET /api/v1/platform-admin/subscriptions/kpis/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def get(self, request: Request) -> Response:
        all_subs = SubscriptionV2.objects.all()

        active = all_subs.filter(status='active').count()
        trialing = all_subs.filter(status='trialing').count()
        past_due = all_subs.filter(status='past_due').count()
        suspended = all_subs.filter(status='suspended').count()
        canceled = all_subs.filter(status='canceled').count()
        checkout_pending = all_subs.filter(status='checkout_pending').count()
        scheduled_cancel = all_subs.filter(
            cancel_at_period_end=True,
        ).exclude(status='canceled').count()

        total = all_subs.count()

        return Response({
            'total': total,
            'active': active,
            'trialing': trialing,
            'past_due': past_due,
            'suspended': suspended,
            'canceled': canceled,
            'checkout_pending': checkout_pending,
            'scheduled_cancel': scheduled_cancel,
        })


# ══════════════════════════════════════════════════════════════════════════════
# AdminSubscriptionCancelView
# ══════════════════════════════════════════════════════════════════════════════

class AdminSubscriptionCancelView(APIView):
    """
    POST /api/v1/platform-admin/subscriptions/<subscription_id>/cancel/

    Immediately cancel a subscription from the admin panel.

    Body:
        { "reason": "Cuenta utilizada para prueba de checkout" }

    The preapproval_id is always read from the database — never accepted from
    the request body. Roles allowed: superadmin, operations.

    Responses:
        200 — successfully canceled (or already canceled — idempotent).
        400 — invalid state or missing provider_sub_id.
        403 — insufficient permissions (handled by permission_classes).
        404 — subscription not found.
        409 — state conflict (not cancellable).
        502 — Mercado Pago rejected the cancellation.
        504 — timeout connecting to Mercado Pago.
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'operations']

    def post(self, request: Request, subscription_id: str) -> Response:
        # ── 1. Look up subscription ───────────────────────────────────────
        try:
            sub = SubscriptionV2.objects.select_related('business', 'canceled_by').get(
                pk=subscription_id,
            )
        except (SubscriptionV2.DoesNotExist, ValueError):
            return Response({'detail': 'Suscripción no encontrada.'}, status=404)

        # ── 2. Validate request body ──────────────────────────────────────
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response(
                {'detail': 'El campo "reason" es obligatorio.'},
                status=400,
            )
        if len(reason) > 512:
            return Response(
                {'detail': 'El motivo no puede superar 512 caracteres.'},
                status=400,
            )

        # ── 3. Delegate to domain service ─────────────────────────────────
        try:
            result = cancel_subscription_immediately(
                subscription=sub,
                canceled_by=request.user,
                reason=reason,
            )
        except CancellationError as exc:
            # State conflict: not in a cancellable status, or already handled.
            status_code = 400
            if 'incompatible' in str(exc).lower():
                status_code = 409
            return Response({'detail': str(exc)}, status=status_code)
        except ProviderSubscriptionNotFound:
            # Preapproval not found at MP during PUT or GET confirmation.
            # Local state was NOT modified; operator must investigate manually.
            return Response(
                {'detail': (
                    'No pudimos confirmar la cancelación en Mercado Pago. '
                    'La suscripción no fue modificada en MiRubro. '
                    'Podés volver a intentarlo.'
                )},
                status=502,
            )
        except MercadoPagoAuthError:
            return Response(
                {'detail': (
                    'Error de autenticación con Mercado Pago. '
                    'Verificá el access token en la configuración.'
                )},
                status=502,
            )
        except MercadoPagoCancelError as exc:
            error_msg = str(exc).lower()
            # Timeout indicators
            if 'timeout' in error_msg or 'timed out' in error_msg or 'conexión' in error_msg:
                return Response(
                    {'detail': (
                        'No pudimos confirmar la cancelación en Mercado Pago. '
                        'La suscripción no fue modificada en MiRubro. '
                        'Podés volver a intentarlo.'
                    )},
                    status=504,
                )
            return Response(
                {'detail': (
                    'No pudimos confirmar la cancelación en Mercado Pago. '
                    'La suscripción no fue modificada en MiRubro. '
                    'Podés volver a intentarlo.'
                )},
                status=502,
            )

        # ── 4. Return success response ────────────────────────────────────
        # Re-fetch to get the canonical updated data for the response.
        try:
            sub.refresh_from_db()
        except Exception:
            pass

        return Response({
            'subscription_id': result['subscription_id'],
            'business_id': result['business_id'],
            'previous_status': result['previous_status'],
            'status': result['status'],
            'provider_status': result['provider_status'],
            'is_active': result['is_active'],
            'canceled_at': result['canceled_at'],
            'message': 'La suscripción fue cancelada correctamente.',
        })

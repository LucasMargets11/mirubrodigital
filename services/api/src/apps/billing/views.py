from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.conf import settings
import hashlib
import hmac as hmac_lib
import logging
import uuid

from apps.accounts.access import resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership, RequiresEmailVerified
from apps.business.models import Business
from apps.accounts.models import Membership

from .models import (
    Module, Bundle, Promotion, Subscription, Plan, SubscriptionIntent,
    PaymentEvent, BillingEvent, SubscriptionV2, PaymentAttempt,
    MpCheckoutSession, WebhookDelivery,
)
from .serializers import (
    ModuleSerializer, BundleSerializer, PromotionSerializer, 
    QuoteRequestSerializer, SubscribeRequestSerializer, SubscriptionSerializer
)
from .services import PricingService
from .mp_service import MercadoPagoService

logger = logging.getLogger(__name__)
User = get_user_model()


# ── Phase 2B helpers ──────────────────────────────────────────────────────────

def _resolve_subscriptionv2(business, service_type, preapproval_id=None):
    """
    Resolve the active SubscriptionV2 for a business using the most stable key available.
    Lookup order:
      1. provider_sub_id (most stable — direct MP preapproval ID)
      2. (business, service_type) non-canceled fallback
    Returns the SubscriptionV2 or None.
    """
    if preapproval_id:
        v2 = SubscriptionV2.objects.filter(provider_sub_id=preapproval_id).first()
        if v2:
            return v2
    # Secondary fallback: by (business, service_type)
    v2 = (
        SubscriptionV2.objects
        .filter(business=business, service_type=service_type)
        .exclude(status=SubscriptionV2.Status.CANCELED)
        .order_by('-created_at')
        .first()
    )
    if v2 is None:
        logger.warning(
            "[_resolve_subscriptionv2] No SubscriptionV2 found for business=%s service_type=%s preapproval_id=%s",
            business.pk, service_type, preapproval_id,
        )
    return v2


def _update_billing_event(billing_event, *, sub_v2=None, new_status, error_message=''):
    """Non-blocking helper to update a BillingEvent's status and optional V2 link."""
    if billing_event is None:
        return
    try:
        update_fields = ['status', 'updated_at'] if hasattr(BillingEvent, 'updated_at') else ['status']
        billing_event.status = new_status
        if new_status == BillingEvent.ProcessingStatus.PROCESSED:
            billing_event.processed_at = timezone.now()
            update_fields.append('processed_at')
        if sub_v2 is not None and billing_event.subscription_id is None:
            billing_event.subscription = sub_v2
            update_fields.append('subscription')
        if error_message:
            billing_event.error_message = error_message
            update_fields.append('error_message')
        billing_event.save(update_fields=update_fields)
    except Exception as exc:
        logger.warning("[_update_billing_event] Failed to update BillingEvent: %s", exc)


def _create_payment_attempt(subscription_v2, billing_event, payment_data, payment_id):
    """
    Idempotently create a PaymentAttempt for an approved/rejected MP payment.
    Safe to call multiple times for the same external_payment_id.
    Returns the PaymentAttempt or None if V2 is not available.
    """
    if subscription_v2 is None:
        logger.warning(
            "[_create_payment_attempt] Skipping — no SubscriptionV2 found (payment_id=%s)", payment_id,
        )
        return None
    if not payment_id:
        return None

    payment_id_str = str(payment_id)

    # Idempotency: if already recorded, update and return
    existing = PaymentAttempt.objects.filter(external_payment_id=payment_id_str).first()
    if existing:
        return existing

    payment_status = payment_data.get('status', 'pending')
    status_map = {
        'approved':   PaymentAttempt.Status.APPROVED,
        'authorized': PaymentAttempt.Status.APPROVED,
        'rejected':   PaymentAttempt.Status.REJECTED,
        'cancelled':  PaymentAttempt.Status.REJECTED,
        'pending':    PaymentAttempt.Status.PENDING,
        'in_process': PaymentAttempt.Status.PROCESSING,
        'refunded':   PaymentAttempt.Status.REFUNDED,
    }
    pa_status = status_map.get(payment_status, PaymentAttempt.Status.PENDING)
    is_terminal = pa_status in (
        PaymentAttempt.Status.APPROVED, PaymentAttempt.Status.REJECTED, PaymentAttempt.Status.REFUNDED,
    )

    raw_amount = payment_data.get('transaction_amount') or payment_data.get('total_paid_amount') or 0
    currency = (
        payment_data.get('currency_id')
        or (payment_data.get('transaction_details') or {}).get('currency_id')
        or 'ARS'
    )

    metadata = {
        k: payment_data.get(k)
        for k in ('status_detail', 'payment_method_id', 'payment_type_id', 'installments',
                  'transaction_details', 'external_reference')
        if payment_data.get(k) is not None
    }

    try:
        pa = PaymentAttempt.objects.create(
            subscription=subscription_v2,
            billing_event=billing_event,
            provider=PaymentAttempt.Provider.MERCADOPAGO,
            external_payment_id=payment_id_str,
            external_reference=f"PAY-{uuid.uuid4()}",
            amount=raw_amount,
            currency=currency,
            status=pa_status,
            failure_reason=payment_data.get('status_detail', '') if pa_status == PaymentAttempt.Status.REJECTED else '',
            attempt_at=timezone.now(),
            resolved_at=timezone.now() if is_terminal else None,
            metadata=metadata or None,
        )
        logger.info(
            "[_create_payment_attempt] Created PaymentAttempt %s for SubV2=%s payment_id=%s status=%s",
            pa.pk, subscription_v2.pk, payment_id, pa_status,
        )
        return pa
    except Exception as exc:
        logger.warning("[_create_payment_attempt] Failed (non-fatal): %s", exc)
        return None


class BillingViewSet(viewsets.ViewSet):
    # Default permission is strict, we override per action if needed
    permission_classes = [IsAuthenticated, HasBusinessMembership]
    # Billing views must stay accessible so users can regularize their subscription.
    billing_enforcement_bypass = True

    def get_permissions(self):
        if self.action in ['modules', 'bundles', 'promotions', 'quote']:
            return [AllowAny()]
        if self.action == 'subscribe':
            # subscribe() initiates commercial activation — requires verified email
            # (RequiresEmailVerified is a no-op when EMAIL_VERIFICATION_ENFORCEMENT flag is off)
            return [IsAuthenticated(), HasBusinessMembership(), RequiresEmailVerified()]
        return [IsAuthenticated(), HasBusinessMembership()]

    @action(detail=False, methods=['get'])
    def modules(self, request):
        vertical = request.query_params.get('vertical')
        qs = Module.objects.filter(is_active=True)
        if vertical:
            qs = qs.filter(vertical__in=[vertical, 'both'])
        serializer = ModuleSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def bundles(self, request):
        vertical = request.query_params.get('vertical')
        qs = Bundle.objects.filter(is_active=True)
        if vertical:
            qs = qs.filter(vertical=vertical)
        serializer = BundleSerializer(qs, many=True)
        return Response(serializer.data)
        
    @action(detail=False, methods=['get'])
    def promotions(self, request):
        # vertical = request.query_params.get('vertical')
        qs = Promotion.objects.filter(is_active=True)
        serializer = PromotionSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def quote(self, request):
        serializer = QuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        try:
            quote = PricingService.calculate_quote(
                vertical=data['vertical'],
                billing_period=data['billing_period'],
                plan_type=data['plan_type'],
                selected_module_codes=data.get('selected_module_codes'),
                bundle_code=data.get('bundle_code')
            )
            return Response(quote)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def subscribe(self, request):
        membership = resolve_request_membership(request)
        if membership.role not in ['owner', 'manager']:
            return Response({'detail': 'Only owners/managers can subscribe.'}, status=403)
            
        business = membership.business
        
        serializer = SubscribeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        vertical_map = {'gestion': 'commercial', 'restaurante': 'restaurant', 'menu_qr': 'menu_qr'}
        # Prefer canonical service_type (set via onboarding) over legacy default_service.
        resolved_service = business.service_type or business.default_service or 'gestion'
        vertical = vertical_map.get(resolved_service, 'commercial')
        
        try:
            quote = PricingService.calculate_quote(
                vertical=vertical,
                billing_period=data['billing_period'],
                plan_type=data['plan_type'],
                selected_module_codes=data.get('selected_module_codes'),
                bundle_code=data.get('bundle_code')
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            
        # 2. Save Subscription
        sub, created = Subscription.objects.update_or_create(
            business=business,
            defaults={
                'plan_type': data['plan_type'],
                'billing_period': data['billing_period'],
                'currency': quote['currency'],
                'price_snapshot': quote,
                'status': 'active' 
            }
        )
        
        if data['plan_type'] == 'bundle':
            bundle = Bundle.objects.get(code=data['bundle_code'])
            sub.bundle = bundle
            sub.selected_modules.clear()
        else:
            sub.bundle = None
            codes = [m['code'] for m in quote['modules']]
            modules = Module.objects.filter(code__in=codes)
            sub.selected_modules.set(modules)
            
        sub.save()

        # ── Phase 3: ensure SubscriptionV2 is created/linked ─────────────────────
        # Close the residual birth-path gap: every subscribe call must leave a
        # traceable SubscriptionV2 record so the runtime resolver and webhooks can
        # operate without falling back to legacy heuristics.
        # Idempotent: existing non-canceled V2 is reused (no duplication).
        try:
            service_type = business.default_service or 'gestion'
            v2_plan_code = data.get('bundle_code') or data.get('plan_type') or 'start'
            v2_qs = (
                SubscriptionV2.objects
                .filter(business=business, service_type=service_type)
                .exclude(status=SubscriptionV2.Status.CANCELED)
                .order_by('-created_at')
            )
            v2 = v2_qs.first()
            if v2 is None:
                price_snap = sub.price_snapshot if hasattr(sub, 'price_snapshot') else {}
                # BIRTH PATH: SubscriptionV2 MUST start as CHECKOUT_PENDING, never
                # ACTIVE.  The runtime resolver excludes CHECKOUT_PENDING intentionally;
                # activation happens only via subscription_activator after a real payment.
                v2 = SubscriptionV2.objects.create(
                    business=business,
                    service_type=service_type,
                    plan_code=v2_plan_code,
                    provider=SubscriptionV2.Provider.MERCADOPAGO,
                    external_reference=f"SUB-{uuid.uuid4()}",
                    status=SubscriptionV2.Status.CHECKOUT_PENDING,
                    price_snapshot=price_snap if isinstance(price_snap, dict) else {},
                )
                logger.info(
                    "[BillingViewSet.subscribe] Created SubscriptionV2 %s for "
                    "business=%s service=%s plan=%s sub_created=%s",
                    v2.pk, business.pk, service_type, v2_plan_code, created,
                )
            else:
                logger.info(
                    "[BillingViewSet.subscribe] SubscriptionV2 already exists: %s "
                    "for business=%s service=%s status=%s (no duplicate created)",
                    v2.pk, business.pk, service_type, v2.status,
                )
        except Exception as _exc:
            logger.warning(
                "[BillingViewSet.subscribe] SubscriptionV2 ensure failed (non-fatal): %s",
                _exc,
            )

        return Response(SubscriptionSerializer(sub).data)

    @action(detail=False, methods=['get'])
    def subscription(self, request):
        # request.business is set by HasBusinessMembership which runs first
        business = getattr(request, 'business', None)
        if not business:
            return Response({})
        try:
            sub = Subscription.objects.get(business=business)
            return Response(SubscriptionSerializer(sub).data)
        except Subscription.DoesNotExist:
             return Response({})

class StartSubscriptionView(APIView):
    """
    POST /billing/start-subscription

    Idempotent signup + subscription checkout.

    Idempotency contract
    --------------------
    If the same user+plan already has an open MpCheckoutSession (not expired),
    the same init_point is returned and NO new MP plan is created.
    This handles double-click, browser refresh, and frontend retries safely.

    Signup path (new users)
    -----------------------
    Creates user + business + legacy Subscription records for backward compat,
    then delegates to checkout_session_service for the MP plan creation.

    Returning user path
    -------------------
    If the email is already registered, we look up the user's open checkout
    session for the requested plan and return it.  No new user/business created.

    Response
    --------
    {
        "checkout_session_id": "<uuid>",
        "init_point": "<url>",
        "status": "checkout_created",
        "reused": false
    }

    The frontend MUST poll GET /billing/checkout-sessions/<checkout_session_id>
    to determine if the subscription was activated.  The back_url redirect from
    MP is NOT sufficient confirmation.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from .checkout_session_service import start_checkout

        email         = (request.data.get('email') or '').strip()
        password      = request.data.get('password')
        business_name = (request.data.get('business_name') or '').strip()
        plan_code     = (request.data.get('plan_code') or '').strip()
        raw_service   = (request.data.get('service') or '').strip()

        if not all([email, password, business_name, plan_code]):
            return Response({'error': 'Missing required fields'}, status=400)

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')

        # ── Case 1: returning user with an existing open session ──────────────
        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            try:
                plan = Plan.objects.get(code=plan_code, plan_status='active')
            except Plan.DoesNotExist:
                return Response({'error': 'Invalid plan code'}, status=400)

            # Try to find or create a checkout session for this user+plan.
            try:
                result = start_checkout(
                    user=existing_user,
                    tenant=_get_first_tenant(existing_user),
                    plan_code=plan_code,
                    frontend_url=frontend_url,
                )
                logger.info(
                    "[StartSubscriptionView] Returning user path user=%s plan=%s reused=%s session=%s",
                    existing_user.pk, plan_code, result.get('reused'), result.get('checkout_session_id'),
                )
                return Response(result, status=200)
            except ValueError as e:
                return Response({'error': str(e)}, status=400)
            except Exception as e:
                logger.exception("[StartSubscriptionView] start_checkout failed for existing user: %s", e)
                return Response({'error': str(e)}, status=500)

        # ── Case 2: new user signup ────────────────────────────────────────────
        try:
            plan = Plan.objects.get(code=plan_code, plan_status='active')
        except Plan.DoesNotExist:
            return Response({'error': 'Invalid plan code'}, status=400)

        allowed_services = {choice[0] for choice in Business.SERVICE_CHOICES}
        service = raw_service or None
        if service is None:
            plan_service = (plan.features_json or {}).get('service') if isinstance(plan.features_json, dict) else None
            if plan_service in allowed_services:
                service = plan_service
        if service is None:
            service = 'gestion'
        if service not in allowed_services:
            return Response({'error': 'Invalid service'}, status=400)

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email, password=password, username=email,
                )
                business = Business.objects.create(
                    name=business_name,
                    # BIRTH PATH: use canonical 'onboarding' status, not 'active' or
                    # deprecated 'pending_activation'.  Business becomes 'active' only
                    # after subscription_activator confirms a real payment.
                    status='onboarding',
                    default_service=service,
                )
                # BIRTH PATH: NO legacy Subscription is created here.
                # A Subscription with status='active' before checkout completes is a
                # phantom subscription that grants free access without real billing.
                # The canonical path: MpCheckoutSession → SubscriptionV2 → activation.
                #
                # TODO (legacy-compat): If downstream systems require a legacy
                # Subscription row before activation, create it with status='canceled'
                # here and promote it in subscription_activator.  For now, omit it
                # entirely — the runtime resolver handles the source='none' case.
                #
                # Legacy SubscriptionIntent kept for backward compatibility with
                # any external system that polls intent status.
                intent = SubscriptionIntent.objects.create(
                    tenant=business,
                    user=user,
                    plan_code=plan_code,
                    status='created',
                )

            # ── Create idempotent checkout session (outside the inner txn for clarity)
            result = start_checkout(
                user=user,
                tenant=business,
                plan_code=plan_code,
                frontend_url=frontend_url,
            )

            # Back-fill the legacy intent with the init_point for API compat.
            try:
                intent.mp_init_point = result.get('init_point')
                intent.save(update_fields=['mp_init_point'])
            except Exception:
                pass  # Non-fatal; legacy field only.

            logger.info(
                "[StartSubscriptionView] New user signup user=%s business=%s plan=%s session=%s",
                user.pk, business.pk, plan_code, result.get('checkout_session_id'),
            )
            return Response(result, status=201)

        except Exception as e:
            logger.exception("[StartSubscriptionView] Signup failed: %s", e)
            return Response({'error': str(e)}, status=500)


def _get_first_tenant(user):
    """Return the first business the user belongs to, or None."""
    from apps.accounts.models import Membership
    membership = Membership.objects.filter(user=user).select_related('business').first()
    return membership.business if membership else None


class CheckoutSessionStatusView(APIView):
    """
    GET /billing/checkout-sessions/<session_id>

    Frontend polling endpoint.  Returns the current state of a checkout session
    so the return page can show the right message WITHOUT trusting the MP redirect.

    Response shape::

        {
            "checkout_session_id": "...",
            "status": "created|checkout_created|awaiting_webhook|linked|activated|failed|expired",
            "catalog_plan": {"code": "...", "name": "...", "amount": ...},
            "subscription": {
                "provider_subscription_id": "...",
                "provider_status": "...",
                "is_active": true/false
            } | null,
            "last_payment": {
                "provider_authorized_payment_id": "...",
                "provider_status": "...",
                "amount": ...
            } | null
        }
    """
    permission_classes = [AllowAny]

    def get(self, request, session_id):
        from .models import BillingInvoiceEvent, MpCheckoutSession

        try:
            session = (
                MpCheckoutSession.objects
                .select_related('plan', 'tenant')
                .prefetch_related('subscriptions')
                .get(id=session_id)
            )
        except MpCheckoutSession.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)

        # Subscription (latest non-canceled).
        sub = session.subscriptions.exclude(
            status=SubscriptionV2.Status.CANCELED
        ).order_by('-created_at').first()

        sub_data = None
        if sub:
            sub_data = {
                'provider_subscription_id': sub.provider_sub_id or '',
                'provider_status': sub.status,
                'is_active': sub.is_active,
            }

        # Last authorized payment.
        last_payment = None
        if sub:
            invoice = (
                BillingInvoiceEvent.objects
                .filter(subscription=sub)
                .order_by('-paid_at', '-created_at')
                .first()
            )
            if invoice:
                last_payment = {
                    'provider_authorized_payment_id': invoice.provider_authorized_payment_id,
                    'provider_status': invoice.provider_status,
                    'amount': str(invoice.amount),
                }

        return Response({
            'checkout_session_id': str(session.id),
            'status': session.status,
            'catalog_plan': {
                'code': session.plan.code,
                'name': session.plan.name,
                'amount': str(session.plan.price),
            },
            'subscription': sub_data,
            'last_payment': last_payment,
        })



class IntentStatusView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        intent_id = request.query_params.get('intent_id')
        if not intent_id:
            return Response({'error': 'intent_id required'}, status=400)
            
        try:
            intent = SubscriptionIntent.objects.get(pk=intent_id)
            is_active = (intent.tenant.status == 'active')
                
            return Response({
                'status': intent.status,
                'active': is_active,
                'tenant_id': intent.tenant.id if is_active else None
            })
        except SubscriptionIntent.DoesNotExist:
             return Response({'error': 'Not found'}, status=404)

class MercadoPagoWebhookView(APIView):
    """
    POST /billing/mercadopago/webhook

    Phase 3 robust webhook handler.

    Every inbound call is persisted as a WebhookDelivery BEFORE any business
    logic runs.  Duplicate detection uses x-request-id + payload hash.
    Signature is verified via HMAC-SHA256 (MP_WEBHOOK_SECRET env var).

    Routing by topic:
      - subscription_preapproval      → webhook_processor handles (Phase 3)
      - subscription_authorized_payment → webhook_processor handles (Phase 3)
      - payment                        → legacy process_payment_event (plan changes, addons, tips)

    Activation rule (STRICT):
      Tenants are NEVER activated from:
        - the MP redirect / back_url
        - the subscription_preapproval webhook alone
      Activation happens ONLY when subscription_authorized_payment is received
      AND the server-to-server fetch from MP confirms status='authorized'.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from .webhook_processor import receive_webhook, dispatch_webhook
        from .models import WebhookDelivery

        topic     = request.data.get('type', '')
        data_id   = str(request.data.get('data', {}).get('id', ''))

        # ── Step 1: Persist delivery and verify signature ─────────────────────
        delivery, sig_valid = receive_webhook(request)

        # Respond 200 immediately for duplicates (idempotent).
        if delivery.processing_status == WebhookDelivery.ProcessingStatus.DUPLICATED:
            return Response(status=200)

        # Reject bad signatures only when MP_WEBHOOK_SECRET is configured.
        if not sig_valid:
            return Response({'detail': 'Invalid signature'}, status=400)

        logger.info(
            "[MPWebhook] delivery=%s topic=%s resource_id=%s x_request_id=%s",
            delivery.id, topic, delivery.resource_id, delivery.x_request_id,
        )

        # ── Step 2: Phase 3 topics (subscription_preapproval / authorized_payment)
        if topic in ('subscription_preapproval', 'subscription_authorized_payment'):
            dispatch_webhook(delivery)
            # Also write legacy BillingEvent for backward compat.
            self._write_legacy_billing_event(request, data_id, topic)
            return Response(status=200)

        # ── Step 3: Legacy topics (payment / tips / addon payments) ───────────
        # These still go through the legacy handlers, which also create BillingEvent.
        _be = self._write_legacy_billing_event(request, data_id, topic)

        if topic == 'payment':
            self.process_payment_event(data_id, billing_event=_be)
        else:
            delivery.processing_status = WebhookDelivery.ProcessingStatus.IGNORED
            delivery.processed_at = timezone.now()
            delivery.save(update_fields=['processing_status', 'processed_at'])
            logger.info("[MPWebhook] Unhandled topic=%s delivery=%s", topic, delivery.id)

        return Response(status=200)

    # ── Legacy helpers (kept for payment / tip / addon flows) ─────────────────

    def _write_legacy_billing_event(self, request, data_id, topic):
        """Write the legacy BillingEvent + PaymentEvent for backward compat."""
        event_id = request.headers.get('x-request-id') or data_id
        if not event_id:
            return None

        # Legacy PaymentEvent.
        if not PaymentEvent.objects.filter(event_id=str(event_id)).exists():
            try:
                PaymentEvent.objects.create(
                    provider='mercadopago',
                    event_id=str(event_id),
                    resource_id=str(data_id) if data_id else '',
                    payload_json=request.data,
                )
            except Exception:
                pass

        # Phase 2A BillingEvent.
        _event_type = (
            BillingEvent.EventType.PREAPPROVAL_UPDATED
            if topic == 'subscription_preapproval'
            else BillingEvent.EventType.UNKNOWN
        )
        try:
            _be, _ = BillingEvent.objects.get_or_create(
                provider_event_id=str(event_id),
                defaults={
                    'provider': BillingEvent.Provider.MERCADOPAGO,
                    'event_type': _event_type,
                    'payload': request.data,
                    'status': BillingEvent.ProcessingStatus.RECEIVED,
                    'received_at': timezone.now(),
                },
            )
            return _be
        except Exception as exc:
            logger.warning("[MPWebhook] BillingEvent persist failed: %s", exc)
            return None

    def process_payment_event(self, payment_id, billing_event=None):
        """Process one-time payments (for subscription changes and addon purchases)."""
        if not payment_id:
            return

        from apps.billing.models import PendingSubscriptionChange
        from apps.billing.services.commercial.apply import apply_subscription_change, apply_addon_activation
        from apps.billing.reviews_views import apply_reviews_plan_upgrade

        mp_service = MercadoPagoService()

        try:
            payment_data = mp_service.get_payment(payment_id)
            if not payment_data:
                return

            external_reference = payment_data.get('external_reference')
            payment_status = payment_data.get('status')

            if not external_reference:
                return

            is_subscription_change = external_reference.startswith('subscription_change_')
            is_addon_purchase       = external_reference.startswith('addon_purchase_')
            is_reviews_upgrade      = external_reference.startswith('reviews_upgrade_')
            is_tip                  = external_reference.startswith('TIP-')

            if is_tip:
                self.process_tip_payment(external_reference, payment_status, payment_id)
                return

            if not (is_subscription_change or is_addon_purchase or is_reviews_upgrade):
                return

            pending_change_id = external_reference.split('_')[-1]
            try:
                pending_change = PendingSubscriptionChange.objects.get(id=pending_change_id)
            except PendingSubscriptionChange.DoesNotExist:
                logger.warning("[MPWebhook] PendingSubscriptionChange %s not found", pending_change_id)
                return

            pending_change.mp_payment_id = str(payment_id)

            if payment_status == 'approved':
                pending_change.status = 'processing'
                pending_change.save()
                try:
                    if is_addon_purchase:
                        addon_codes = [k for k, v in pending_change.config_snapshot.items() if v is True]
                        if addon_codes:
                            apply_addon_activation(
                                business=pending_change.business,
                                addon_code=addon_codes[0],
                            )
                        else:
                            raise ValueError("No addon code found in config_snapshot")
                    elif is_reviews_upgrade:
                        apply_reviews_plan_upgrade(
                            business=pending_change.business,
                            target_plan_code=pending_change.target_plan_code,
                        )
                    else:
                        apply_subscription_change(
                            business=pending_change.business,
                            target_plan_code=pending_change.target_plan_code,
                            billing_cycle=pending_change.billing_cycle,
                            config=pending_change.config_snapshot,
                        )
                    pending_change.status = 'completed'
                    pending_change.applied_at = timezone.now()
                    pending_change.save()
                    try:
                        biz = pending_change.business
                        svc = 'qr_reviews' if is_reviews_upgrade else biz.default_service
                        v2 = _resolve_subscriptionv2(biz, svc)
                        _create_payment_attempt(v2, billing_event, payment_data, payment_id)
                        if v2:
                            _update_billing_event(billing_event, sub_v2=v2,
                                                  new_status=BillingEvent.ProcessingStatus.PROCESSED)
                    except Exception as exc:
                        logger.warning("[process_payment_event] PaymentAttempt update failed: %s", exc)
                except Exception as e:
                    pending_change.status = 'failed'
                    pending_change.save()
                    _update_billing_event(billing_event, new_status=BillingEvent.ProcessingStatus.ERROR,
                                          error_message=str(e))
                    logger.error("[MPWebhook] Error applying change %s: %s", pending_change_id, e)

            elif payment_status in ['rejected', 'cancelled']:
                pending_change.status = 'failed'
                pending_change.save()
                try:
                    biz = pending_change.business
                    v2 = _resolve_subscriptionv2(biz, biz.default_service)
                    _create_payment_attempt(v2, billing_event, payment_data, payment_id)
                    _update_billing_event(billing_event, sub_v2=v2,
                                          new_status=BillingEvent.ProcessingStatus.PROCESSED)
                except Exception as exc:
                    logger.warning("[process_payment_event] PaymentAttempt (rejected) failed: %s", exc)
            else:
                pending_change.save()

        except Exception as e:
            logger.error("[MPWebhook] Error processing payment event %s: %s", payment_id, e)

    def process_tip_payment(self, external_reference: str, payment_status: str, payment_id):
        """Idempotently update a TipTransaction from an MP payment webhook."""
        from apps.menu.models import TipTransaction
        try:
            tip = TipTransaction.objects.get(external_reference=external_reference)
        except TipTransaction.DoesNotExist:
            logger.warning("[TipWebhook] TipTransaction not found for ref %s", external_reference)
            return

        status_map = {
            'approved': 'approved', 'authorized': 'approved',
            'rejected': 'rejected', 'cancelled': 'cancelled',
            'pending': 'pending',   'in_process': 'pending',
        }
        new_status = status_map.get(payment_status, tip.status)
        update_fields = ['updated_at']
        if tip.status != new_status:
            tip.status = new_status
            update_fields.append('status')
        if payment_id and not tip.mp_payment_id:
            tip.mp_payment_id = str(payment_id)
            update_fields.append('mp_payment_id')
        tip.save(update_fields=update_fields)
        logger.info("[TipWebhook] %s → %s (mp_payment_id=%s)", external_reference, new_status, payment_id)


# ---------------------------------------------------------------------------
# DEV: Mercado Pago diagnostics ping (never expose tokens in response)
# ---------------------------------------------------------------------------

_MP_PLACEHOLDER_PATTERNS = ('xxxx', 'placeholder', 'your_token', 'changeme', 'APP_USR-0000', 'TEST-0000')



def _is_placeholder(value: str | None) -> bool:
    """Return True if the value looks like a template placeholder, not a real credential."""
    if not value:
        return False
    lower = value.lower()
    return any(p in lower for p in _MP_PLACEHOLDER_PATTERNS)


class DevMercadoPagoPingView(APIView):
    """
    GET /api/v1/billing/dev/mercadopago/ping
    GET /api/v1/billing/dev/mp/status   (alias)
    Quick health-check for MP credentials. Returns diagnostic info without
    exposing the access token. Only available when DJANGO_DEBUG=True.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        if not getattr(settings, 'DEBUG', False):
            return Response({'detail': 'Not available in production.'}, status=403)

        access_token = getattr(settings, 'MP_ACCESS_TOKEN', None)
        webhook_secret = getattr(settings, 'MP_WEBHOOK_SECRET', None)
        # BASE_PUBLIC_URL = API server public URL (for notification_url / webhooks)
        # PUBLIC_MENU_BASE_URL / FRONTEND_URL = frontend public URL (for back_urls)
        api_public_url = getattr(settings, 'BASE_PUBLIC_URL', None)
        frontend_public_url = (
            getattr(settings, 'PUBLIC_MENU_BASE_URL', None)
            or getattr(settings, 'FRONTEND_URL', None)
        )
        # Use api_public_url for the rest of this view's display
        base_public_url = api_public_url or frontend_public_url

        warnings: list[str] = []

        token_is_placeholder = _is_placeholder(access_token)
        if token_is_placeholder:
            warnings.append('MP_ACCESS_TOKEN looks like a placeholder. Paste a real TEST token from mercadopago.com → Credenciales de prueba.')
        if not access_token:
            warnings.append('MP_ACCESS_TOKEN is not set. The tip create-preference endpoint will return 503.')

        api_url_is_placeholder = _is_placeholder(api_public_url)
        if api_url_is_placeholder:
            warnings.append(
                'BASE_PUBLIC_URL looks like a placeholder. '
                'Run `ngrok http 8000`, copy the HTTPS URL, set BASE_PUBLIC_URL=https://xxxx.ngrok-free.app in services/api/.env, '
                'and restart the API container.'
            )
        if not api_public_url or api_url_is_placeholder:
            warnings.append('MP webhook notifications and back_urls will NOT work correctly without a valid BASE_PUBLIC_URL.')

        if not webhook_secret:
            warnings.append('MP_WEBHOOK_SECRET is not set. Webhook signature verification is disabled (DEV bypass active).')
        elif _is_placeholder(webhook_secret):
            warnings.append('MP_WEBHOOK_SECRET looks like a placeholder. Set the same value you configure in the MP Webhooks panel.')

        result: dict = {
            'mp_access_token_set': bool(access_token) and not token_is_placeholder,
            'mp_access_token_placeholder': token_is_placeholder,
            'mp_access_token_prefix': (access_token[:15] + '…') if access_token else None,
            'mp_webhook_secret_set': bool(webhook_secret) and not _is_placeholder(webhook_secret),
            # API public URL — used for notification_url (must reach Django port 8000 via ngrok)
            'api_public_url': api_public_url if not api_url_is_placeholder else f'PLACEHOLDER: {api_public_url}',
            'api_public_url_valid': bool(api_public_url) and not api_url_is_placeholder,
            'webhook_url': f"{api_public_url.rstrip('/')}/api/v1/billing/mercadopago/webhook" if (api_public_url and not api_url_is_placeholder) else '(not set — set BASE_PUBLIC_URL to your ngrok URL)',
            # Frontend public URL — used for back_urls (user browser redirect after payment)
            'frontend_public_url': frontend_public_url,
            'mp_client_id_set': bool(getattr(settings, 'MP_CLIENT_ID', None)),
        }

        # Try a live MP API call — use payment search (very cheap, verifies auth)
        mp_reachable = False
        mp_error = None
        if access_token and not token_is_placeholder:
            try:
                from .mp_service import MercadoPagoService
                sdk = MercadoPagoService().sdk
                # GET /v1/payments/search with limit=1 — works with any valid token
                resp = sdk.payment().search({"limit": 1, "offset": 0})
                mp_reachable = resp.get('status') == 200
                if not mp_reachable:
                    mp_error = (
                        f"MP API returned {resp.get('status')}: "
                        f"{resp.get('response', {}).get('message', str(resp.get('response', '')))}"
                    )
            except Exception as exc:
                mp_error = str(exc)
        elif token_is_placeholder:
            mp_error = 'Skipped live ping — token is a placeholder.'

        result['mp_api_reachable'] = mp_reachable
        if mp_error:
            result['mp_error'] = mp_error
        if warnings:
            result['warnings'] = warnings

        return Response(result)


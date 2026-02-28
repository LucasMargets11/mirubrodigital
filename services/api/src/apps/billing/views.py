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

from apps.accounts.access import resolve_request_membership
from apps.accounts.permissions import HasBusinessMembership
from apps.business.models import Business
from apps.accounts.models import Membership

from .models import Module, Bundle, Promotion, Subscription, Plan, SubscriptionIntent, PaymentEvent
from .serializers import (
    ModuleSerializer, BundleSerializer, PromotionSerializer, 
    QuoteRequestSerializer, SubscribeRequestSerializer, SubscriptionSerializer
)
from .services import PricingService
from .mp_service import MercadoPagoService

logger = logging.getLogger(__name__)
User = get_user_model()

class BillingViewSet(viewsets.ViewSet):
    # Default permission is strict, we override per action if needed
    permission_classes = [IsAuthenticated, HasBusinessMembership]

    def get_permissions(self):
        if self.action in ['modules', 'bundles', 'promotions', 'quote']:
            return [AllowAny()]
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
        vertical = vertical_map.get(business.default_service, 'commercial')
        
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
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        business_name = request.data.get('business_name')
        plan_code = request.data.get('plan_code')
        raw_service = (request.data.get('service') or '').strip()
        service = raw_service or None

        if not all([email, password, business_name, plan_code]):
            return Response({'error': 'Missing required fields'}, status=400)

        if User.objects.filter(email=email).exists():
            return Response({'error': 'Email already registered'}, status=400)
            
        try:
            plan = Plan.objects.get(code=plan_code)
        except Plan.DoesNotExist:
            return Response({'error': 'Invalid plan code'}, status=400)

        allowed_services = {choice[0] for choice in Business.SERVICE_CHOICES}
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
                user = User.objects.create_user(email=email, password=password, username=email)
                business = Business.objects.create(
                    name=business_name,
                    status='pending_activation',
                    default_service=service,
                )
                
                # Subscription
                subscription = Subscription.objects.create(
                    business=business,
                    plan=plan,
                    plan_type='bundle', # Setting default for compatibility
                    billing_period='monthly', # default
                    status='active',
                    service=service,
                )
                
                mp_service = MercadoPagoService()
                
                # Ensure Plan has preapproval_plan_id
                if not plan.mp_preapproval_plan_id:
                    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
                    back_url = f"{frontend_url}/subscribe/return"
                    
                    auto_recurring = {
                        "frequency": 1,
                        "frequency_type": "months",
                        "transaction_amount": float(plan.price),
                        "currency_id": "ARS"
                    }
                    if plan.interval == 'yearly':
                        auto_recurring['frequency'] = 12
                    
                    mp_plan = mp_service.create_preapproval_plan(
                        reason=f"Subscription to {plan.name}",
                        auto_recurring=auto_recurring,
                        back_url=back_url
                    )
                    plan.mp_preapproval_plan_id = mp_plan['id']
                    plan.save()

                # Create Intent
                intent = SubscriptionIntent.objects.create(
                    tenant=business,
                    user=user,
                    plan_code=plan_code,
                    status='created'
                )
                
                frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
                back_url = f"{frontend_url}/subscribe/return?intent_id={intent.id}"
                
                mp_response = mp_service.create_preapproval(
                    email=email,
                    plan_id=plan.mp_preapproval_plan_id,
                    external_reference=str(intent.id),
                    back_url=back_url
                )
                
                intent.mp_init_point = mp_response['init_point']
                intent.mp_preapproval_id = mp_response['id']
                intent.save()
                
                subscription.mp_preapproval_id = mp_response['id']
                subscription.save()

                return Response({
                    'init_point': intent.mp_init_point,
                    'intent_id': intent.pk
                })
        except Exception as e:
            return Response({'error': str(e)}, status=500)

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
    permission_classes = [AllowAny]

    def _verify_mp_signature(self, request) -> bool:
        """
        Verify the Mercado Pago webhook signature.
        Header format: x-signature: ts=<timestamp>,v1=<hmac_hex>
        Message: "id:<data.id>;request-id:<x-request-id>;ts:<timestamp>"
        Returns True if valid OR if MP_WEBHOOK_SECRET is not configured (DEV bypass).
        """
        secret = getattr(settings, 'MP_WEBHOOK_SECRET', None)
        if not secret:
            logger.warning("[MPWebhook] MP_WEBHOOK_SECRET not set — skipping signature verification (DEV mode)")
            return True

        x_signature = request.headers.get('x-signature', '')
        x_request_id = request.headers.get('x-request-id', '')

        # Parse ts and v1 from header
        ts = ''
        v1 = ''
        for part in x_signature.split(','):
            if part.startswith('ts='):
                ts = part[3:]
            elif part.startswith('v1='):
                v1 = part[3:]

        if not ts or not v1:
            logger.warning("[MPWebhook] x-signature header missing or malformed")
            return False

        data_id = request.data.get('data', {}).get('id', '')
        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts}"

        try:
            expected = hmac_lib.new(
                secret.encode('utf-8'),
                manifest.encode('utf-8'),
                hashlib.sha256,
            ).hexdigest()
        except Exception as exc:
            logger.error(f"[MPWebhook] HMAC computation error: {exc}")
            return False

        if not hmac_lib.compare_digest(expected, v1):
            logger.warning(f"[MPWebhook] Signature mismatch. manifest={manifest!r}")
            return False

        return True

    def post(self, request):
        # Verify MP signature (skipped in DEV when MP_WEBHOOK_SECRET is not set)
        if not self._verify_mp_signature(request):
            return Response({'detail': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        topic = request.data.get('type')
        data_id = request.data.get('data', {}).get('id')
        
        event_id = request.headers.get('x-request-id') or data_id
        if event_id and PaymentEvent.objects.filter(event_id=str(event_id)).exists():
             return Response(status=200)

        if event_id:
             PaymentEvent.objects.create(
                 provider='mercadopago',
                 event_id=str(event_id),
                 resource_id=str(data_id) if data_id else '',
                 payload_json=request.data
             )
        
        if topic == 'subscription_preapproval':
             self.process_subscription_event(data_id)
        elif topic == 'payment':
             self.process_payment_event(data_id)
        
        return Response(status=200)

    def process_payment_event(self, payment_id):
        """Process one-time payments (for subscription changes and addon purchases)."""
        if not payment_id:
            return
        
        from apps.billing.models import PendingSubscriptionChange
        from apps.billing.services.commercial.apply import apply_subscription_change, apply_addon_activation
        
        mp_service = MercadoPagoService()
        
        try:
            # Get payment details from MercadoPago
            payment = mp_service.sdk.payment().get(payment_id)
            if payment["status"] != 200:
                return
            
            payment_data = payment["response"]
            external_reference = payment_data.get('external_reference')
            payment_status = payment_data.get('status')
            
            if not external_reference:
                return
            
            # ── Route by external_reference prefix ──────────────────────
            is_subscription_change = external_reference.startswith('subscription_change_')
            is_addon_purchase = external_reference.startswith('addon_purchase_')
            is_tip = external_reference.startswith('TIP-')
            
            if is_tip:
                self.process_tip_payment(external_reference, payment_status, payment_id)
                return
            
            if not (is_subscription_change or is_addon_purchase):
                return
            
            # Extract pending_change_id
            pending_change_id = external_reference.split('_')[-1]
            
            try:
                pending_change = PendingSubscriptionChange.objects.get(id=pending_change_id)
            except PendingSubscriptionChange.DoesNotExist:
                logger.warning(f"PendingSubscriptionChange {pending_change_id} not found")
                return
            
            # Update pending change with payment info
            pending_change.mp_payment_id = str(payment_id)
            
            # If payment approved, apply the change
            if payment_status == 'approved':
                pending_change.status = 'processing'
                pending_change.save()
                
                try:
                    if is_addon_purchase:
                        # Extract addon code from config_snapshot
                        addon_codes = [key for key, value in pending_change.config_snapshot.items() if value is True]
                        
                        if addon_codes:
                            # Activate the addon
                            addon_code = addon_codes[0]  # Should only be one for addon purchases
                            apply_addon_activation(
                                business=pending_change.business,
                                addon_code=addon_code,
                            )
                        else:
                            raise ValueError("No addon code found in config_snapshot")
                    else:
                        # Standard subscription change
                        apply_subscription_change(
                            business=pending_change.business,
                            target_plan_code=pending_change.target_plan_code,
                            billing_cycle=pending_change.billing_cycle,
                            config=pending_change.config_snapshot,
                        )
                    
                    pending_change.status = 'completed'
                    pending_change.applied_at = timezone.now()
                    pending_change.save()
                    
                except Exception as e:
                    pending_change.status = 'failed'
                    pending_change.save()
                    logger.error(f"Error applying change {pending_change_id}: {e}")
            
            elif payment_status in ['rejected', 'cancelled']:
                pending_change.status = 'failed'
                pending_change.save()
            
            else:
                # pending, in_process, etc.
                pending_change.save()
        
        except Exception as e:
            logger.error(f"Error processing payment event {payment_id}: {e}")

    def process_tip_payment(self, external_reference: str, payment_status: str, payment_id):
        """Idempotently update a TipTransaction from an MP payment webhook."""
        from apps.menu.models import TipTransaction
        try:
            tip = TipTransaction.objects.get(external_reference=external_reference)
        except TipTransaction.DoesNotExist:
            logger.warning(f"[TipWebhook] TipTransaction not found for ref {external_reference}")
            return

        # Map MP statuses → TipTransaction statuses
        status_map = {
            'approved': 'approved',
            'authorized': 'approved',
            'rejected': 'rejected',
            'cancelled': 'cancelled',
            'pending': 'pending',
            'in_process': 'pending',
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
        logger.info(f"[TipWebhook] {external_reference} → {new_status} (mp_payment_id={payment_id})")

    def process_subscription_event(self, preapproval_id):
        if not preapproval_id:
            return

        mp_service = MercadoPagoService()
        preapproval = mp_service.get_preapproval(preapproval_id)
        
        if not preapproval:
            return

        external_reference = preapproval.get('external_reference')
        if not external_reference:
            return

        try:
            intent = SubscriptionIntent.objects.get(id=external_reference)
        except (SubscriptionIntent.DoesNotExist, ValueError):
            return

        status_val = preapproval.get('status')
        
        if status_val == 'authorized':
             self.activate_tenant(intent, preapproval_id)

    def activate_tenant(self, intent, preapproval_id):
        with transaction.atomic():
            ticket = intent.tenant
            if ticket.status != 'active':
                ticket.status = 'active'
                ticket.save()
            
            if intent.status != 'confirmed':
                intent.status = 'confirmed'
                intent.confirmed_at = timezone.now()
                intent.save()
            
            sub = Subscription.objects.filter(mp_preapproval_id=preapproval_id).first()
            if sub:
                sub.status = 'active'
                sub.save()
            
            Membership.objects.get_or_create(
                user=intent.user,
                business=intent.tenant,
                defaults={'role': 'owner'}
            )


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


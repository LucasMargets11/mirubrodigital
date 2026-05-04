"""
business/onboarding_views.py — Gestión Comercial embedded onboarding endpoints.

Endpoints (all under /api/v1/onboarding/gestion/):
  GET  context           — fetch wizard state and computed steps
  POST business-basics   — save business name / contact, advance step
  POST first-product     — atomic product + optional category + optional stock
  POST sales-setup       — apply commercial settings for starter plan
  POST skip-step         — mark a skippable step as skipped
  POST complete          — mark onboarding as completed
  POST dismiss           — dismiss banner/wizard without completing

Access: IsAuthenticated + HasBusinessMembership + role owner|admin
Rollout: NEW_ONBOARDING flag must be enabled; returns 503 otherwise.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.accounts.permissions import HasBusinessMembership
from apps.accounts.rollout import rollout
from apps.business.models import (
    Business,
    BusinessBillingProfile,
    BusinessOnboardingProgress,
    CommercialSettings,
    Subscription,
)
from apps.business.onboarding_serializers import (
    BusinessBasicsSerializer,
    FirstProductSerializer,
    OnboardingProgressSerializer,
    SkipStepSerializer,
)
from apps.catalog.models import Product, ProductCategory
from apps.inventory.services import ensure_stock_record, register_stock_movement
from apps.inventory.models import StockMovement
from apps.sales.models import Sale

logger = logging.getLogger(__name__)

# ── Step ordering ─────────────────────────────────────────────────────────────
STEP_ORDER = ['business_basics', 'first_product', 'sales_setup']

# Plans that behave like starter for the purpose of CommercialSettings defaults.
STARTER_PLAN_KEYS = {'starter', 'start'}

# The placeholder name assigned at registration — treated as "not yet set".
_NAME_PLACEHOLDERS = {'mi negocio', 'my business', 'negocio'}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_membership_role(request) -> str | None:
    """Return the role of the authenticated user for the current business."""
    membership: Membership | None = getattr(request, 'membership', None)
    if membership is not None:
        return membership.role
    business = getattr(request, 'business', None)
    if business is None:
        return None
    try:
        return Membership.objects.get(user=request.user, business=business).role
    except Membership.DoesNotExist:
        return None


def _check_rollout_and_role(request) -> Response | None:
    """
    Return a Response with an error if either:
      - the NEW_ONBOARDING rollout flag is disabled, or
      - the user's role is not owner/admin.
    Returns None if all checks pass.
    """
    if not rollout.is_enabled(rollout.NEW_ONBOARDING):
        return Response(
            {'detail': 'El onboarding asistido no está disponible en este momento.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    role = _get_membership_role(request)
    if role not in ('owner', 'admin'):
        return Response(
            {'detail': 'Solo propietarios y administradores pueden acceder al asistente de configuración.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _get_or_create_progress(business) -> BusinessOnboardingProgress:
    progress, _ = BusinessOnboardingProgress.objects.get_or_create(
        business=business,
        product_type='gestion',
        version='v1',
    )
    return progress


def _get_plan_code(business) -> str:
    """Return the canonical plan code for the business (lowercase)."""
    try:
        return (business.subscription.plan or 'starter').lower()
    except Subscription.DoesNotExist:
        return 'starter'


def _compute_step_status(
    step_id: str,
    progress: BusinessOnboardingProgress,
    products_count: int,
    commercial_settings: CommercialSettings,
    business: Business,
) -> str:
    skipped = progress.skipped_steps or []
    if step_id in skipped:
        return 'skipped'

    plan = _get_plan_code(business)

    if step_id == 'business_basics':
        name = (business.name or '').strip()
        try:
            trade_name = business.billing_profile.trade_name or ''
        except BusinessBillingProfile.DoesNotExist:
            trade_name = ''
        if trade_name.strip():
            return 'completed'
        if name and name.lower() not in _NAME_PLACEHOLDERS:
            return 'completed'
        return 'pending'

    if step_id == 'first_product':
        return 'completed' if products_count > 0 else 'pending'

    if step_id == 'sales_setup':
        if plan in STARTER_PLAN_KEYS:
            # Completed once block_sales flag is False (default is True → not ready)
            if not commercial_settings.block_sales_if_no_open_cash_session:
                return 'completed'
        else:
            # PRO/BUSINESS: no automatic action needed, consider completed
            return 'completed'
        return 'pending'

    return 'pending'


def _build_steps(
    progress: BusinessOnboardingProgress,
    products_count: int,
    commercial_settings: CommercialSettings,
    business: Business,
) -> list[dict]:
    return [
        {
            'id': 'business_basics',
            'status': _compute_step_status('business_basics', progress, products_count, commercial_settings, business),
            'required': True,
            'skippable': True,
        },
        {
            'id': 'first_product',
            'status': _compute_step_status('first_product', progress, products_count, commercial_settings, business),
            'required': False,
            'skippable': True,
        },
        {
            'id': 'sales_setup',
            'status': _compute_step_status('sales_setup', progress, products_count, commercial_settings, business),
            'required': False,
            'skippable': False,
        },
    ]


def _serialize_context(
    request,
    business: Business,
    progress: BusinessOnboardingProgress,
) -> dict:
    """Build the full context response dict."""
    plan_code = _get_plan_code(business)
    try:
        subscription = business.subscription
        is_trial = business.status == 'trialing'
        plan_name = subscription.get_plan_display()
    except Subscription.DoesNotExist:
        is_trial = False
        plan_name = plan_code.capitalize()

    # Entitlements subset
    try:
        from apps.business.entitlements import get_effective_entitlements
        entitlements = get_effective_entitlements(business.subscription)
    except Exception:
        entitlements = set()

    # Billing profile
    try:
        bp = business.billing_profile
        business_basics = {
            'name': business.name or '',
            'trade_name': bp.trade_name or '',
            'phone': bp.phone or '',
            'email': bp.email or '',
        }
    except BusinessBillingProfile.DoesNotExist:
        business_basics = {'name': business.name or '', 'trade_name': '', 'phone': '', 'email': ''}

    # Catalog counts
    products_count = Product.objects.filter(business=business).count()
    categories_count = ProductCategory.objects.filter(business=business).count()

    # Sales counts
    from django.db.models import Min, Count
    sales_agg = Sale.objects.filter(business=business).aggregate(
        sales_count=Count('id'),
        first_sale_at=Min('created_at'),
    )

    # CommercialSettings
    cs = CommercialSettings.objects.for_business(business)

    user_role = _get_membership_role(request) or 'viewer'

    steps = _build_steps(progress, products_count, cs, business)

    return {
        'business': {
            'id': business.id,
            'name': business.name,
            'status': business.status,
        },
        'plan': {
            'code': plan_code,
            'name': plan_name,
            'is_trial': is_trial,
        },
        'features': {
            'products': 'gestion.products' in entitlements,
            'inventory_basic': 'gestion.inventory_basic' in entitlements,
            'sales_basic': 'gestion.sales_basic' in entitlements,
            'settings_basic': 'gestion.settings_basic' in entitlements,
            'cash': 'gestion.cash' in entitlements,
            'customers': 'gestion.customers' in entitlements,
        },
        'user_role': user_role,
        'business_basics': business_basics,
        'catalog': {
            'products_count': products_count,
            'categories_count': categories_count,
        },
        'sales': {
            'sales_count': sales_agg['sales_count'],
            'first_sale_at': (
                sales_agg['first_sale_at'].isoformat() if sales_agg['first_sale_at'] else None
            ),
        },
        'commercial_settings': {
            'allow_sell_without_stock': cs.allow_sell_without_stock,
            'block_sales_if_no_open_cash_session': cs.block_sales_if_no_open_cash_session,
            'require_customer_for_sales': cs.require_customer_for_sales,
        },
        'progress': OnboardingProgressSerializer(progress).data,
        'steps': steps,
    }


# ── Views ─────────────────────────────────────────────────────────────────────

class GestionOnboardingContextView(APIView):
    """
    GET /api/v1/onboarding/gestion/context
    Returns the full onboarding context including computed step statuses.
    Creates a BusinessOnboardingProgress record on first access (lazy).
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]

    def get(self, request):
        error = _check_rollout_and_role(request)
        if error:
            return error

        business = request.business
        progress = _get_or_create_progress(business)
        return Response(_serialize_context(request, business, progress))


class GestionOnboardingBusinessBasicsView(APIView):
    """
    POST /api/v1/onboarding/gestion/business-basics
    Updates Business.name and BusinessBillingProfile.trade_name atomically.
    Advances current_step to 'first_product'.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]

    def post(self, request):
        error = _check_rollout_and_role(request)
        if error:
            return error

        serializer = BusinessBasicsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        business = request.business

        with transaction.atomic():
            # Update Business.name
            business.name = data['business_name']
            business.save(update_fields=['name', 'updated_at'])

            # Update billing profile
            bp, _ = BusinessBillingProfile.objects.get_or_create(business=business)
            bp.trade_name = data['business_name']
            if data.get('phone') is not None:
                bp.phone = data['phone'] or ''
            if data.get('email') is not None:
                bp.email = data['email'] or ''
            bp.save(update_fields=['trade_name', 'phone', 'email', 'updated_at'])

            # Advance progress
            progress = _get_or_create_progress(business)
            skipped = list(progress.skipped_steps or [])
            if 'business_basics' in skipped:
                skipped.remove('business_basics')
            progress.current_step = 'first_product'
            progress.skipped_steps = skipped
            progress.save(update_fields=['current_step', 'skipped_steps', 'updated_at'])

        return Response(_serialize_context(request, business, progress))


class GestionOnboardingFirstProductView(APIView):
    """
    POST /api/v1/onboarding/gestion/first-product
    Atomically creates: ProductCategory (if needed) + Product + StockMovement (if stock > 0).
    Advances current_step to 'sales_setup'.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]

    def post(self, request):
        error = _check_rollout_and_role(request)
        if error:
            return error

        serializer = FirstProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        business = request.business
        category = None
        movement = None

        with transaction.atomic():
            # ── Resolve category ──────────────────────────────────────────
            category_id = data.get('category_id')
            category_name = (data.get('category_name') or '').strip()

            if category_id:
                try:
                    category = ProductCategory.objects.get(pk=category_id, business=business)
                except ProductCategory.DoesNotExist:
                    return Response(
                        {'detail': 'La categoría seleccionada no existe en este negocio.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif category_name:
                category = (
                    ProductCategory.objects.filter(business=business, name__iexact=category_name)
                    .order_by('id')
                    .first()
                )
                if not category:
                    category = ProductCategory.objects.create(
                        business=business,
                        name=category_name,
                        is_active=True,
                    )

            # ── Create Product ────────────────────────────────────────────
            product = Product.objects.create(
                business=business,
                name=data['name'],
                price=data['price'],
                cost=data.get('cost') or Decimal('0'),
                category=category,
                is_active=True,
            )
            # Ensure stock record exists (quantity=0 by default)
            ensure_stock_record(business, product)

            # ── Create StockMovement if initial_stock > 0 ─────────────────
            initial_stock = data.get('initial_stock')
            if initial_stock is not None and initial_stock > Decimal('0'):
                movement, _ = register_stock_movement(
                    business=business,
                    product=product,
                    movement_type=StockMovement.MovementType.IN,
                    quantity=initial_stock,
                    note='Stock inicial — onboarding',
                    created_by=request.user,
                )

            # ── Advance progress ──────────────────────────────────────────
            progress = _get_or_create_progress(business)
            skipped = list(progress.skipped_steps or [])
            if 'first_product' in skipped:
                skipped.remove('first_product')
            progress.current_step = 'sales_setup'
            progress.skipped_steps = skipped
            progress.save(update_fields=['current_step', 'skipped_steps', 'updated_at'])

        # ── Build response ────────────────────────────────────────────────
        category_data = None
        if category:
            category_data = {'id': str(category.id), 'name': category.name}

        movement_data = None
        if movement:
            movement_data = {
                'id': str(movement.id),
                'quantity': str(movement.quantity),
                'movement_type': movement.movement_type,
            }

        return Response(
            {
                'product': {
                    'id': str(product.id),
                    'name': product.name,
                    'price': str(product.price),
                    'cost': str(product.cost),
                    'sku': product.sku,
                    'category': category_data,
                },
                'stock_movement': movement_data,
                **_serialize_context(request, business, progress),
            },
            status=status.HTTP_201_CREATED,
        )


class GestionOnboardingSalesSetupView(APIView):
    """
    POST /api/v1/onboarding/gestion/sales-setup
    For starter plan: applies safe CommercialSettings defaults so the user can
    register their first sale without needing to open a cash session.
    For PRO/BUSINESS: no-op (returns current settings; warns if potentially blocked).
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]

    def post(self, request):
        error = _check_rollout_and_role(request)
        if error:
            return error

        business = request.business
        plan = _get_plan_code(business)
        cs = CommercialSettings.objects.for_business(business)
        warning = None

        with transaction.atomic():
            if plan in STARTER_PLAN_KEYS:
                cs.block_sales_if_no_open_cash_session = False
                cs.allow_sell_without_stock = True
                cs.require_customer_for_sales = False
                cs.save(update_fields=[
                    'block_sales_if_no_open_cash_session',
                    'allow_sell_without_stock',
                    'require_customer_for_sales',
                    'updated_at',
                ])
            else:
                # PRO/BUSINESS: emit a warning if cash blocking is still on
                if cs.block_sales_if_no_open_cash_session:
                    warning = (
                        'Tu plan requiere abrir una sesión de caja antes de registrar ventas. '
                        'Podés cambiar esto en Ajustes > Configuración comercial.'
                    )

            progress = _get_or_create_progress(business)
            progress.current_step = ''
            progress.save(update_fields=['current_step', 'updated_at'])

        response_data = {
            'commercial_settings': {
                'allow_sell_without_stock': cs.allow_sell_without_stock,
                'block_sales_if_no_open_cash_session': cs.block_sales_if_no_open_cash_session,
                'require_customer_for_sales': cs.require_customer_for_sales,
            },
            'progress': OnboardingProgressSerializer(progress).data,
            'steps': _build_steps(
                progress,
                Product.objects.filter(business=business).count(),
                cs,
                business,
            ),
        }
        if warning:
            response_data['warning'] = warning

        return Response(response_data)


class GestionOnboardingSkipStepView(APIView):
    """
    POST /api/v1/onboarding/gestion/skip-step
    Marks a skippable step as skipped and advances current_step.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]

    def post(self, request):
        error = _check_rollout_and_role(request)
        if error:
            return error

        serializer = SkipStepSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        step_id = serializer.validated_data['step_id']

        business = request.business

        with transaction.atomic():
            progress = _get_or_create_progress(business)
            skipped = list(progress.skipped_steps or [])
            if step_id not in skipped:
                skipped.append(step_id)

            # Advance to next logical step
            try:
                current_idx = STEP_ORDER.index(step_id)
                next_step = STEP_ORDER[current_idx + 1] if current_idx + 1 < len(STEP_ORDER) else ''
            except ValueError:
                next_step = ''

            progress.skipped_steps = skipped
            progress.current_step = next_step
            progress.save(update_fields=['skipped_steps', 'current_step', 'updated_at'])

        products_count = Product.objects.filter(business=business).count()
        cs = CommercialSettings.objects.for_business(business)

        return Response({
            'progress': OnboardingProgressSerializer(progress).data,
            'steps': _build_steps(progress, products_count, cs, business),
        })


class GestionOnboardingCompleteView(APIView):
    """
    POST /api/v1/onboarding/gestion/complete
    Marks the onboarding as genuinely completed.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]

    def post(self, request):
        error = _check_rollout_and_role(request)
        if error:
            return error

        business = request.business

        with transaction.atomic():
            progress = _get_or_create_progress(business)
            progress.completed_at = timezone.now()
            progress.dismissed_at = None  # clear any stale dismiss
            progress.current_step = ''
            progress.save(update_fields=['completed_at', 'dismissed_at', 'current_step', 'updated_at'])

        return Response(_serialize_context(request, business, progress))


class GestionOnboardingDismissView(APIView):
    """
    POST /api/v1/onboarding/gestion/dismiss
    Dismisses the banner/wizard without marking it as completed.
    The user can resume later.
    """
    permission_classes = [IsAuthenticated, HasBusinessMembership]

    def post(self, request):
        error = _check_rollout_and_role(request)
        if error:
            return error

        business = request.business

        with transaction.atomic():
            progress = _get_or_create_progress(business)
            progress.dismissed_at = timezone.now()
            # Do NOT touch completed_at or current_step
            progress.save(update_fields=['dismissed_at', 'updated_at'])

        return Response({'progress': OnboardingProgressSerializer(progress).data})

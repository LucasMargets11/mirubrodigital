"""
Gestión Comercial — Setup Center context view (Phase 1, read-only).

GET /api/v1/setup/gestion/context

Returns the current completion state of every setup task so the frontend
HelpModal can display real progress instead of hard-coded stubs.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasBusinessMembership
from apps.accounts.models import Membership
from apps.business.entitlements import get_effective_entitlements
from apps.business.models import (
    Business,
    BusinessBillingProfile,
    BusinessBranding,
    Subscription,
)
from apps.catalog.models import Product, ProductCategory
from apps.inventory.models import ProductStock
from apps.invoices.models import DocumentSeries
from apps.treasury.models import Account, TreasurySettings


# ── Plan tier helpers ─────────────────────────────────────────────────────────

# Canonical tier (0 = Starter, 1 = PRO, 2 = Business/Enterprise)
_PLAN_TIER: dict[str, int] = {
    'starter': 0,
    'start': 0,
    'pro': 1,
    'business': 2,
    'enterprise': 2,
    'plus': 2,
}

_PLAN_DISPLAY_NAME: dict[str, str] = {
    'starter': 'Starter',
    'start': 'Starter',
    'pro': 'Pro',
    'business': 'Business',
    'enterprise': 'Enterprise',
    'plus': 'Business',
}

# Names that are considered "still a placeholder" — business_and_fiscal task
_PLACEHOLDER_NAMES: frozenset[str] = frozenset({
    'mi negocio',
    'mi empresa',
    'negocio',
    'demo',
    'test',
    'empresa',
    'nuevo negocio',
})


def _get_plan_code(business: Business) -> str:
    """Return the raw plan code (lowercase), defaulting to 'starter'."""
    try:
        return (business.subscription.plan or 'starter').lower()
    except Subscription.DoesNotExist:
        return 'starter'


def _tier(plan_code: str) -> int:
    return _PLAN_TIER.get(plan_code, 0)


# ── Task completion detectors ─────────────────────────────────────────────────

def _task_business_and_fiscal(business: Business) -> bool:
    name_ok = (
        business.name.strip().lower() not in _PLACEHOLDER_NAMES
        and len(business.name.strip()) > 2
    )
    if name_ok:
        return True
    # Fallback: billing profile has legal data
    try:
        bp = BusinessBillingProfile.objects.get(business=business)
        return bool(bp.legal_name or bp.trade_name)
    except BusinessBillingProfile.DoesNotExist:
        return False


def _task_branding(business: Business) -> bool:
    try:
        branding = business.branding
        return bool(branding.logo_horizontal or branding.logo_square)
    except BusinessBranding.DoesNotExist:
        return False


def _task_categories(business: Business) -> bool:
    return ProductCategory.objects.filter(business=business).exists()


def _task_products(business: Business) -> bool:
    return Product.objects.filter(business=business).exists()


def _task_initial_stock(business: Business) -> bool:
    return ProductStock.objects.filter(business=business, quantity__gt=0).exists()


def _task_treasury_accounts(business: Business) -> bool:
    return Account.objects.filter(business=business, is_active=True).exists()


def _task_cash_link(business: Business) -> bool:
    try:
        ts = business.treasury_settings
        return ts.default_cash_account_id is not None
    except TreasurySettings.DoesNotExist:
        return False


def _task_document_series(business: Business) -> bool:
    return DocumentSeries.objects.filter(business=business).exists()


def _task_team(business: Business) -> bool:
    return Membership.objects.filter(business=business).count() > 1


def _task_branches(business: Business) -> bool:
    return business.branches.exists()


# ── Ordered step definitions ──────────────────────────────────────────────────

# (step_id_suffix, min_tier, completion_fn)
# step_id_suffix will be prefixed with 'gestion.' in the response
_STEPS: list[tuple[str, int, callable]] = [
    ('business_and_fiscal', 0, _task_business_and_fiscal),
    ('branding',            0, _task_branding),
    ('categories',          0, _task_categories),
    ('products',            0, _task_products),
    ('initial_stock',       0, _task_initial_stock),
    ('treasury_accounts',   1, _task_treasury_accounts),
    ('cash_link',           1, _task_cash_link),
    ('document_series',     1, _task_document_series),
    ('team',                1, _task_team),
    ('branches',            2, _task_branches),
]


# ── View ──────────────────────────────────────────────────────────────────────

class GestionSetupContextView(APIView):
    """
    Returns the setup context for the Gestión Comercial Setup Center.

    All authenticated business members may call this endpoint regardless of
    their role — it is read-only and contains no sensitive data.
    """

    permission_classes = [IsAuthenticated, HasBusinessMembership]

    def get(self, request: Request) -> Response:
        business: Business = request.business

        plan_code = _get_plan_code(business)
        plan_tier = _tier(plan_code)

        # ── Effective entitlements (plan + add-ons) ───────────────────────
        try:
            effective = get_effective_entitlements(business.subscription)
        except Subscription.DoesNotExist:
            effective = set()

        features = {
            'products':        'gestion.products'        in effective,
            'inventory_basic': 'gestion.inventory_basic' in effective,
            'sales_basic':     'gestion.sales_basic'     in effective,
            'settings_basic':  'gestion.settings_basic'  in effective,
            'cash':            'gestion.cash'            in effective,
            'treasury':        'gestion.treasury'        in effective,
            'invoices':        'gestion.invoices'        in effective,
            'rbac_full':       'gestion.rbac_full'       in effective,
            'multi_branch':    'gestion.multi_branch'    in effective,
            'tax_backup':      'gestion.tax_backup'      in effective,
        }

        # ── Compute task statuses ─────────────────────────────────────────
        tasks: dict[str, dict] = {}
        status_map: dict[str, str] = {}
        completed_count = 0
        total_count = 0

        for suffix, min_tier, detector_fn in _STEPS:
            step_id = f'gestion.{suffix}'

            if plan_tier < min_tier:
                # Step not available on this plan
                tasks[step_id] = {'status': 'upgrade', 'detail': {}}
                status_map[step_id] = 'pending'
                continue

            total_count += 1
            try:
                is_done = detector_fn(business)
            except Exception:
                # Defensive: if a detector raises, treat as pending
                is_done = False

            step_status = 'completed' if is_done else 'pending'
            if is_done:
                completed_count += 1

            tasks[step_id] = {'status': step_status, 'detail': {}}
            status_map[step_id] = step_status

        return Response({
            'plan': {
                'code': plan_code,
                'name': _PLAN_DISPLAY_NAME.get(plan_code, plan_code.title()),
            },
            'features': features,
            'tasks': tasks,
            'progress': {
                'completed': completed_count,
                'total': total_count,
            },
            'status_map': status_map,
        })

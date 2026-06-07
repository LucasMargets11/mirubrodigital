"""
sales/pos_offline_views.py — POS Offline bootstrap snapshot endpoint.

Route:
  GET /api/v1/pos/offline/bootstrap/

Auth: EmployeeTokenAuthentication + PinChangeNotRequired
Capability: none beyond an authenticated, pin-cleared employee (same bar as the
catalog browse endpoint). The snapshot only exposes data the POS already reads
online (products, categories, settings); it never returns secrets.

Purpose (PR-OFF-02A)
--------------------
Deliver a minimal, business-scoped snapshot the future offline contingency mode
(quick-sale only) will download and cache locally. This PR is backend-only:
there is NO IndexedDB, no offline capture and no sync here — just the read API.

Scope guarantees
----------------
- Strictly single-business: every queryset is filtered by ``request.business``.
- Quick-sale only: the offline policy advertises supports_kitchen/tables/orders
  as False even when those features are enabled online.
- No sensitive data: no PINs, tokens, passwords, fiscal data, customers, sales
  history, orders, tables or kitchen state.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import EmployeeTokenAuthentication
from apps.accounts.permissions import EmployeeIsAuthenticated, PinChangeNotRequired
from apps.business.entitlements import has_pos_offline_contingency_access
from apps.business.models import CommercialSettings
from apps.cash.models import CashSession
from apps.catalog.models import Product, ProductCategory
from apps.inventory.models import ProductStock
from apps.resto.models import RestaurantOperationSettings

logger = logging.getLogger(__name__)

# Current shape version of the bootstrap payload. Bump when the structure changes
# so offline clients can invalidate stale caches.
BOOTSTRAP_VERSION = 1

# How long an offline snapshot is considered usable before the client should
# refuse to keep operating offline. Hardcoded for the MVP.
OFFLINE_EXPIRES_IN_HOURS = 24

# Static POS payment methods. Mirrors sales.Sale.PaymentMethod choices. The
# system has no per-business configurable payment-method model yet, so this is
# the canonical list compatible with the current POS sale endpoint.
POS_PAYMENT_METHODS = [
    {'code': 'cash', 'label': 'Efectivo'},
    {'code': 'transfer', 'label': 'Transferencia'},
    {'code': 'card', 'label': 'Tarjeta'},
    {'code': 'other', 'label': 'Otro'},
]


def _decimal_str(value: Decimal | int | float | None) -> str:
    """Serialise a Decimal-ish value as a plain string (never None)."""
    if value is None:
        return '0'
    return str(value)


class PosOfflineBootstrapView(APIView):
    """
    GET /api/v1/pos/offline/bootstrap/

    Returns the minimal offline snapshot for the authenticated employee's
    business. See module docstring for scope and security guarantees.

    Response 200
    ------------
    {
        "bootstrap_version": 1,
        "generated_at": "...",
        "business": {...},
        "employee": {...},
        "offline_policy": {...},
        "commercial_settings": {...},
        "operation_settings": {...},
        "cash_session": {...} | null,
        "categories": [...],
        "products": [...],
        "payment_methods": [...]
    }

    Errors
    ------
    401/403 → missing / invalid employee token (handled by auth + permissions)
    """

    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def get(self, request) -> Response:
        employee = request.employee
        business = request.business

        payload = {
            'bootstrap_version': BOOTSTRAP_VERSION,
            'generated_at': timezone.now().isoformat(),
            'business': self._business_block(business),
            'employee': self._employee_block(employee),
            'offline_policy': self._offline_policy_block(business),
            'commercial_settings': self._commercial_settings_block(business),
            'operation_settings': self._operation_settings_block(business),
            'cash_session': self._cash_session_block(employee, business),
            'categories': self._categories_block(business),
            'products': self._products_block(business),
            'payment_methods': POS_PAYMENT_METHODS,
        }
        return Response(payload)

    # ── Blocks ──────────────────────────────────────────────────────────────

    def _business_block(self, business) -> dict:
        return {
            'id': str(business.pk),
            'name': business.name,
            'currency': business.currency,
            'default_service': business.service_type or business.default_service,
            'timezone': business.timezone,
        }

    def _employee_block(self, employee) -> dict:
        display_name = (
            employee.alias
            or f'{employee.first_name} {employee.last_name}'.strip()
        )
        return {
            'id': str(employee.pk),
            'name': display_name,
            'role': employee.role_type,
            'code': employee.employee_code,
        }

    def _offline_policy_block(self, business) -> dict:
        # `enabled` is gated by the dedicated entitlement. When the business does
        # not have it, the snapshot is still returned but the client must NOT
        # enable offline operation. Quick-sale only for the MVP — kitchen, tables
        # and orders are explicitly unsupported offline even if enabled online.
        return {
            'enabled': has_pos_offline_contingency_access(business),
            'mode': 'quick_sale_only',
            'expires_in_hours': OFFLINE_EXPIRES_IN_HOURS,
            'supports_kitchen': False,
            'supports_tables': False,
            'supports_orders': False,
        }

    def _commercial_settings_block(self, business) -> dict:
        cs: CommercialSettings = CommercialSettings.objects.for_business(business)
        return {
            'allow_sell_without_stock': cs.allow_sell_without_stock,
            'block_sales_if_no_open_cash_session': cs.block_sales_if_no_open_cash_session,
            'require_customer_for_sales': cs.require_customer_for_sales,
        }

    def _operation_settings_block(self, business) -> dict:
        ops: RestaurantOperationSettings = (
            RestaurantOperationSettings.objects.for_business(business)
        )
        return {
            'pos_quick_sale_enabled': ops.pos_quick_sale_enabled,
            'kitchen_enabled': ops.kitchen_enabled,
            'tables_enabled': ops.tables_enabled,
            'counter_orders_enabled': ops.counter_orders_enabled,
        }

    def _cash_session_block(self, employee, business) -> dict | None:
        session = (
            CashSession.objects
            .filter(
                business=business,
                status=CashSession.Status.OPEN,
                opened_by_employee=employee,
            )
            .select_related('register')
            .first()
        )
        if session is None:
            return None
        return {
            'id': str(session.pk),
            'status': session.status,
            'opened_at': session.opened_at.isoformat() if session.opened_at else None,
            'register_name': session.register.name if session.register else None,
        }

    def _categories_block(self, business) -> list[dict]:
        categories = (
            ProductCategory.objects
            .filter(business=business, is_active=True)
            .order_by('name')
            .values('id', 'name', 'is_active')
        )
        return [
            {
                'id': str(row['id']),
                'name': row['name'],
                'is_active': row['is_active'],
            }
            for row in categories
        ]

    def _products_block(self, business) -> list[dict]:
        # Single stock query → {product_id: quantity} to avoid N+1.
        stock_map = {
            row['product_id']: row['quantity']
            for row in ProductStock.objects
            .filter(business=business)
            .values('product_id', 'quantity')
        }

        products = (
            Product.objects
            .filter(business=business, is_active=True)
            .order_by('name')
            .values(
                'id', 'name', 'sku', 'barcode',
                'category_id', 'price', 'stock_min', 'is_active',
            )
        )
        return [
            {
                'id': str(row['id']),
                'name': row['name'],
                'sku': row['sku'],
                'barcode': row['barcode'],
                'category_id': str(row['category_id']) if row['category_id'] else None,
                'price': _decimal_str(row['price']),
                'stock_min': _decimal_str(row['stock_min']),
                'current_stock': _decimal_str(stock_map.get(row['id'])),
                'is_active': row['is_active'],
            }
            for row in products
        ]

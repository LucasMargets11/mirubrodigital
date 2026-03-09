"""
sales/pos_serializers.py — POS employee-specific serializer for sale creation.

Reuses the full validation + stock logic from SaleCreateSerializer.

Differences from the admin serializer:
  - `cash_session_id` is NOT a client field — the view auto-injects
    context['cash_session'] from the employee's current open session.
  - `created_by` (auth.User FK) is intentionally left NULL.
  - `created_by_employee` is set from context['employee'] after super().create().
"""
from __future__ import annotations

from django.db import transaction

from .serializers import SaleCreateSerializer


class PosSaleCreateSerializer(SaleCreateSerializer):
    """
    POS-specific sale creation serializer.

    Expected context keys (injected by PosSaleCreateView):
        employee     : EmployeeProfile  — authenticated employee
        business     : Business         — employee.business (set by view)
        cash_session : CashSession|None — employee's open session or None

    What changes vs admin SaleCreateSerializer:
        - `cash_session_id` field removed; view injects context['cash_session'] directly.
        - `created_by` remains NULL (no auth.User in POS flows).
        - `created_by_employee` is patched onto the sale after super().create().

    What is fully reused (no duplication):
        - Customer validation (validate_customer_id)
        - Item/quantity/price validation
        - Stock availability checking
        - CommercialSettings guards (block_sales_if_no_open_cash_session, etc.)
        - Atomic create + SaleItem bulk_create + StockMovement registration
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove the client-facing field.  The view pre-fetches the open session
        # and injects it into context['cash_session'] before calling is_valid().
        self.fields.pop('cash_session_id', None)

    @transaction.atomic
    def create(self, validated_data):
        employee = self.context['employee']
        # super().create() uses context['business'] and context['cash_session'] as set by the view.
        # context.get('request') returns None → user = None → created_by=None.
        sale = super().create(validated_data)
        # Attach operative identity without touching admin FK.
        sale.created_by_employee = employee
        sale.save(update_fields=['created_by_employee'])
        return sale

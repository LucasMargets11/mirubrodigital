"""
Respaldo Impositivo — Application Services

Servicios explícitos para provisionar perfiles fiscales.
Se llaman desde los flujos de pago en treasury (no señales frágiles).
"""
from __future__ import annotations

import logging

from apps.treasury.models import Expense, FixedExpensePeriod

from .models import ExpenseFiscalProfile, SourceType

logger = logging.getLogger(__name__)


def ensure_fiscal_profile_for_expense(expense: Expense) -> ExpenseFiscalProfile | None:
    """
    Crea un ExpenseFiscalProfile para un gasto puntual PAGADO si no existe.
    Idempotente: si ya existe retorna el existente sin modificar.

    Se invoca desde ExpenseViewSet.pay() dentro del atomic block.
    Solo crea para gastos en estado PAID.
    """
    if expense.status != Expense.Status.PAID:
        return None

    profile, created = ExpenseFiscalProfile.objects.get_or_create(
        expense=expense,
        defaults={
            'business': expense.business,
            'source_type': SourceType.EXPENSE,
        },
    )

    if created:
        logger.info(
            "[tax_backup] Auto-created fiscal profile %s for expense %s (business=%s)",
            profile.pk, expense.pk, expense.business_id,
        )

    return profile


def ensure_fiscal_profile_for_fixed_expense_period(
    period: FixedExpensePeriod,
) -> ExpenseFiscalProfile | None:
    """
    Crea un ExpenseFiscalProfile para un período de gasto fijo PAGADO si no existe.
    Idempotente: si ya existe retorna el existente sin modificar.

    Se invoca desde FixedExpensePeriodViewSet.pay() dentro del atomic block.
    Solo crea para períodos en estado PAID.
    """
    if period.status != FixedExpensePeriod.Status.PAID:
        return None

    profile, created = ExpenseFiscalProfile.objects.get_or_create(
        fixed_expense_period=period,
        defaults={
            'business': period.fixed_expense.business,
            'source_type': SourceType.FIXED_EXPENSE_PERIOD,
        },
    )

    if created:
        logger.info(
            "[tax_backup] Auto-created fiscal profile %s for fixed_expense_period %s "
            "(fixed_expense=%s, business=%s)",
            profile.pk, period.pk,
            period.fixed_expense_id, period.fixed_expense.business_id,
        )

    return profile

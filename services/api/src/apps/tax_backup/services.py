"""
Respaldo Impositivo — Application Services

Servicios explícitos para provisionar perfiles fiscales.
Se llaman desde los flujos de pago en treasury (no señales frágiles).
"""
from __future__ import annotations

import logging

from apps.treasury.models import Expense, FixedExpensePeriod

from .models import ExpenseFiscalProfile, SourceType, TaxStatus, TaxStatusLog

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
        # Sprint 4: initial fiscal validation
        _run_fiscal_validation(profile, trigger='auto_create_expense')

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
        # Sprint 4: initial fiscal validation
        _run_fiscal_validation(profile, trigger='auto_create_fep')

    return profile


def handle_payment_voided(payment, transaction, reason: str | None = None) -> None:
    """
    Servicio desacoplado para reaccionar a la anulación de un Payment
    en el plano fiscal. Se invoca desde treasury (Transaction.void flow)
    sin hardcodear reglas fiscales en la capa financiera.

    Responsabilidades:
    - Re-evaluar tax_status del perfil fiscal asociado al origen del pago.
    - Registrar TaxStatusLog con el cambio.

    No borra perfiles fiscales — los deja para trazabilidad.
    """
    # Resolve the fiscal profile from the payment's origin
    profile = None
    if payment.expense_id:
        profile = ExpenseFiscalProfile.objects.filter(expense_id=payment.expense_id).first()
    elif payment.fixed_expense_period_id:
        profile = ExpenseFiscalProfile.objects.filter(
            fixed_expense_period_id=payment.fixed_expense_period_id
        ).first()

    if not profile:
        logger.info(
            "[tax_backup] handle_payment_voided: no fiscal profile for payment %s — skipping",
            payment.pk,
        )
        return

    old_status = profile.tax_status
    new_status = TaxStatus.NEEDS_REVIEW

    note = f'Pago anulado (Payment #{payment.pk})'
    if reason:
        note += f' — motivo: {reason}'

    if old_status != new_status:
        profile.tax_status = new_status
        profile.review_reason = note
        profile.save(update_fields=['tax_status', 'review_reason', 'updated_at'])
        TaxStatusLog.objects.create(
            fiscal_profile=profile,
            previous_status=old_status,
            new_status=new_status,
            rule_code='PAYMENT_VOIDED',
            note=note,
        )
        logger.info(
            "[tax_backup] Payment voided → fiscal profile %s moved %s → %s",
            profile.pk, old_status, new_status,
        )

    # Sprint 4: re-evaluate fiscal validation
    _run_fiscal_validation(profile, trigger='payment_voided')


def _run_fiscal_validation(
    profile: ExpenseFiscalProfile,
    *,
    trigger: str = '',
) -> None:
    """Sprint 4: run fiscal validation on a profile, catching errors to avoid breaking callers."""
    try:
        from .fiscal_validation import apply_fiscal_validation
        apply_fiscal_validation(profile, trigger=trigger)
    except Exception as exc:
        logger.warning(
            "[tax_backup] fiscal validation failed for profile %s: %s",
            profile.pk, exc,
        )

"""
Respaldo Impositivo — Checklist operativo mensual.

Evalúa 5 reglas sobre un queryset de ``ExpenseFiscalProfile`` (ya filtrado
por build_period_queryset) y devuelve un dict con el resultado de cada una.

No crea modelos nuevos — todo es cálculo puro sobre datos existentes.
"""
from __future__ import annotations

from django.db.models import QuerySet

from .models import (
    AllocationType,
    DuplicateFlag,
    DuplicateStatus,
    ExpenseFiscalProfile,
    FiscalDocument,
    TaxStatus,
)


def _check_all_profiles_backed(qs: QuerySet[ExpenseFiscalProfile]) -> dict:
    """PASS si todos los perfiles están respaldados o potencialmente deducibles."""
    total = qs.count()
    if total == 0:
        return {
            'key': 'all_profiles_backed',
            'label': 'Perfiles respaldados',
            'passed': True,
            'detail': 'Sin perfiles en el período',
        }

    not_backed = qs.filter(
        tax_status__in=[TaxStatus.REGISTERED, TaxStatus.NOT_BACKED],
    )
    count = not_backed.count()
    if count == 0:
        return {
            'key': 'all_profiles_backed',
            'label': 'Perfiles respaldados',
            'passed': True,
            'detail': f'{total}/{total} perfiles respaldados',
        }
    return {
        'key': 'all_profiles_backed',
        'label': 'Perfiles respaldados',
        'passed': False,
        'detail': f'{count} perfiles sin respaldo fiscal',
        'profile_ids': list(not_backed.values_list('id', flat=True)[:100]),
    }


def _check_no_missing_documents(qs: QuerySet[ExpenseFiscalProfile]) -> dict:
    """PASS si todos los perfiles business/mixed tienen al menos 1 doc fiscal."""
    relevant = qs.filter(
        allocation_type__in=[AllocationType.BUSINESS, AllocationType.MIXED],
    )
    total = relevant.count()
    if total == 0:
        return {
            'key': 'no_missing_documents',
            'label': 'Documentación completa',
            'passed': True,
            'detail': 'Sin perfiles que requieran documentación',
        }

    profile_ids = list(relevant.values_list('id', flat=True)[:2000])
    profiles_with_fiscal_doc = set(
        FiscalDocument.objects.filter(
            fiscal_profile_id__in=profile_ids,
            is_fiscal_document=True,
        ).values_list('fiscal_profile_id', flat=True)
    )
    missing = [pid for pid in profile_ids if pid not in profiles_with_fiscal_doc]

    if not missing:
        return {
            'key': 'no_missing_documents',
            'label': 'Documentación completa',
            'passed': True,
            'detail': f'{total}/{total} perfiles con comprobantes',
        }
    return {
        'key': 'no_missing_documents',
        'label': 'Documentación completa',
        'passed': False,
        'detail': f'{len(missing)} perfiles sin comprobantes',
        'profile_ids': missing[:100],
    }


def _check_all_payments_covered(qs: QuerySet[ExpenseFiscalProfile]) -> dict:
    """PASS si todos los perfiles relevantes tienen al menos 1 payment_detail."""
    relevant = qs.filter(
        allocation_type__in=[AllocationType.BUSINESS, AllocationType.MIXED],
    )
    total = relevant.count()
    if total == 0:
        return {
            'key': 'all_payments_covered',
            'label': 'Pagos documentados',
            'passed': True,
            'detail': 'Sin perfiles que requieran pagos',
        }

    from .models import ExpensePaymentDetail
    profile_ids = list(relevant.values_list('id', flat=True)[:2000])
    profiles_with_payment = set(
        ExpensePaymentDetail.objects.filter(
            fiscal_profile_id__in=profile_ids,
        ).values_list('fiscal_profile_id', flat=True)
    )
    missing = [pid for pid in profile_ids if pid not in profiles_with_payment]

    if not missing:
        return {
            'key': 'all_payments_covered',
            'label': 'Pagos documentados',
            'passed': True,
            'detail': f'{total}/{total} perfiles con detalle de pago',
        }
    return {
        'key': 'all_payments_covered',
        'label': 'Pagos documentados',
        'passed': False,
        'detail': f'{len(missing)} perfiles sin detalle de pago',
        'profile_ids': missing[:100],
    }


def _check_no_pending_reviews(qs: QuerySet[ExpenseFiscalProfile]) -> dict:
    """PASS si no hay perfiles en estado a_revisar."""
    pending = qs.filter(tax_status=TaxStatus.NEEDS_REVIEW)
    count = pending.count()

    if count == 0:
        return {
            'key': 'no_pending_reviews',
            'label': 'Sin revisiones pendientes',
            'passed': True,
            'detail': 'Ningún perfil requiere revisión',
        }
    return {
        'key': 'no_pending_reviews',
        'label': 'Sin revisiones pendientes',
        'passed': False,
        'detail': f'{count} perfiles requieren revisión',
        'profile_ids': list(pending.values_list('id', flat=True)[:100]),
    }


def _check_no_open_duplicates(qs: QuerySet[ExpenseFiscalProfile]) -> dict:
    """PASS si no hay DuplicateFlags pendientes para perfiles del período."""
    profile_ids = list(qs.values_list('id', flat=True)[:2000])
    if not profile_ids:
        return {
            'key': 'no_open_duplicates',
            'label': 'Sin duplicados pendientes',
            'passed': True,
            'detail': 'Sin perfiles en el período',
        }

    open_dupes = DuplicateFlag.objects.filter(
        status=DuplicateStatus.PENDING,
    ).filter(
        # Either side of the pair is in-period
        fiscal_profile_id__in=profile_ids,
    ) | DuplicateFlag.objects.filter(
        status=DuplicateStatus.PENDING,
        matched_profile_id__in=profile_ids,
    )
    count = open_dupes.distinct().count()

    if count == 0:
        return {
            'key': 'no_open_duplicates',
            'label': 'Sin duplicados pendientes',
            'passed': True,
            'detail': 'Ningún duplicado pendiente de resolución',
        }
    return {
        'key': 'no_open_duplicates',
        'label': 'Sin duplicados pendientes',
        'passed': False,
        'detail': f'{count} duplicados pendientes de resolución',
    }


def evaluate_checklist(
    business,
    qs: QuerySet[ExpenseFiscalProfile],
    *,
    month: int | None = None,
    year: int | None = None,
) -> dict:
    """
    Evalúa las 5 reglas del checklist operativo mensual.

    Parámetros
    ----------
    business : Business
    qs : QuerySet[ExpenseFiscalProfile]
        Ya filtrado por build_period_queryset().
    month, year : int | None
        Período actual (para formato de salida).

    Returns
    -------
    dict con period, ready, score, total, items.
    """
    items = [
        _check_all_profiles_backed(qs),
        _check_no_missing_documents(qs),
        _check_all_payments_covered(qs),
        _check_no_pending_reviews(qs),
        _check_no_open_duplicates(qs),
    ]

    score = sum(1 for item in items if item['passed'])
    total = len(items)

    period_str = None
    if month is not None and year is not None:
        period_str = f'{year}-{month:02d}'

    return {
        'period': period_str,
        'ready': score == total,
        'score': score,
        'total': total,
        'items': items,
    }

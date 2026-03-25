"""
Respaldo Impositivo — Fuente única de filtrado por período/estado/business.

Decisión técnica: TODAS las vistas de export, report y checklist deben
usar ``build_period_queryset()`` como fuente temporal oficial.  Esto
garantiza que CSV, ZIP, monthly-report y checklist apliquen exactamente
los mismos criterios de filtrado.

Período oficial:
 - Se define por ``month`` y ``year`` (query-params).
 - En el modelo, se mapea a ``expense__due_date`` (fecha de vencimiento
   del gasto original en treasury), que representa el período fiscal real.
 - Si no se envían, se devuelve el queryset sin filtro de período (todos).
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

from django.db.models import QuerySet

from .models import ExpenseFiscalProfile


def build_period_queryset(
    business,
    *,
    month: Optional[int] = None,
    year: Optional[int] = None,
    tax_status: Optional[str] = None,
) -> QuerySet[ExpenseFiscalProfile]:
    """
    Fuente única de filtrado para exportes, reportes y checklist.

    Parámetros
    ----------
    business : Business
        Tenant activo (obligatorio).
    month : int | None
        Mes (1-12). Si se omite junto con year, no filtra por período.
    year : int | None
        Año (ej. 2025). Si se omite junto con month, no filtra.
    tax_status : str | None
        Valor de TaxStatus (ej. 'respaldado'). Filtra si se provee.

    Returns
    -------
    QuerySet[ExpenseFiscalProfile]
        Con select_related('expense') ya incluido.
    """
    qs = (
        ExpenseFiscalProfile.objects
        .filter(business=business)
        .select_related('expense', 'fixed_expense_period__fixed_expense')
    )

    # ── Filtro temporal ─────────────────────────────────────────────────
    # Unifica expense.due_date para gastos puntuales y
    # fixed_expense_period.period para períodos de gasto fijo.
    if month is not None and year is not None:
        _, last_day = calendar.monthrange(year, month)
        start = date(year, month, 1)
        end = date(year, month, last_day)
        from django.db.models import Q
        qs = qs.filter(
            Q(expense__due_date__gte=start, expense__due_date__lte=end)
            | Q(fixed_expense_period__period__gte=start, fixed_expense_period__period__lte=end)
        )

    # ── Filtro por estado fiscal ─────────────────────────────────────────
    if tax_status:
        qs = qs.filter(tax_status=tax_status)

    return qs.order_by('-created_at')


def parse_period_params(query_params) -> dict:
    """
    Extrae y valida month/year/tax_status de request.query_params.
    Devuelve dict listo para pasar a ``build_period_queryset(**result)``.
    Lanza ValueError si los valores son inválidos.
    """
    raw_month = query_params.get('month')
    raw_year = query_params.get('year')
    tax_status = query_params.get('tax_status') or None

    month = None
    year = None

    if raw_month is not None and raw_year is not None:
        try:
            month = int(raw_month)
            year = int(raw_year)
        except (ValueError, TypeError):
            raise ValueError('month y year deben ser enteros.')
        if not (1 <= month <= 12):
            raise ValueError('month debe estar entre 1 y 12.')
        if not (2000 <= year <= 2100):
            raise ValueError('year debe estar entre 2000 y 2100.')
    elif raw_month is not None or raw_year is not None:
        raise ValueError('Ambos parámetros month y year son requeridos juntos.')

    return {'month': month, 'year': year, 'tax_status': tax_status}

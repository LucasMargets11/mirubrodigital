"""
Sprint 4 — Fiscal Validation Service

Servicio de dominio que evalúa el estado fiscal/documental de un
ExpenseFiscalProfile. Determina si el gasto tiene comprobante válido,
datos completos y consistencia con el pago.

Reglas evaluadas:
  A. Existencia documental
  B. Resultado de extracción
  C. Datos mínimos del comprobante
  D. Consistencia documento vs gasto/pago
  E. Trazabilidad de observaciones

Resultado persistido en: fiscal_status, missing_fields, validation_issues,
review_required, evaluated_at, evaluation_source.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import NamedTuple

from django.utils import timezone

from .models import (
    EvaluationSource,
    ExpenseFiscalProfile,
    FiscalDocument,
    FiscalStatus,
    ParseStatus,
)

logger = logging.getLogger(__name__)

# ── Campos mínimos requeridos en un comprobante fiscal ──────────────────

REQUIRED_FIELDS = [
    ('document_type', 'Tipo de comprobante'),
    ('invoice_number', 'Número de comprobante'),
    ('issuer_tax_id', 'CUIT emisor'),
    ('issue_date', 'Fecha de emisión'),
    ('total', 'Total'),
    ('is_fiscal_document', 'Indicador fiscal'),
]

# Tolerancia de monto: ±2% o $10, lo que sea mayor
AMOUNT_TOLERANCE_PERCENT = Decimal('0.02')
AMOUNT_TOLERANCE_ABS = Decimal('10')

# Tolerancia de fecha: ±30 días
DATE_TOLERANCE_DAYS = 30


# ── Resultado de la evaluación ──────────────────────────────────────────

class FiscalValidationResult(NamedTuple):
    fiscal_status: str          # FiscalStatus value
    review_required: bool
    missing_fields: list[str]   # field codes
    validation_issues: list[dict]  # [{"code": "...", "message": "..."}]
    evaluation_source: str      # EvaluationSource value


# ── Servicio principal ──────────────────────────────────────────────────

def evaluate_expense_fiscal_status(
    profile: ExpenseFiscalProfile,
) -> FiscalValidationResult:
    """
    Evalúa el estado fiscal/documental de un ExpenseFiscalProfile.

    Inspecciona:
    - FiscalDocument (tax_backup) — adjuntos al perfil fiscal
    - ExpenseDocument (treasury) — adjuntos al gasto/período origen
    - Payment (treasury) — pago asociado al origen

    Retorna FiscalValidationResult con status, issues y missing_fields.
    Determinístico y sin efectos secundarios.
    """
    issues: list[dict] = []
    missing: list[str] = []

    # ── Recolectar documentos ────────────────────────────────────────
    fiscal_docs = _get_fiscal_documents(profile)
    expense_docs = _get_expense_documents(profile)

    has_any_doc = len(fiscal_docs) > 0 or len(expense_docs) > 0

    # ── A. Existencia documental ─────────────────────────────────────
    if not has_any_doc:
        return FiscalValidationResult(
            fiscal_status=FiscalStatus.SIN_COMPROBANTE,
            review_required=False,
            missing_fields=[],
            validation_issues=[{
                'code': 'NO_DOCUMENT',
                'message': 'No hay comprobante/documento asociado al gasto.',
            }],
            evaluation_source=EvaluationSource.MANUAL,
        )

    # ── B. Resultado de extracción ───────────────────────────────────
    eval_source = _determine_evaluation_source(fiscal_docs, expense_docs)
    extraction_failed = _check_extraction_failures(fiscal_docs, expense_docs)

    if extraction_failed['all_failed'] and not extraction_failed['has_usable_data']:
        issues.append({
            'code': 'EXTRACTION_FAILED',
            'message': 'La extracción de datos del comprobante falló y no hay datos suficientes.',
        })
        return FiscalValidationResult(
            fiscal_status=FiscalStatus.INCOMPLETO,
            review_required=True,
            missing_fields=[],
            validation_issues=issues,
            evaluation_source=eval_source,
        )

    if extraction_failed['some_failed']:
        issues.append({
            'code': 'EXTRACTION_PARTIAL',
            'message': 'Algunos documentos no pudieron ser procesados correctamente.',
        })

    # ── C. Datos mínimos del comprobante ─────────────────────────────
    best_doc = _get_best_fiscal_document(fiscal_docs)
    best_exp_doc = _get_best_expense_document(expense_docs)

    # Merge data from best available sources
    merged = _merge_document_data(best_doc, best_exp_doc)

    for field_code, field_label in REQUIRED_FIELDS:
        if field_code == 'is_fiscal_document':
            if not merged.get('is_fiscal_document'):
                missing.append(field_code)
        elif not merged.get(field_code):
            missing.append(field_code)

    # ── D. Consistencia documento vs gasto/pago ──────────────────────
    amount_ok = _check_amount_consistency(profile, merged, issues)
    date_ok = _check_date_consistency(profile, merged, issues)
    currency_ok = _check_currency_consistency(profile, merged, issues)
    fiscal_ok = merged.get('is_fiscal_document', False)

    if not fiscal_ok:
        issues.append({
            'code': 'NOT_FISCAL',
            'message': 'El comprobante no está identificado como documento fiscal.',
        })

    # Check buyer tax ID
    buyer_required = _is_buyer_tax_id_required(profile, merged)
    if buyer_required and not merged.get('buyer_tax_id'):
        issues.append({
            'code': 'NO_BUYER_TAX_ID',
            'message': 'Falta CUIT/RUT del comprador en el comprobante.',
        })
        missing.append('buyer_tax_id')

    # ── Determinar status final ──────────────────────────────────────
    critical_missing = [f for f in missing if f in ('issuer_tax_id', 'total', 'is_fiscal_document')]

    if len(critical_missing) > 0 or len(missing) >= 3:
        status = FiscalStatus.INCOMPLETO
    elif not amount_ok or not date_ok or not currency_ok:
        status = FiscalStatus.REQUIERE_REVISION
    elif len(missing) > 0 or len(issues) > 0:
        if any(i['code'] in ('NOT_FISCAL', 'EXTRACTION_FAILED', 'EXTRACTION_PARTIAL')
               for i in issues):
            status = FiscalStatus.REQUIERE_REVISION
        else:
            status = FiscalStatus.VALIDO_CON_OBSERVACIONES
    else:
        status = FiscalStatus.VALIDO

    review = status in (FiscalStatus.REQUIERE_REVISION, FiscalStatus.INCOMPLETO)

    return FiscalValidationResult(
        fiscal_status=status,
        review_required=review,
        missing_fields=missing,
        validation_issues=issues,
        evaluation_source=eval_source,
    )


def apply_fiscal_validation(
    profile: ExpenseFiscalProfile,
    *,
    trigger: str = '',
) -> FiscalValidationResult:
    """
    Evalúa y persiste el resultado de validación fiscal en el perfil.
    Wrapper que llama evaluate_expense_fiscal_status() y graba los campos.
    """
    result = evaluate_expense_fiscal_status(profile)

    profile.fiscal_status = result.fiscal_status
    profile.review_required = result.review_required
    profile.missing_fields = result.missing_fields if result.missing_fields else None
    profile.validation_issues = result.validation_issues if result.validation_issues else None
    profile.evaluated_at = timezone.now()
    profile.evaluation_source = result.evaluation_source

    profile.save(update_fields=[
        'fiscal_status', 'review_required', 'missing_fields',
        'validation_issues', 'evaluated_at', 'evaluation_source',
        'updated_at',
    ])

    logger.info(
        '[fiscal_validation] Profile %s evaluated: status=%s, issues=%d, missing=%d (trigger=%s)',
        profile.pk,
        result.fiscal_status,
        len(result.validation_issues),
        len(result.missing_fields),
        trigger,
    )

    return result


# ── Helpers internos ────────────────────────────────────────────────────

def _get_fiscal_documents(
    profile: ExpenseFiscalProfile,
) -> list[FiscalDocument]:
    """Obtiene FiscalDocuments del perfil fiscal (cacheados o query)."""
    cache = getattr(profile, '_prefetched_objects_cache', None) or {}
    if 'documents' in cache:
        return list(cache['documents'])
    return list(profile.documents.all())


def _get_expense_documents(profile: ExpenseFiscalProfile) -> list:
    """Obtiene ExpenseDocuments del origen (expense o fep) en treasury."""
    from apps.treasury.models import ExpenseDocument

    if profile.expense_id:
        return list(
            ExpenseDocument.objects.filter(
                expense_id=profile.expense_id,
            ).exclude(status='archived')
        )
    if profile.fixed_expense_period_id:
        return list(
            ExpenseDocument.objects.filter(
                fixed_expense_period_id=profile.fixed_expense_period_id,
            ).exclude(status='archived')
        )
    return []


def _determine_evaluation_source(
    fiscal_docs: list[FiscalDocument],
    expense_docs: list,
) -> str:
    """Determina si la evaluación se basa en datos manuales, extraídos o ambos."""
    has_manual = any(
        d.parse_status in (ParseStatus.MANUAL, ParseStatus.PENDING) for d in fiscal_docs
    )
    has_extracted = any(
        d.parse_status == ParseStatus.PARSED for d in fiscal_docs
    )
    has_exp_extracted = any(
        getattr(d, 'extraction_source', None) in ('qr', 'ocr', 'mixed')
        for d in expense_docs
    )

    if (has_extracted or has_exp_extracted) and has_manual:
        return EvaluationSource.MIXED
    if has_extracted or has_exp_extracted:
        return EvaluationSource.EXTRACTED
    return EvaluationSource.MANUAL


def _check_extraction_failures(
    fiscal_docs: list[FiscalDocument],
    expense_docs: list,
) -> dict:
    """Evalúa resultados de extracción en ambas capas documentales."""
    all_fiscal_failed = all(
        d.parse_status == ParseStatus.FAILED for d in fiscal_docs
    ) if fiscal_docs else False

    all_exp_failed = all(
        getattr(d, 'status', None) == 'failed' for d in expense_docs
    ) if expense_docs else False

    some_failed = any(
        d.parse_status == ParseStatus.FAILED for d in fiscal_docs
    ) or any(
        getattr(d, 'status', None) == 'failed' for d in expense_docs
    )

    # Check if there's usable data despite failures
    has_usable = any(
        d.parse_status in (ParseStatus.PARSED, ParseStatus.MANUAL) for d in fiscal_docs
    ) or any(
        d.total is not None or d.issuer_tax_id for d in fiscal_docs
    ) or any(
        getattr(d, 'normalized_data', None) for d in expense_docs
    )

    all_failed = (
        (all_fiscal_failed and not expense_docs)
        or (all_exp_failed and not fiscal_docs)
        or (all_fiscal_failed and all_exp_failed)
    )
    # If only one layer has docs and all failed
    if not fiscal_docs and not expense_docs:
        all_failed = False

    return {
        'all_failed': all_failed,
        'some_failed': some_failed,
        'has_usable_data': has_usable,
    }


def _get_best_fiscal_document(docs: list[FiscalDocument]) -> FiscalDocument | None:
    """Selecciona el mejor FiscalDocument: prioriza parsed, luego con más datos."""
    if not docs:
        return None
    # Prefer parsed, then manual, then others
    parsed = [d for d in docs if d.parse_status == ParseStatus.PARSED and d.is_fiscal_document]
    if parsed:
        return max(parsed, key=lambda d: _doc_completeness(d))
    fiscal = [d for d in docs if d.is_fiscal_document]
    if fiscal:
        return max(fiscal, key=lambda d: _doc_completeness(d))
    return max(docs, key=lambda d: _doc_completeness(d))


def _doc_completeness(doc: FiscalDocument) -> int:
    """Score de completitud para ranking de documentos."""
    score = 0
    if doc.issuer_tax_id:
        score += 1
    if doc.invoice_number:
        score += 1
    if doc.issue_date:
        score += 1
    if doc.total is not None:
        score += 1
    if doc.is_fiscal_document:
        score += 1
    if doc.buyer_tax_id:
        score += 1
    if doc.document_type and doc.document_type != 'otro':
        score += 1
    return score


def _get_best_expense_document(docs: list) -> object | None:
    """Selecciona el mejor ExpenseDocument: prioriza processed con más datos."""
    if not docs:
        return None
    processed = [d for d in docs if getattr(d, 'status', None) == 'processed'
                 and getattr(d, 'normalized_data', None)]
    if processed:
        return max(processed, key=lambda d: len(d.normalized_data or {}))
    with_data = [d for d in docs if getattr(d, 'normalized_data', None)]
    if with_data:
        return max(with_data, key=lambda d: len(d.normalized_data or {}))
    return docs[0] if docs else None


def _merge_document_data(
    fiscal_doc: FiscalDocument | None,
    expense_doc: object | None,
) -> dict:
    """
    Combina datos del FiscalDocument y ExpenseDocument en un dict unificado.
    FiscalDocument tiene prioridad (datos manuales/verificados).
    ExpenseDocument.normalized_data complementa lo que falte.
    """
    merged: dict = {}

    # Layer 1: ExpenseDocument normalized_data (base — se sobreescribe)
    if expense_doc:
        nd = getattr(expense_doc, 'normalized_data', None) or {}
        if nd.get('document_type'):
            merged['document_type'] = nd['document_type']
        if nd.get('document_number'):
            merged['invoice_number'] = nd['document_number']
        if nd.get('issuer_tax_id'):
            merged['issuer_tax_id'] = nd['issuer_tax_id']
        if nd.get('issue_date'):
            merged['issue_date'] = nd['issue_date']
        if nd.get('total_amount'):
            try:
                merged['total'] = Decimal(str(nd['total_amount']))
            except Exception:
                pass
        if nd.get('buyer_tax_id'):
            merged['buyer_tax_id'] = nd['buyer_tax_id']
        if nd.get('issuer_name'):
            merged['issuer_name'] = nd['issuer_name']
        if nd.get('currency'):
            merged['currency'] = nd['currency']
        # Mark as fiscal if document type is recognized
        _FISCAL_TYPES = {
            'Factura A', 'Factura B', 'Factura C', 'Factura M',
            'Nota de Crédito A', 'Nota de Crédito B', 'Nota de Crédito C',
            'Nota de Débito A', 'Nota de Débito B', 'Nota de Débito C',
        }
        if nd.get('document_type') in _FISCAL_TYPES:
            merged['is_fiscal_document'] = True

    # Layer 2: FiscalDocument fields (override — verified data)
    if fiscal_doc:
        if fiscal_doc.document_type and fiscal_doc.document_type != 'otro':
            merged['document_type'] = fiscal_doc.document_type
        if fiscal_doc.invoice_number:
            merged['invoice_number'] = fiscal_doc.invoice_number
        if fiscal_doc.issuer_tax_id:
            merged['issuer_tax_id'] = fiscal_doc.issuer_tax_id
        if fiscal_doc.issue_date:
            merged['issue_date'] = fiscal_doc.issue_date
        if fiscal_doc.total is not None:
            merged['total'] = fiscal_doc.total
        if fiscal_doc.is_fiscal_document:
            merged['is_fiscal_document'] = True
        if fiscal_doc.buyer_tax_id:
            merged['buyer_tax_id'] = fiscal_doc.buyer_tax_id
        if fiscal_doc.issuer_name:
            merged['issuer_name'] = fiscal_doc.issuer_name
        if fiscal_doc.currency and fiscal_doc.currency != 'ARS':
            # Only override if not the default — a non-default currency is meaningful
            merged['currency'] = fiscal_doc.currency
        elif not merged.get('currency') and fiscal_doc.currency:
            merged['currency'] = fiscal_doc.currency

    return merged


def _check_amount_consistency(
    profile: ExpenseFiscalProfile,
    merged: dict,
    issues: list[dict],
) -> bool:
    """
    Valida cercanía razonable entre total del comprobante y monto del gasto/pago.
    Returns True if amounts are consistent (or not checkable).
    """
    doc_total = merged.get('total')
    if doc_total is None:
        return True  # Can't check — not an inconsistency

    source_amount = profile.source_amount
    if source_amount is None:
        return True

    doc_total = Decimal(str(doc_total))
    source_amount = Decimal(str(source_amount))

    if source_amount == 0:
        return True

    diff = abs(doc_total - source_amount)
    threshold = max(
        source_amount * AMOUNT_TOLERANCE_PERCENT,
        AMOUNT_TOLERANCE_ABS,
    )

    if diff > threshold:
        issues.append({
            'code': 'AMOUNT_MISMATCH',
            'message': (
                f'El total del comprobante (${doc_total}) difiere del monto '
                f'del gasto (${source_amount}) por ${diff}.'
            ),
        })
        return False

    return True


def _check_date_consistency(
    profile: ExpenseFiscalProfile,
    merged: dict,
    issues: list[dict],
) -> bool:
    """
    Valida que la fecha del comprobante sea razonablemente cercana al gasto/pago.
    Returns True if dates are consistent (or not checkable).
    """
    from datetime import date as date_type

    doc_date = merged.get('issue_date')
    if doc_date is None:
        return True  # Can't check

    # Normalize to date object
    if isinstance(doc_date, str):
        try:
            doc_date = date_type.fromisoformat(doc_date)
        except (ValueError, TypeError):
            return True

    source_date = profile.source_due_date
    if source_date is None:
        return True

    # Normalize source_date
    if isinstance(source_date, str):
        try:
            source_date = date_type.fromisoformat(source_date)
        except (ValueError, TypeError):
            return True

    diff_days = abs((doc_date - source_date).days)
    if diff_days > DATE_TOLERANCE_DAYS:
        issues.append({
            'code': 'DATE_MISMATCH',
            'message': (
                f'La fecha del comprobante ({doc_date}) difiere en {diff_days} días '
                f'de la fecha del gasto ({source_date}).'
            ),
        })
        return False

    return True


def _check_currency_consistency(
    profile: ExpenseFiscalProfile,
    merged: dict,
    issues: list[dict],
) -> bool:
    """
    Valida que la moneda del comprobante coincida con la esperada (ARS por defecto).
    Returns True if currencies match (or not checkable).
    """
    doc_currency = merged.get('currency')
    if not doc_currency:
        return True  # Can't check — not an inconsistency

    # Expected currency: ARS for Argentine businesses (default assumption)
    expected_currency = 'ARS'

    if doc_currency.upper() != expected_currency:
        issues.append({
            'code': 'CURRENCY_MISMATCH',
            'message': (
                f'La moneda del comprobante ({doc_currency}) no coincide '
                f'con la esperada ({expected_currency}).'
            ),
        })
        return False

    return True


def _is_buyer_tax_id_required(
    profile: ExpenseFiscalProfile,
    merged: dict,
) -> bool:
    """
    Determina si se requiere CUIT/RUT del comprador.
    Requerido cuando el comprobante es fiscal y de tipo factura (A, B, M) o
    cuando el gasto es de negocio.
    """
    from .models import AllocationType

    if profile.allocation_type == AllocationType.PERSONAL:
        return False

    # For fiscal documents tipo A (typically requires buyer info)
    doc_type = merged.get('document_type', '')
    if isinstance(doc_type, str) and 'A' in doc_type.upper():
        return True

    # For business allocation with factura type
    if profile.allocation_type == AllocationType.BUSINESS:
        if doc_type in ('factura', 'Factura A', 'Factura B', 'Factura M'):
            return True

    return False

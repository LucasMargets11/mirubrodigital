"""
Respaldo Impositivo — Rule Engine (Motor de Reglas)

Funciones puras y sin estado que evalúan el estado fiscal de un
ExpenseFiscalProfile basándose en sus documentos, pagos y metadatos.

Cada regla devuelve ``(new_status, rule_code, note)`` o ``None``
si no aplica.  Se evalúan en orden de prioridad descendente; la
primera que retorne un resultado gana.
"""
from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from .models import (
    AllocationType,
    DuplicateFlag,
    DuplicateMatchType,
    DuplicateStatus,
    ExpenseFiscalProfile,
    FiscalDocument,
    TaxStatus,
)


# ── Resultado de una regla ────────────────────────────────────────────────

class RuleResult(NamedTuple):
    status: str        # TaxStatus value
    rule_code: str     # Código corto para el TaxStatusLog
    note: str          # Descripción legible


# ── Reglas individuales ──────────────────────────────────────────────────
# Convención: cada función recibe el profile *con* sus relaciones
# pre-cargadas (documents, payment_details) y devuelve RuleResult | None.

def rule_personal_allocation(profile: ExpenseFiscalProfile) -> RuleResult | None:
    """R1 — Gasto 100 % personal → nunca es deducible."""
    if profile.allocation_type == AllocationType.PERSONAL:
        return RuleResult(
            TaxStatus.NOT_BACKED,
            'RULE_PERSONAL',
            'Gasto declarado como personal — no respaldado fiscalmente.',
        )
    return None


def rule_no_fiscal_document(profile: ExpenseFiscalProfile) -> RuleResult | None:
    """R2 — Sin ningún comprobante fiscal válido → no respaldado."""
    docs = _get_documents(profile)
    if not docs:
        return RuleResult(
            TaxStatus.NOT_BACKED,
            'RULE_NO_DOC',
            'No tiene documentos fiscales adjuntos.',
        )
    has_fiscal = any(d.is_fiscal_document for d in docs)
    if not has_fiscal:
        return RuleResult(
            TaxStatus.NOT_BACKED,
            'RULE_NO_FISCAL_DOC',
            'Tiene documentos pero ninguno es comprobante fiscal válido.',
        )
    return None


def rule_capital_asset_review(profile: ExpenseFiscalProfile) -> RuleResult | None:
    """R3 — Bien de uso requiere revisión de amortización."""
    if profile.is_capital_asset:
        return RuleResult(
            TaxStatus.NEEDS_REVIEW,
            'RULE_CAPITAL_ASSET',
            'Bien de uso / activo fijo — requiere revisión de amortización.',
        )
    return None


def rule_mixed_allocation(profile: ExpenseFiscalProfile) -> RuleResult | None:
    """R4 — Gasto mixto → potencialmente deducible (proporcional)."""
    if profile.allocation_type == AllocationType.MIXED:
        docs = _get_documents(profile)
        has_fiscal = any(d.is_fiscal_document for d in docs)
        if has_fiscal:
            return RuleResult(
                TaxStatus.POTENTIALLY_DEDUCTIBLE,
                'RULE_MIXED',
                'Gasto mixto con comprobante fiscal — deducción proporcional.',
            )
    return None


def rule_amount_mismatch(profile: ExpenseFiscalProfile) -> RuleResult | None:
    """R5 — El total del comprobante no coincide con el monto del gasto."""
    docs = _get_documents(profile)
    fiscal_docs = [d for d in docs if d.is_fiscal_document and d.total is not None]
    if not fiscal_docs:
        return None
    expense_amount = profile.source_amount
    if expense_amount is None:
        return None
    doc_total = sum(d.total for d in fiscal_docs)
    # Tolerancia de ±$1 por redondeo
    if abs(doc_total - expense_amount) > Decimal('1'):
        return RuleResult(
            TaxStatus.NEEDS_REVIEW,
            'RULE_AMOUNT_MISMATCH',
            f'Diferencia entre comprobantes (${doc_total}) y gasto (${expense_amount}).',
        )
    return None


def rule_missing_buyer_data(profile: ExpenseFiscalProfile) -> RuleResult | None:
    """R6 — Comprobante fiscal sin CUIT del comprador → revisar."""
    docs = _get_documents(profile)
    for doc in docs:
        if doc.is_fiscal_document and not doc.buyer_tax_id:
            return RuleResult(
                TaxStatus.NEEDS_REVIEW,
                'RULE_NO_BUYER_TAX_ID',
                'Comprobante fiscal sin CUIT/RUT del comprador.',
            )
    return None


def rule_backed(profile: ExpenseFiscalProfile) -> RuleResult | None:
    """R7 — Gasto de negocio con comprobante fiscal y datos completos → respaldado."""
    if profile.allocation_type != AllocationType.BUSINESS:
        return None
    docs = _get_documents(profile)
    has_complete_fiscal = any(
        d.is_fiscal_document
        and d.issuer_tax_id
        and d.buyer_tax_id
        and d.total is not None
        for d in docs
    )
    if has_complete_fiscal:
        return RuleResult(
            TaxStatus.BACKED,
            'RULE_BACKED',
            'Gasto de negocio con comprobante fiscal completo.',
        )
    return None


def rule_fallback_registered(profile: ExpenseFiscalProfile) -> RuleResult | None:
    """R8 — Fallback: si ninguna otra regla aplica, queda registrado."""
    return RuleResult(
        TaxStatus.REGISTERED,
        'RULE_FALLBACK',
        'Sin condición específica — permanece como registrado.',
    )


# ── Orden de evaluación ─────────────────────────────────────────────────

RULES = [
    rule_personal_allocation,     # R1
    rule_no_fiscal_document,      # R2
    rule_capital_asset_review,    # R3
    rule_mixed_allocation,        # R4
    rule_amount_mismatch,         # R5
    rule_missing_buyer_data,      # R6
    rule_backed,                  # R7
    rule_fallback_registered,     # R8 — siempre matchea
]


def evaluate_tax_status(profile: ExpenseFiscalProfile) -> RuleResult:
    """
    Evalúa el perfil fiscal contra todas las reglas en orden.
    Retorna la primera que matchee (siempre retorna algo gracias al fallback).
    """
    for rule_fn in RULES:
        result = rule_fn(profile)
        if result is not None:
            return result
    # Nunca debería llegar aquí por el fallback, pero por seguridad:
    return RuleResult(TaxStatus.REGISTERED, 'RULE_FALLBACK', 'Fallback de seguridad.')


# ── Detección de duplicados ──────────────────────────────────────────────

def detect_duplicates(profile: ExpenseFiscalProfile) -> list[tuple[ExpenseFiscalProfile, str]]:
    """
    Busca perfiles fiscales del mismo business cuyos documentos coincidan
    por (issuer_tax_id + invoice_number + issue_date + total).

    Retorna lista de (matched_profile, match_type_value).
    """
    docs = _get_documents(profile)
    matched: dict[int, str] = {}

    for doc in docs:
        if not (doc.issuer_tax_id and doc.invoice_number and doc.issue_date and doc.total is not None):
            continue
        candidates = FiscalDocument.objects.filter(
            fiscal_profile__business=profile.business,
            issuer_tax_id=doc.issuer_tax_id,
            invoice_number=doc.invoice_number,
            issue_date=doc.issue_date,
            total=doc.total,
        ).exclude(
            fiscal_profile=profile,
        ).select_related('fiscal_profile')

        for candidate in candidates:
            if candidate.fiscal_profile_id not in matched:
                matched[candidate.fiscal_profile_id] = (
                    DuplicateMatchType.PROVIDER_INVOICE_DATE_AMOUNT
                )

    return [
        (ExpenseFiscalProfile.objects.get(pk=pid), mt)
        for pid, mt in matched.items()
    ]


def create_duplicate_flags(profile: ExpenseFiscalProfile) -> list[DuplicateFlag]:
    """
    Detecta duplicados y crea DuplicateFlag para cada par nuevo.
    Ignora pares que ya existen (por el UniqueConstraint canónico).
    """
    matches = detect_duplicates(profile)
    created = []
    for matched_profile, match_type in matches:
        # El save() del modelo normaliza el orden del par
        flag, is_new = DuplicateFlag.objects.get_or_create(
            fiscal_profile_id=min(profile.pk, matched_profile.pk),
            matched_profile_id=max(profile.pk, matched_profile.pk),
            defaults={
                'match_type': match_type,
                'status': DuplicateStatus.PENDING,
            },
        )
        if is_new:
            created.append(flag)
    return created


# ── Helpers ──────────────────────────────────────────────────────────────

def _get_documents(profile: ExpenseFiscalProfile) -> list[FiscalDocument]:
    """Obtiene documentos cacheados o hace la query."""
    cache = getattr(profile, '_prefetched_objects_cache', None) or {}
    if 'documents' in cache:
        return list(cache['documents'])
    return list(profile.documents.all())

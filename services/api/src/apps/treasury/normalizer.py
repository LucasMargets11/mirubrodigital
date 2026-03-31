"""
treasury/normalizer.py — Document data normalization service.

Sprint 5: transforms flat extracted fields into a stable nested structure.
Normalization is strictly separated from extraction logic.

The normalized output has a STABLE shape regardless of how many fields
were actually extracted. Missing fields are null, never omitted.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Current pipeline version — bump when extraction or normalization logic changes
PIPELINE_VERSION = '5.0'


def _stable_normalized_schema() -> dict[str, Any]:
    """Return the empty canonical normalized data structure."""
    return {
        'issuer': {
            'name': None,
            'cuit': None,
        },
        'buyer': {
            'name': None,
            'cuit': None,
        },
        'voucher': {
            'type': None,
            'number': None,
            'issue_date': None,
        },
        'amounts': {
            'total': None,
            'currency': None,
        },
        'source_priority': {},
        'confidence': 'low',
    }


def normalize_extraction(
    parsed_fields: dict[str, Any],
    source_priority: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Transform flat extracted fields into the stable nested structure.

    Args:
        parsed_fields: Flat dict from extractors (issuer_tax_id, total_amount, etc.)
        source_priority: Per-field source attribution (e.g. {'issuer_tax_id': 'qr'})

    Returns:
        Nested dict with stable shape — all keys present, nulls for missing data.
    """
    result = _stable_normalized_schema()
    priority = source_priority or parsed_fields.get('_source_priority', {})

    # ── Issuer ────────────────────────────────────────────────────
    if parsed_fields.get('issuer_name'):
        result['issuer']['name'] = str(parsed_fields['issuer_name']).strip()
    if parsed_fields.get('issuer_tax_id'):
        result['issuer']['cuit'] = str(parsed_fields['issuer_tax_id']).strip()

    # ── Buyer ─────────────────────────────────────────────────────
    if parsed_fields.get('buyer_name'):
        result['buyer']['name'] = str(parsed_fields['buyer_name']).strip()
    if parsed_fields.get('buyer_tax_id'):
        result['buyer']['cuit'] = str(parsed_fields['buyer_tax_id']).strip()

    # ── Voucher ───────────────────────────────────────────────────
    if parsed_fields.get('document_type'):
        result['voucher']['type'] = str(parsed_fields['document_type']).strip()
    if parsed_fields.get('document_number'):
        result['voucher']['number'] = str(parsed_fields['document_number']).strip()
    if parsed_fields.get('issue_date'):
        result['voucher']['issue_date'] = str(parsed_fields['issue_date']).strip()

    # ── Amounts ───────────────────────────────────────────────────
    if parsed_fields.get('total_amount'):
        result['amounts']['total'] = str(parsed_fields['total_amount']).strip()
    if parsed_fields.get('currency'):
        result['amounts']['currency'] = str(parsed_fields['currency']).strip()

    # ── Source priority ───────────────────────────────────────────
    result['source_priority'] = {
        k: v for k, v in priority.items() if k != '_source_priority'
    }

    # ── Confidence ────────────────────────────────────────────────
    key_fields_present = sum(1 for v in [
        result['issuer']['cuit'],
        result['voucher']['number'],
        result['amounts']['total'],
        result['voucher']['issue_date'],
    ] if v is not None)

    result['confidence'] = (
        'high' if key_fields_present >= 3
        else 'medium' if key_fields_present >= 2
        else 'low'
    )

    return result

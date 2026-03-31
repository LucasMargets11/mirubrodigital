"""
treasury/extractors/ocr_adapter.py — OCR text extraction adapter.

Uses pytesseract for text extraction, with regex-based field parsing
for Argentine fiscal documents.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .base import BaseExtractor, ExtractionResult
from .image_utils import images_from_file

logger = logging.getLogger(__name__)


class OCRExtractor(BaseExtractor):
    """OCR text extractor — pytesseract with Argentine fiscal regex parsing."""

    name = 'ocr'

    def is_available(self) -> bool:
        try:
            import pytesseract  # noqa: F401
            return True
        except ImportError:
            return False

    def extract(self, file_data: bytes, mime_type: str) -> ExtractionResult:
        if not self.is_available():
            return ExtractionResult(
                source='ocr',
                success=False,
                errors=['pytesseract not installed — OCR extraction unavailable'],
            )

        try:
            import pytesseract
        except ImportError:
            return ExtractionResult(
                source='ocr', success=False,
                errors=['pytesseract import failed'],
            )

        images = images_from_file(file_data, mime_type)
        if not images:
            return ExtractionResult(
                source='ocr', success=False,
                errors=['No images could be loaded from file'],
            )

        full_text_parts: list[str] = []
        page_texts: list[dict[str, Any]] = []
        errors: list[str] = []

        for idx, img in enumerate(images):
            try:
                text = pytesseract.image_to_string(img, lang='spa+eng')
                if text and text.strip():
                    stripped = text.strip()
                    full_text_parts.append(stripped)
                    page_texts.append({
                        'page': idx + 1,
                        'text': stripped,
                        'char_count': len(stripped),
                    })
            except Exception as exc:
                errors.append(f'pytesseract error on page {idx + 1}: {exc}')
                logger.warning('pytesseract error on page %d: %s', idx + 1, exc)

        if not full_text_parts:
            return ExtractionResult(
                source='ocr', success=False,
                errors=errors or ['OCR produced no text from document'],
            )

        full_text = '\n'.join(full_text_parts)
        parsed = _parse_ocr_text(full_text)

        raw_data = {
            'ocr_text': full_text,
            'parsed_fields': parsed,
        }

        # Compute a basic confidence from how many key fields were found
        key_fields = ['issuer_tax_id', 'document_number', 'total_amount', 'issue_date']
        found = sum(1 for f in key_fields if parsed.get(f))
        confidence = 'high' if found >= 3 else 'medium' if found >= 2 else 'low'

        return ExtractionResult(
            source='ocr',
            success=True,
            raw_data=raw_data,
            parsed_fields=parsed,
            errors=errors,
            metadata={
                'pages': len(page_texts),
                'page_details': page_texts,
                'total_chars': len(full_text),
                'confidence': confidence,
            },
        )


def _parse_ocr_text(text: str) -> dict[str, Any]:
    """Extract structured fields from OCR text using regex patterns."""
    result: dict[str, Any] = {}

    # ── Find ALL CUITs in the text ──
    cuit_pattern = r'\b(20|23|24|27|30|33|34)\-?\d{8}\-?\d\b'
    all_cuits = [(m.start(), m.group(0).replace('-', '')) for m in re.finditer(cuit_pattern, text)]

    # First CUIT (usually in emisor section) → issuer_tax_id
    if all_cuits:
        cuit_raw = all_cuits[0][1]
        result['issuer_tax_id'] = f'{cuit_raw[:2]}-{cuit_raw[2:10]}-{cuit_raw[10:]}'

    # Second CUIT (usually in comprador section) → buyer_tax_id
    if len(all_cuits) >= 2:
        # Only if it's a different CUIT and appears after the doc type header
        buyer_raw = all_cuits[1][1]
        if buyer_raw != all_cuits[0][1]:
            result['buyer_tax_id'] = f'{buyer_raw[:2]}-{buyer_raw[2:10]}-{buyer_raw[10:]}'
            logger.info('[ocr] buyer_tax_id detected from text: %s', result['buyer_tax_id'])

    # Document number patterns
    doc_num_match = re.search(r'(?:N[°ºr.:o]+\s*)?(\d{4,5})\s*[-–]\s*(\d{6,8})', text)
    if doc_num_match:
        pto = doc_num_match.group(1).zfill(5)
        nro = doc_num_match.group(2).zfill(8)
        result['document_number'] = f'{pto}-{nro}'

    # Document type
    type_patterns = [
        (r'FACTURA\s+["\']?A["\']?', 'Factura A'),
        (r'FACTURA\s+["\']?B["\']?', 'Factura B'),
        (r'FACTURA\s+["\']?C["\']?', 'Factura C'),
        (r'NOTA\s+DE\s+CR[ÉE]DITO\s+["\']?A["\']?', 'Nota de Crédito A'),
        (r'NOTA\s+DE\s+CR[ÉE]DITO\s+["\']?B["\']?', 'Nota de Crédito B'),
        (r'NOTA\s+DE\s+D[ÉE]BITO\s+["\']?A["\']?', 'Nota de Débito A'),
        (r'RECIBO', 'Recibo'),
        (r'TICKET', 'Ticket'),
    ]
    for pat, label in type_patterns:
        if re.search(pat, text, re.IGNORECASE):
            result['document_type'] = label
            break

    # Date patterns
    date_match = re.search(
        r'(?:Fecha|Emisi[óo]n|Date)[:\s]*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})',
        text, re.IGNORECASE,
    )
    if date_match:
        d, m, y = date_match.group(1), date_match.group(2), date_match.group(3)
        result['issue_date'] = f'{y}-{m.zfill(2)}-{d.zfill(2)}'

    # Total amount
    total_match = re.search(
        r'(?:TOTAL|Total|IMPORTE\s+TOTAL)[:\s$]*\$?\s*([\d.,]+)',
        text, re.IGNORECASE,
    )
    if total_match:
        raw_amount = total_match.group(1)
        result['total_amount'] = _normalize_amount(raw_amount)

    # ── Names: CUIT-anchored extraction ──────────────────────────
    # Instead of splitting by doc-type header (unreliable with OCR),
    # use detected CUIT positions as anchors to find nearby name labels.
    issuer_cuit_raw = result.get('issuer_tax_id', '').replace('-', '')
    buyer_cuit_raw = result.get('buyer_tax_id', '').replace('-', '')

    lines = text.split('\n')
    cuit_word_re = re.compile(r'\b((?:20|23|24|27|30|33|34)\d{8}\d)\b')

    issuer_cuit_lines: list[int] = []
    buyer_cuit_lines: list[int] = []
    for i, line in enumerate(lines):
        clean = line.replace('-', '')
        for m in cuit_word_re.finditer(clean):
            val = m.group(1)
            if issuer_cuit_raw and val == issuer_cuit_raw and i not in issuer_cuit_lines:
                issuer_cuit_lines.append(i)
            if buyer_cuit_raw and val == buyer_cuit_raw and val != issuer_cuit_raw and i not in buyer_cuit_lines:
                buyer_cuit_lines.append(i)

    name_label_re = re.compile(
        r'(?:Apellido\s+y\s+Nombre[s]?\s*/?\s*)?'
        r'(?:Raz[oó]n\s+Social|Denominaci[oó]n)\s*:\s*(.+)',
        re.IGNORECASE,
    )

    # ── Buyer name: same line as buyer CUIT (AFIP standard layout) ──
    if buyer_cuit_lines:
        for bl in buyer_cuit_lines:
            m = name_label_re.search(lines[bl])
            if m:
                name = _clean_name(m.group(1))
                if _is_valid_name(name):
                    result['buyer_name'] = name
                    logger.info('[ocr] buyer_name (CUIT-anchored): %s', name)
                    break
            # Also check the next line (OCR sometimes splits long lines)
            if bl + 1 < len(lines):
                m = name_label_re.search(lines[bl + 1])
                if m:
                    name = _clean_name(m.group(1))
                    if _is_valid_name(name):
                        result['buyer_name'] = name
                        logger.info('[ocr] buyer_name (CUIT-anchored+1): %s', name)
                        break

    # ── Issuer name: search near issuer CUIT line (backward then forward) ──
    if issuer_cuit_lines:
        first_issuer_line = issuer_cuit_lines[0]
        buyer_boundary = buyer_cuit_lines[0] if buyer_cuit_lines else len(lines)

        # Backward search (primary — AFIP standard has name above CUIT)
        for i in range(first_issuer_line, max(-1, first_issuer_line - 10), -1):
            if i < 0:
                break
            m = name_label_re.search(lines[i])
            if m:
                name = _clean_name(m.group(1))
                if _is_valid_name(name):
                    result['issuer_name'] = name
                    logger.info('[ocr] issuer_name (CUIT-backward): %s', name)
                    break

        # Forward search (fallback — for non-standard layouts)
        if 'issuer_name' not in result:
            for i in range(first_issuer_line + 1, min(len(lines), first_issuer_line + 5)):
                if i >= buyer_boundary:
                    break  # Don't cross into buyer section
                m = name_label_re.search(lines[i])
                if m:
                    name = _clean_name(m.group(1))
                    if _is_valid_name(name):
                        result['issuer_name'] = name
                        logger.info('[ocr] issuer_name (CUIT-forward): %s', name)
                        break

    return result


# ── Name cleaning & validation ───────────────────────────────────────────

_LABEL_BOUNDARY_RE = re.compile(
    r'(?:'
    r'Fecha\s+de\s+Emisi[oó]n'
    r'|Fecha\s+de\s+Inicio'
    r'|Domicilio\s+Comercial'
    r'|Condici[oó]n\s+frente'
    r'|Ingresos\s+Brutos'
    r'|Punto\s+de\s+Venta'
    r'|Comp\.\s*Nro'
    r'|CUIT\s*:'
    r'|\d{2}/\d{2}/\d{4}'
    r')',
    re.IGNORECASE,
)

_CONTAMINATION_PATTERNS = [
    r'Fecha\s+de\s+Emisi[oó]n',
    r'Fecha\s+de\s+Inicio',
    r'Condici[oó]n\s+frente',
    r'Domicilio\s+Comercial',
    r'Ingresos\s+Brutos',
    r'Punto\s+de\s+Venta',
    r'IVA\s+Responsable',
    r'Comp\.\s*Nro',
    r'CUIT\s*:',
]


def _clean_name(raw: str) -> str:
    """Clean a raw name: trim at label boundaries, remove OCR artifacts."""
    # Trim at first metadata label boundary
    m = _LABEL_BOUNDARY_RE.search(raw)
    if m:
        raw = raw[:m.start()]

    # OCR artifact cleanup: brackets often replace letters
    name = re.sub(r'[\[\]]', '', raw)
    # Collapse multiple spaces
    name = re.sub(r'\s{2,}', ' ', name)

    return name.strip().rstrip(':- \t')


def _is_valid_name(name: str) -> bool:
    """Validate a name candidate — reject contaminated or nonsensical values."""
    if not name or len(name) < 3:
        return False
    if len(name) > 100:
        return False
    # Too many digits → likely a number/code, not a name
    if sum(c.isdigit() for c in name) > 3:
        return False
    # Contains known metadata labels → still contaminated
    for p in _CONTAMINATION_PATTERNS:
        if re.search(p, name, re.IGNORECASE):
            return False
    return True


def _normalize_amount(raw: str) -> str | None:
    """Normalize a currency amount string to decimal."""
    if ',' in raw and '.' in raw:
        last_comma = raw.rfind(',')
        last_dot = raw.rfind('.')
        if last_comma > last_dot:
            cleaned = raw.replace('.', '').replace(',', '.')
        else:
            cleaned = raw.replace(',', '')
    elif ',' in raw:
        cleaned = raw.replace(',', '.')
    else:
        cleaned = raw

    try:
        return str(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None

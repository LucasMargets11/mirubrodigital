"""
treasury/extractors.py — Document data extraction: QR-first, OCR-fallback.

Sprint 3: provides a clean interface for extracting structured data from
expense documents (PDFs and images).

Architecture:
  extract_qr()   → attempts QR code decoding (pyzbar)
  extract_ocr()  → attempts OCR text extraction (pytesseract)
  extract_document() → orchestrates QR-first, OCR-fallback, merges results
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# QR extraction
# ─────────────────────────────────────────────────────────────────────────────

def _images_from_file(file_path: str, mime_type: str) -> list[Image.Image]:
    """Load image(s) from a file path. PDFs are rasterized to images."""
    if mime_type == 'application/pdf':
        try:
            from pdf2image import convert_from_path
            return convert_from_path(file_path, dpi=300, fmt='png')
        except Exception as exc:
            logger.warning('pdf2image failed for %s: %s', file_path, exc)
            return []
    else:
        try:
            return [Image.open(file_path)]
        except Exception as exc:
            logger.warning('PIL.Image.open failed for %s: %s', file_path, exc)
            return []


def extract_qr(file_path: str, mime_type: str) -> dict[str, Any] | None:
    """
    Attempt to decode QR codes from a document file.

    Returns a dict with:
      - qr_payloads: list of decoded QR strings
      - parsed_fields: dict of structured fields extracted from AFIP QR URLs
    Or None if no QR found.
    """
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError:
        logger.error('pyzbar not installed — QR extraction unavailable')
        return None

    images = _images_from_file(file_path, mime_type)
    if not images:
        return None

    all_payloads: list[str] = []
    for img in images:
        try:
            decoded = pyzbar_decode(img)
            for obj in decoded:
                if obj.type == 'QRCODE' and obj.data:
                    payload = obj.data.decode('utf-8', errors='replace')
                    all_payloads.append(payload)
        except Exception as exc:
            logger.warning('pyzbar decode error: %s', exc)

    if not all_payloads:
        return None

    # Try to parse AFIP QR URL format
    parsed = _parse_afip_qr(all_payloads[0]) if all_payloads else {}

    return {
        'qr_payloads': all_payloads,
        'parsed_fields': parsed,
    }


def _parse_afip_qr(payload: str) -> dict[str, Any]:
    """
    Parse an AFIP QR code URL.

    AFIP QR URLs follow the pattern:
      https://www.afip.gob.ar/fe/qr/?p=BASE64_JSON

    The decoded JSON contains fields like:
      ver, fecha, cuit, ptoVta, tipoCmp, nroCmp, importe, moneda, ctz, ...
    """
    result: dict[str, Any] = {}

    # Pattern: AFIP QR URL with base64 payload
    afip_pattern = r'https?://www\.afip\.gob\.ar/fe/qr/\?p=([A-Za-z0-9+/=]+)'
    match = re.search(afip_pattern, payload)
    if match:
        import base64
        try:
            decoded_bytes = base64.b64decode(match.group(1))
            data = json.loads(decoded_bytes)
            result = _map_afip_fields(data)
            result['qr_payload'] = payload
            return result
        except Exception as exc:
            logger.debug('AFIP QR decode failed: %s', exc)

    # If not AFIP URL, try parsing as raw JSON
    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            result = _map_afip_fields(data)
            result['qr_payload'] = payload
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: store raw payload
    result['qr_payload'] = payload
    return result


# AFIP document type codes → human-friendly labels
_AFIP_DOC_TYPES = {
    1: 'Factura A', 2: 'Nota de Débito A', 3: 'Nota de Crédito A',
    6: 'Factura B', 7: 'Nota de Débito B', 8: 'Nota de Crédito B',
    11: 'Factura C', 12: 'Nota de Débito C', 13: 'Nota de Crédito C',
    51: 'Factura M',
    201: 'Factura de Crédito Electrónica A',
    206: 'Factura de Crédito Electrónica B',
    211: 'Factura de Crédito Electrónica C',
}


def _map_afip_fields(data: dict) -> dict[str, Any]:
    """Map AFIP QR JSON fields to normalized field names."""
    result: dict[str, Any] = {}

    if 'cuit' in data:
        cuit = str(data['cuit'])
        result['issuer_tax_id'] = cuit

    if 'fecha' in data:
        result['issue_date'] = str(data['fecha'])

    tipo_cmp = data.get('tipoCmp')
    if tipo_cmp is not None:
        result['document_type'] = _AFIP_DOC_TYPES.get(int(tipo_cmp), f'Tipo {tipo_cmp}')

    if 'ptoVta' in data and 'nroCmp' in data:
        pto = str(data['ptoVta']).zfill(5)
        nro = str(data['nroCmp']).zfill(8)
        result['document_number'] = f'{pto}-{nro}'

    if 'importe' in data:
        try:
            result['total_amount'] = str(Decimal(str(data['importe'])))
        except (InvalidOperation, ValueError):
            pass

    moneda = data.get('moneda')
    if moneda:
        currency_map = {'PES': 'ARS', 'DOL': 'USD', 'EUR': 'EUR'}
        result['currency'] = currency_map.get(str(moneda), str(moneda))

    if 'cuitRec' in data:
        result['buyer_tax_id'] = str(data['cuitRec'])

    return result


# ─────────────────────────────────────────────────────────────────────────────
# OCR extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_ocr(file_path: str, mime_type: str) -> dict[str, Any] | None:
    """
    Attempt OCR text extraction from a document file.

    Returns a dict with:
      - ocr_text: raw extracted text
      - parsed_fields: dict of structured fields inferred from text patterns
    Or None if OCR fails or produces no text.
    """
    try:
        import pytesseract
    except ImportError:
        logger.error('pytesseract not installed — OCR extraction unavailable')
        return None

    images = _images_from_file(file_path, mime_type)
    if not images:
        return None

    full_text_parts: list[str] = []
    for img in images:
        try:
            text = pytesseract.image_to_string(img, lang='spa+eng')
            if text and text.strip():
                full_text_parts.append(text.strip())
        except Exception as exc:
            logger.warning('pytesseract error: %s', exc)

    if not full_text_parts:
        return None

    full_text = '\n'.join(full_text_parts)
    parsed = _parse_ocr_text(full_text)

    return {
        'ocr_text': full_text,
        'parsed_fields': parsed,
    }


def _parse_ocr_text(text: str) -> dict[str, Any]:
    """
    Extract structured fields from OCR text using regex patterns.
    Best-effort — not all fields will be found in all documents.
    """
    result: dict[str, Any] = {}

    # CUIT pattern: 20-12345678-9 or 20123456789
    cuit_match = re.search(r'\b(20|23|24|27|30|33|34)\-?\d{8}\-?\d\b', text)
    if cuit_match:
        cuit_raw = cuit_match.group(0).replace('-', '')
        result['issuer_tax_id'] = f'{cuit_raw[:2]}-{cuit_raw[2:10]}-{cuit_raw[10:]}'

    # Document number patterns: 0001-00001234 or Nro: 0001-00001234
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

    # Date patterns: DD/MM/YYYY or DD-MM-YYYY
    date_match = re.search(
        r'(?:Fecha|Emisi[óo]n|Date)[:\s]*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})',
        text, re.IGNORECASE,
    )
    if date_match:
        d, m, y = date_match.group(1), date_match.group(2), date_match.group(3)
        result['issue_date'] = f'{y}-{m.zfill(2)}-{d.zfill(2)}'

    # Total amount: "Total: $ 1.234,56" or "TOTAL $1234.56"
    total_match = re.search(
        r'(?:TOTAL|Total|IMPORTE\s+TOTAL)[:\s$]*\$?\s*([\d.,]+)',
        text, re.IGNORECASE,
    )
    if total_match:
        raw_amount = total_match.group(1)
        result['total_amount'] = _normalize_amount(raw_amount)

    # Razón social / issuer name (line after "Razón Social:" or "RAZON SOCIAL:")
    issuer_match = re.search(
        r'(?:RAZ[ÓO]N\s+SOCIAL|Denominaci[oó]n)[:\s]*([^\n]{3,60})',
        text, re.IGNORECASE,
    )
    if issuer_match:
        result['issuer_name'] = issuer_match.group(1).strip()

    return result


def _normalize_amount(raw: str) -> str | None:
    """Normalize a currency amount string like '1.234,56' or '1234.56' to decimal."""
    # Argentine format: 1.234,56 → 1234.56
    if ',' in raw and '.' in raw:
        # Determine which is the decimal separator (last one)
        last_comma = raw.rfind(',')
        last_dot = raw.rfind('.')
        if last_comma > last_dot:
            # Argentine: 1.234,56
            cleaned = raw.replace('.', '').replace(',', '.')
        else:
            # US: 1,234.56
            cleaned = raw.replace(',', '')
    elif ',' in raw:
        # Only comma → decimal separator: 1234,56
        cleaned = raw.replace(',', '.')
    else:
        cleaned = raw

    try:
        return str(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator: QR-first, OCR-fallback
# ─────────────────────────────────────────────────────────────────────────────

def extract_document(file_path: str, mime_type: str) -> dict[str, Any]:
    """
    Extract data from a document file using QR-first, OCR-fallback strategy.

    Returns:
      {
        'extraction_source': 'qr' | 'ocr' | 'mixed' | 'none',
        'raw_extraction': { ... },       # raw data from source(s)
        'normalized_data': { ... },       # merged structured fields
        'errors': [ ... ],                # list of error strings if any
      }
    """
    errors: list[str] = []
    raw: dict[str, Any] = {}
    normalized: dict[str, Any] = {}
    source = 'none'

    # 1. Try QR first
    qr_result = None
    try:
        qr_result = extract_qr(file_path, mime_type)
    except Exception as exc:
        errors.append(f'QR extraction error: {exc}')
        logger.exception('QR extraction failed for %s', file_path)

    if qr_result:
        raw['qr'] = qr_result
        normalized.update(qr_result.get('parsed_fields', {}))
        source = 'qr'

    # 2. OCR fallback (or complement)
    # Run OCR if QR didn't find all key fields
    needs_ocr = (
        not qr_result
        or not normalized.get('issuer_tax_id')
        or not normalized.get('total_amount')
    )

    ocr_result = None
    if needs_ocr:
        try:
            ocr_result = extract_ocr(file_path, mime_type)
        except Exception as exc:
            errors.append(f'OCR extraction error: {exc}')
            logger.exception('OCR extraction failed for %s', file_path)

    if ocr_result:
        raw['ocr'] = ocr_result
        ocr_fields = ocr_result.get('parsed_fields', {})

        if source == 'qr':
            # Merge: OCR fills gaps not covered by QR
            for key, val in ocr_fields.items():
                if key not in normalized or not normalized[key]:
                    normalized[key] = val
            source = 'mixed'
        else:
            normalized.update(ocr_fields)
            source = 'ocr'

    # 3. Infer confidence
    key_fields = ['issuer_tax_id', 'document_number', 'total_amount', 'issue_date']
    found = sum(1 for f in key_fields if normalized.get(f))
    normalized['inferred_source_confidence'] = (
        'high' if found >= 3 else 'medium' if found >= 2 else 'low'
    )

    return {
        'extraction_source': source,
        'raw_extraction': raw,
        'normalized_data': normalized,
        'errors': errors,
    }

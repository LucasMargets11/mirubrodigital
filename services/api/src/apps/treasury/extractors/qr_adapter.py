"""
treasury/extractors/qr_adapter.py — QR code extraction adapter.

Reads QR codes from images/PDFs using pyzbar, parses AFIP QR URL format.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .base import BaseExtractor, ExtractionResult
from .image_utils import images_from_file

logger = logging.getLogger(__name__)

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


class QRExtractor(BaseExtractor):
    """QR code extractor — attempts pyzbar decode + AFIP QR URL parsing."""

    name = 'qr'

    def is_available(self) -> bool:
        try:
            from pyzbar.pyzbar import decode  # noqa: F401
            return True
        except ImportError:
            return False

    def extract(self, file_data: bytes, mime_type: str) -> ExtractionResult:
        if not self.is_available():
            return ExtractionResult(
                source='qr',
                success=False,
                errors=['pyzbar not installed — QR extraction unavailable'],
            )

        try:
            from pyzbar.pyzbar import decode as pyzbar_decode
        except ImportError:
            return ExtractionResult(
                source='qr', success=False,
                errors=['pyzbar import failed'],
            )

        images = images_from_file(file_data, mime_type)
        if not images:
            return ExtractionResult(
                source='qr', success=False,
                errors=['No images could be loaded from file'],
            )

        all_payloads: list[str] = []
        errors: list[str] = []

        for idx, img in enumerate(images):
            try:
                decoded = pyzbar_decode(img)
                for obj in decoded:
                    if obj.type == 'QRCODE' and obj.data:
                        payload = obj.data.decode('utf-8', errors='replace')
                        all_payloads.append(payload)
            except Exception as exc:
                errors.append(f'pyzbar decode error on page {idx}: {exc}')
                logger.warning('pyzbar decode error on page %d: %s', idx, exc)

        if not all_payloads:
            return ExtractionResult(
                source='qr', success=False,
                errors=errors or ['No QR codes found in document'],
            )

        # Parse AFIP QR from first payload
        parsed = _parse_afip_qr(all_payloads[0])

        raw_data = {
            'qr_payloads': all_payloads,
            'parsed_fields': parsed,
        }

        return ExtractionResult(
            source='qr',
            success=True,
            raw_data=raw_data,
            parsed_fields=parsed,
            errors=errors,
            metadata={'qr_count': len(all_payloads)},
        )


def _parse_afip_qr(payload: str) -> dict[str, Any]:
    """Parse an AFIP QR code URL or raw JSON payload."""
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


def _map_afip_fields(data: dict) -> dict[str, Any]:
    """Map AFIP QR JSON fields to normalized field names."""
    result: dict[str, Any] = {}

    if 'cuit' in data:
        result['issuer_tax_id'] = str(data['cuit'])

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

    # AFIP QR v2 format: tipoDocRec + nroDocRec (used when cuitRec is absent)
    # tipoDocRec: 80=CUIT, 86=CUIL, 96=DNI, 99=CF, etc.
    if not result.get('buyer_tax_id'):
        nro_doc_rec = data.get('nroDocRec')
        tipo_doc_rec = data.get('tipoDocRec')
        if nro_doc_rec is not None and nro_doc_rec != 0:
            result['buyer_tax_id'] = str(nro_doc_rec)
            logger.info(
                '[qr] buyer_tax_id from nroDocRec=%s (tipoDocRec=%s)',
                nro_doc_rec, tipo_doc_rec,
            )

    return result

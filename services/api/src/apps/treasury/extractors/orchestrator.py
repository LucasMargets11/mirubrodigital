"""
treasury/extractors/orchestrator.py — QR-first, OCR-fallback extraction orchestrator.

Coordinates multiple extractors and merges their results into a unified
extraction output ready for normalization.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import ExtractionResult
from .qr_adapter import QRExtractor
from .ocr_adapter import OCRExtractor
from .text_adapter import TextLayerExtractor

logger = logging.getLogger(__name__)

# Singleton instances — stateless, safe to reuse
_qr_extractor = QRExtractor()
_text_extractor = TextLayerExtractor()
_ocr_extractor = OCRExtractor()


class DocumentExtractionOrchestrator:
    """
    Orchestrates QR-first, OCR-fallback extraction.

    Strategy:
    1. Try QR extraction
    2. If QR fails or misses key fields → run OCR
    3. Merge results (QR takes priority, OCR fills gaps)
    4. Return unified raw + parsed fields + source attribution
    """

    KEY_FIELDS = ('issuer_tax_id', 'total_amount', 'document_number', 'issue_date')

    def __init__(
        self,
        qr_extractor: QRExtractor | None = None,
        text_extractor: TextLayerExtractor | None = None,
        ocr_extractor: OCRExtractor | None = None,
    ):
        self.qr = qr_extractor or _qr_extractor
        self.text = text_extractor or _text_extractor
        self.ocr = ocr_extractor or _ocr_extractor

    def extract(self, file_data: bytes, mime_type: str) -> dict[str, Any]:
        """
        Run the full extraction pipeline.

        Args:
            file_data: Raw file content as bytes (storage-agnostic).
            mime_type: MIME type of the file.

        Returns:
          {
            'extraction_source': 'qr' | 'ocr' | 'mixed' | 'none',
            'raw_extraction': { 'qr': {...}, 'ocr': {...} },
            'parsed_fields': { ... },
            'errors': [ ... ],
            'metadata': { 'qr': {...}, 'ocr': {...} },
          }
        """
        errors: list[str] = []
        raw: dict[str, Any] = {}
        merged_fields: dict[str, Any] = {}
        metadata: dict[str, Any] = {}
        source = 'none'

        # ── Step 1: QR ────────────────────────────────────────────
        qr_result: ExtractionResult | None = None
        try:
            qr_result = self.qr.extract(file_data, mime_type)
        except Exception as exc:
            errors.append(f'QR extraction error: {exc}')
            logger.exception('QR extraction failed')

        if qr_result:
            if qr_result.errors:
                errors.extend(qr_result.errors)
            if qr_result.success:
                raw['qr'] = qr_result.raw_data
                merged_fields.update(qr_result.parsed_fields)
                metadata['qr'] = qr_result.metadata
                source = 'qr'

        # ── Step 2: Text layer (PDFs only — cleaner than OCR) ─────
        text_result: ExtractionResult | None = None
        if mime_type == 'application/pdf':
            try:
                text_result = self.text.extract(file_data, mime_type)
            except Exception as exc:
                errors.append(f'Text-layer extraction error: {exc}')
                logger.exception('Text-layer extraction failed')

        if text_result:
            if text_result.errors:
                errors.extend(text_result.errors)
            if text_result.success:
                raw['text_layer'] = text_result.raw_data
                metadata['text_layer'] = text_result.metadata
                text_fields = text_result.parsed_fields

                if source == 'qr':
                    # Merge: text-layer fills gaps not covered by QR
                    for key, val in text_fields.items():
                        if key not in merged_fields or not merged_fields[key]:
                            merged_fields[key] = val
                    source = 'mixed'
                else:
                    merged_fields.update(text_fields)
                    source = 'text_layer'

        # ── Step 3: OCR (fallback or complement) ──────────────────
        needs_ocr = (
            not qr_result
            or not qr_result.success
        ) and (
            not text_result
            or not text_result.success
        ) or (
            not merged_fields.get('issuer_tax_id')
            or not merged_fields.get('total_amount')
            or not merged_fields.get('issuer_name')
            or not merged_fields.get('buyer_tax_id')
        )

        ocr_result: ExtractionResult | None = None
        if needs_ocr:
            try:
                ocr_result = self.ocr.extract(file_data, mime_type)
            except Exception as exc:
                errors.append(f'OCR extraction error: {exc}')
                logger.exception('OCR extraction failed')

        if ocr_result:
            if ocr_result.errors:
                errors.extend(ocr_result.errors)
            if ocr_result.success:
                raw['ocr'] = ocr_result.raw_data
                metadata['ocr'] = ocr_result.metadata
                ocr_fields = ocr_result.parsed_fields

                if source in ('qr', 'mixed', 'text_layer'):
                    # Merge: OCR fills gaps not covered by prior sources
                    for key, val in ocr_fields.items():
                        if key not in merged_fields or not merged_fields[key]:
                            merged_fields[key] = val
                    source = 'mixed'
                else:
                    merged_fields.update(ocr_fields)
                    source = 'ocr'

        # ── Step 4: Source-priority tracking per field ─────────────
        source_priority: dict[str, str] = {}
        if qr_result and qr_result.success:
            for key in qr_result.parsed_fields:
                if qr_result.parsed_fields.get(key):
                    source_priority[key] = 'qr'
        if text_result and text_result.success:
            for key in text_result.parsed_fields:
                if text_result.parsed_fields.get(key) and key not in source_priority:
                    source_priority[key] = 'text_layer'
        if ocr_result and ocr_result.success:
            for key in ocr_result.parsed_fields:
                if ocr_result.parsed_fields.get(key) and key not in source_priority:
                    source_priority[key] = 'ocr'
        merged_fields['_source_priority'] = source_priority

        # ── Step 5: Confidence ────────────────────────────────────
        found = sum(1 for f in self.KEY_FIELDS if merged_fields.get(f))
        merged_fields['inferred_source_confidence'] = (
            'high' if found >= 3 else 'medium' if found >= 2 else 'low'
        )

        return {
            'extraction_source': source,
            'raw_extraction': raw,
            'parsed_fields': merged_fields,
            'errors': errors,
            'metadata': metadata,
        }


def extract_document(file_data: bytes, mime_type: str) -> dict[str, Any]:
    """
    Convenience function — backward-compatible shape with Sprint 3 callers.

    Args:
        file_data: Raw file content as bytes (storage-agnostic).
        mime_type: MIME type of the file.

    Returns the same shape as Sprint 3's extract_document() plus enhanced metadata.
    The normalized_data key is built here for backward compat; the real
    normalization is done in normalizer.py.
    """
    orchestrator = DocumentExtractionOrchestrator()
    result = orchestrator.extract(file_data, mime_type)

    # Map to Sprint 3 expected shape for backward compatibility
    return {
        'extraction_source': result['extraction_source'],
        'raw_extraction': result['raw_extraction'],
        'normalized_data': {
            k: v for k, v in result['parsed_fields'].items()
            if k != '_source_priority'
        },
        'errors': result['errors'],
        'metadata': result.get('metadata', {}),
        '_source_priority': result['parsed_fields'].get('_source_priority', {}),
    }

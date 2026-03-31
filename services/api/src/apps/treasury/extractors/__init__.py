"""
treasury/extractors/ — Adapter-based document extraction package.

Sprint 5: refactored from monolithic extractors.py into adapter pattern.
Each extractor implements BaseExtractor and can be swapped independently.

Backward-compatible re-exports for Sprint 3 callers/tests.
"""
from .base import BaseExtractor, ExtractionResult
from .qr_adapter import QRExtractor, _parse_afip_qr, _map_afip_fields
from .ocr_adapter import OCRExtractor, _parse_ocr_text, _normalize_amount, _clean_name, _is_valid_name
from .text_adapter import TextLayerExtractor
from .orchestrator import DocumentExtractionOrchestrator, extract_document

# Legacy re-exports — Sprint 3 tests use these directly
# Note: extract_qr/extract_ocr now accept (file_data: bytes, mime_type: str)
extract_qr = QRExtractor().extract
extract_ocr = OCRExtractor().extract

__all__ = [
    'BaseExtractor',
    'ExtractionResult',
    'QRExtractor',
    'OCRExtractor',
    'DocumentExtractionOrchestrator',
    'extract_document',
    # Legacy re-exports
    'extract_qr',
    'extract_ocr',
    '_parse_afip_qr',
    '_map_afip_fields',
    '_parse_ocr_text',
    '_normalize_amount',
]

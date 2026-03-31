"""
treasury/extractors/text_adapter.py — PDF text-layer extraction adapter.

Extracts embedded text from PDFs via pdftotext (poppler-utils).
Preferred over OCR when the PDF has a text layer — produces cleaner text
without OCR artifacts like garbled characters.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import Any

from .base import BaseExtractor, ExtractionResult

logger = logging.getLogger(__name__)


class TextLayerExtractor(BaseExtractor):
    """PDF text-layer extractor — pdftotext with layout preservation."""

    name = 'text_layer'

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                ['pdftotext', '-v'],
                capture_output=True, timeout=5,
            )
            # pdftotext -v writes version info to stderr
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def extract(self, file_data: bytes, mime_type: str) -> ExtractionResult:
        if mime_type != 'application/pdf':
            return ExtractionResult(
                source='text_layer', success=False,
                errors=['Text-layer extraction only supports PDF files'],
            )

        if not self.is_available():
            return ExtractionResult(
                source='text_layer', success=False,
                errors=['pdftotext not installed'],
            )

        try:
            text = _pdftotext(file_data)
        except Exception as exc:
            logger.warning('[text_layer] pdftotext failed: %s', exc)
            return ExtractionResult(
                source='text_layer', success=False,
                errors=[f'pdftotext failed: {exc}'],
            )

        if not text or len(text.strip()) < 50:
            logger.info(
                '[text_layer] PDF has no meaningful text layer (%d chars)',
                len(text or ''),
            )
            return ExtractionResult(
                source='text_layer', success=False,
                errors=['PDF has no meaningful text layer'],
            )

        # Use only the first copy (ORIGINAL) of multi-copy AFIP documents
        first_copy = _first_copy_text(text)
        logger.info(
            '[text_layer] Extracted %d chars (first copy: %d chars)',
            len(text), len(first_copy),
        )

        from .ocr_adapter import _parse_ocr_text
        parsed = _parse_ocr_text(first_copy)

        return ExtractionResult(
            source='text_layer',
            success=True,
            raw_data={'text_layer': first_copy},
            parsed_fields=parsed,
            errors=[],
            metadata={
                'chars': len(first_copy),
                'full_chars': len(text),
                'source': 'pdftotext',
            },
        )


def _pdftotext(file_data: bytes) -> str:
    """Run pdftotext on raw PDF bytes, returning extracted text."""
    fd, path = tempfile.mkstemp(suffix='.pdf')
    try:
        os.write(fd, file_data)
        os.close(fd)
        result = subprocess.run(
            ['pdftotext', '-layout', path, '-'],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='replace')
            raise RuntimeError(
                f'pdftotext exited {result.returncode}: {stderr}',
            )
        return result.stdout.decode('utf-8', errors='replace')
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _first_copy_text(text: str) -> str:
    """Return only the first copy (ORIGINAL) of multi-copy AFIP documents.

    AFIP facturas typically contain ORIGINAL/DUPLICADO/TRIPLICADO sections.
    We only need the first one to avoid duplicate regex matches.
    """
    earliest = len(text)
    for marker in ('DUPLICADO', 'TRIPLICADO', 'CUADRUPLICADO'):
        idx = text.find(marker)
        if 200 < idx < earliest:
            earliest = idx
    if earliest < len(text):
        return text[:earliest].strip()
    return text

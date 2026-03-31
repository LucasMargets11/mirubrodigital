"""
treasury/extractors/base.py — Base adapter interface for document extractors.

All extractors (QR, OCR, future providers) implement this interface.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Standardized result from any extractor."""
    source: str  # 'qr', 'ocr', etc.
    success: bool
    raw_data: dict[str, Any] = field(default_factory=dict)
    parsed_fields: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)  # pages, confidence, etc.


class BaseExtractor:
    """
    Abstract base for document data extractors.

    Subclasses must implement `extract(file_path, mime_type)`.
    """

    name: str = 'base'

    def extract(self, file_data: bytes, mime_type: str) -> ExtractionResult:
        """
        Extract data from a document's raw bytes.

        Args:
            file_data: Raw file content as bytes (storage-agnostic).
            mime_type: MIME type of the file.

        Returns:
            ExtractionResult with source, success flag, raw data, parsed fields, errors.
        """
        raise NotImplementedError

    def is_available(self) -> bool:
        """Check if this extractor's dependencies are installed and ready."""
        return True

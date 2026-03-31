"""
treasury/extractors/image_utils.py — Shared image loading utilities for extractors.

Accepts raw bytes so the pipeline works with any Django storage backend
(local filesystem, S3, GCS, Azure Blob, etc.).
"""
from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image

logger = logging.getLogger(__name__)


def images_from_file(file_data: bytes, mime_type: str) -> list[Image.Image]:
    """Load image(s) from raw bytes. PDFs are rasterized to images."""
    if not isinstance(file_data, (bytes, bytearray)):
        logger.error(
            '[image_utils] images_from_file received %s instead of bytes — '
            'this is a bug in the caller. Value preview: %.100r',
            type(file_data).__name__, file_data,
        )
        return []

    data_size = len(file_data)

    if mime_type == 'application/pdf':
        logger.info(
            '[image_utils] Converting PDF to images (%d bytes) via pdf2image...',
            data_size,
        )
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(file_data, dpi=300, fmt='png')
            logger.info(
                '[image_utils] PDF conversion successful: %d page(s) extracted',
                len(images),
            )
            return images
        except Exception as exc:
            logger.error(
                '[image_utils] pdf2image convert_from_bytes failed (%d bytes): %s',
                data_size, exc,
                exc_info=True,
            )
            return []
    else:
        logger.info(
            '[image_utils] Opening image (%d bytes, mime=%s) via PIL...',
            data_size, mime_type,
        )
        try:
            img = Image.open(BytesIO(file_data))
            logger.info(
                '[image_utils] Image opened: %s, size=%s, mode=%s',
                img.format, img.size, img.mode,
            )
            return [img]
        except Exception as exc:
            logger.error(
                '[image_utils] PIL.Image.open failed (%d bytes, mime=%s): %s',
                data_size, mime_type, exc,
                exc_info=True,
            )
            return []

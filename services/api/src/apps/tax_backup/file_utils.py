"""
tax_backup/file_utils.py — Centralized file access for local and storage backends.

Provides a single point to resolve file bytes from a Django FileField,
whether the file is stored locally on disk or via Django's default storage.
No S3/cloud dependency — designed for local-first development.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import NamedTuple

from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


class ResolvedFile(NamedTuple):
    """Result of resolving a Django FileField to usable data."""
    file_bytes: bytes
    local_path: str | None   # absolute path if available on disk
    mime_type: str
    size: int


# MIME type detection by extension
_EXT_MIME = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
}


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from file extension."""
    ext = os.path.splitext(filename)[1].lower()
    return _EXT_MIME.get(ext, 'application/octet-stream')


def resolve_file_field(file_field) -> ResolvedFile | None:
    """
    Given a Django FileField value, resolve it to bytes + metadata.

    Tries (in order):
    1. file_field.path — direct local path if storage supports it
    2. file_field.read() — reads via Django storage backend

    Returns None if the file cannot be read.
    """
    if not file_field or not file_field.name:
        logger.warning("[file_utils] resolve_file_field called with empty FileField")
        return None

    filename = file_field.name
    mime_type = guess_mime_type(filename)

    # Strategy 1: try local path (works with FileSystemStorage)
    local_path = _try_local_path(file_field)
    if local_path and os.path.isfile(local_path):
        try:
            with open(local_path, 'rb') as f:
                data = f.read()
            size = len(data)
            logger.info(
                "[file_utils] Resolved file via local path: %s (%d bytes, mime=%s)",
                local_path, size, mime_type,
            )
            return ResolvedFile(
                file_bytes=data,
                local_path=local_path,
                mime_type=mime_type,
                size=size,
            )
        except (IOError, OSError) as exc:
            logger.warning(
                "[file_utils] Local path exists but read failed: %s — %s",
                local_path, exc,
            )

    # Strategy 2: read via Django storage backend
    try:
        file_field.open('rb')
        data = file_field.read()
        file_field.close()
        size = len(data)
        logger.info(
            "[file_utils] Resolved file via storage.read(): %s (%d bytes, mime=%s)",
            filename, size, mime_type,
        )
        return ResolvedFile(
            file_bytes=data,
            local_path=local_path,
            mime_type=mime_type,
            size=size,
        )
    except Exception as exc:
        logger.error(
            "[file_utils] Failed to read file via storage: %s — %s",
            filename, exc,
            exc_info=True,
        )

    return None


def _try_local_path(file_field) -> str | None:
    """Try to get the absolute local filesystem path from a FileField."""
    try:
        return file_field.path
    except NotImplementedError:
        # Storage backend doesn't support .path (e.g., S3)
        return None
    except Exception:
        return None

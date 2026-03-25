"""
treasury/file_validation.py — Centralized file validation for expense documents.

Sprint 3: extracted from duplicated validate_file() across serializers.
Validates content_type (with optional magic-byte hardening), file size,
and provides a single reusable entry point.
"""
from rest_framework import serializers

from .models import EXPENSE_DOCUMENT_ALLOWED_TYPES, EXPENSE_DOCUMENT_MAX_SIZE_BYTES

# Magic byte signatures for the allowed MIME types.
# Used as a secondary check when the file is large enough to inspect.
_MAGIC_SIGNATURES = {
    'application/pdf': [b'%PDF'],
    'image/jpeg': [b'\xff\xd8\xff'],
    'image/png': [b'\x89PNG'],
    'image/webp': [b'RIFF'],  # RIFF....WEBP
}


def validate_expense_document_file(file_obj):
    """
    Validate an uploaded file for the expense document pipeline.

    Checks:
    1. content_type is in the allowlist
    2. file size does not exceed the maximum
    3. magic bytes match the declared content_type (best-effort hardening)

    Returns the file object if valid, raises serializers.ValidationError otherwise.
    """
    # 1. Content-type allowlist
    if file_obj.content_type not in EXPENSE_DOCUMENT_ALLOWED_TYPES:
        allowed = ', '.join(sorted(EXPENSE_DOCUMENT_ALLOWED_TYPES))
        raise serializers.ValidationError(
            f'Tipo de archivo no permitido ({file_obj.content_type}). Permitidos: {allowed}'
        )

    # 2. Size limit
    if file_obj.size > EXPENSE_DOCUMENT_MAX_SIZE_BYTES:
        max_mb = EXPENSE_DOCUMENT_MAX_SIZE_BYTES / (1024 * 1024)
        raise serializers.ValidationError(
            f'El archivo excede el tamaño máximo permitido ({max_mb:.0f} MB).'
        )

    # 3. Magic-byte hardening (best-effort, no external dependency)
    signatures = _MAGIC_SIGNATURES.get(file_obj.content_type, [])
    if signatures:
        try:
            pos = file_obj.tell()
            header = file_obj.read(16)
            file_obj.seek(pos)
            if header and not any(header.startswith(sig) for sig in signatures):
                raise serializers.ValidationError(
                    'El contenido del archivo no coincide con el tipo declarado '
                    f'({file_obj.content_type}).'
                )
        except (OSError, AttributeError):
            pass  # If we can't read, skip magic check — content_type still validated

    return file_obj

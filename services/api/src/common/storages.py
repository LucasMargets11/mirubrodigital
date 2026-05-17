from __future__ import annotations

from django.conf import settings


def public_media_storage():
    """
    Callable storage for public-facing image fields only:
      - menu/items/
      - menu/categories/
      - menu/branding/logos/
      - business/logos/

    Returns S3Boto3Storage when AWS_STORAGE_BUCKET_NAME is set in settings,
    otherwise falls back to the default FileSystemStorage (local dev, CI).

    Intentionally NOT used for invoices/, treasury/, or tax_backup/ — those
    fields stay on the default (filesystem) storage regardless of this setting.
    """
    bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '')
    if bucket:
        from storages.backends.s3boto3 import S3Boto3Storage
        return S3Boto3Storage()
    from django.core.files.storage import FileSystemStorage
    return FileSystemStorage(
        location=settings.MEDIA_ROOT,
        base_url=settings.MEDIA_URL,
    )

"""
Tests unitarios para resolve_document_logo_path.

Cubre:
- campo None devuelve None
- campo sin nombre devuelve None
- SVG devuelve None
- FileSystemStorage devuelve path str
- S3Storage (NotImplementedError en .path) usa storage.open y devuelve BytesIO
- ValueError en .path también usa storage.open
- storage.open falla → devuelve None y loguea warning
"""
from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, PropertyMock, patch

from django.test import TestCase


class ResolveDocumentLogoPathTests(TestCase):
    """Tests unitarios para apps.business.services.resolve_document_logo_path."""

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_field(name: str, path_value=None, path_exc=None, storage=None):
        """
        Crea un mock de ImageFieldFile.

        path_value: valor que devuelve .path (str).
        path_exc:   excepción que lanza .path cuando se accede.
        storage:    mock de storage, o None.
        """
        field = MagicMock()
        field.name = name
        if path_exc is not None:
            type(field).path = PropertyMock(side_effect=path_exc)
        elif path_value is not None:
            type(field).path = PropertyMock(return_value=path_value)
        if storage is not None:
            field.storage = storage
        return field

    @staticmethod
    def _mock_storage_open(data: bytes):
        """Devuelve un mock de storage con .open() que retorna `data`."""
        storage = MagicMock()
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=data)))
        cm.__exit__ = MagicMock(return_value=False)
        storage.open.return_value = cm
        return storage

    # ── casos None/vacíos ────────────────────────────────────────────────────

    def test_none_field_returns_none(self):
        from apps.business.services import resolve_document_logo_path
        self.assertIsNone(resolve_document_logo_path(None))

    def test_falsy_field_returns_none(self):
        """Cualquier valor falsy (string vacío, 0, False) devuelve None."""
        from apps.business.services import resolve_document_logo_path
        self.assertIsNone(resolve_document_logo_path(''))
        self.assertIsNone(resolve_document_logo_path(0))

    def test_field_with_empty_name_returns_none(self):
        from apps.business.services import resolve_document_logo_path
        field = self._make_field(name='')
        self.assertIsNone(resolve_document_logo_path(field))

    # ── SVG ──────────────────────────────────────────────────────────────────

    def test_svg_extension_returns_none(self):
        from apps.business.services import resolve_document_logo_path
        for svg_name in (
            'logos/brand.svg',
            'business/logos/icon.SVG',
            'LOGO.Svg',
        ):
            with self.subTest(name=svg_name):
                field = self._make_field(name=svg_name, path_value='/any/path.svg')
                self.assertIsNone(resolve_document_logo_path(field))

    # ── FileSystemStorage (devuelve path) ────────────────────────────────────

    def test_filesystem_storage_returns_path_string(self):
        from apps.business.services import resolve_document_logo_path
        field = self._make_field(
            name='logos/my_logo.png',
            path_value='/srv/media/logos/my_logo.png',
        )
        result = resolve_document_logo_path(field)
        self.assertEqual(result, '/srv/media/logos/my_logo.png')

    def test_filesystem_jpg_returns_path_string(self):
        from apps.business.services import resolve_document_logo_path
        field = self._make_field(
            name='logos/brand.jpg',
            path_value='/media/logos/brand.jpg',
        )
        result = resolve_document_logo_path(field)
        self.assertEqual(result, '/media/logos/brand.jpg')

    # ── S3Boto3Storage — NotImplementedError en .path ─────────────────────────

    def test_s3_not_implemented_error_uses_storage_open(self):
        """S3 lanza NotImplementedError en .path → debe usar storage.open."""
        from apps.business.services import resolve_document_logo_path

        png_bytes = b'\x89PNG\r\n\x1a\nfakedata'
        storage = self._mock_storage_open(png_bytes)
        field = self._make_field(
            name='business/logos/brand.png',
            path_exc=NotImplementedError('S3 has no local path'),
            storage=storage,
        )

        result = resolve_document_logo_path(field)

        self.assertIsInstance(result, BytesIO)
        self.assertEqual(result.read(), png_bytes)
        storage.open.assert_called_once_with('business/logos/brand.png', 'rb')

    def test_s3_value_error_uses_storage_open(self):
        """ValueError en .path también debe caer al fallback de storage.open."""
        from apps.business.services import resolve_document_logo_path

        png_bytes = b'\x89PNG\r\n\x1a\nfakedata2'
        storage = self._mock_storage_open(png_bytes)
        field = self._make_field(
            name='logos/icon.png',
            path_exc=ValueError('storage does not support path'),
            storage=storage,
        )

        result = resolve_document_logo_path(field)

        self.assertIsInstance(result, BytesIO)
        self.assertEqual(result.read(), png_bytes)

    def test_bytesio_is_seeked_to_zero(self):
        """El BytesIO devuelto debe estar en posición 0."""
        from apps.business.services import resolve_document_logo_path

        png_bytes = b'\x89PNG\r\n\x1a\nmoredata'
        storage = self._mock_storage_open(png_bytes)
        field = self._make_field(
            name='logos/logo.png',
            path_exc=NotImplementedError(),
            storage=storage,
        )

        result = resolve_document_logo_path(field)
        self.assertEqual(result.tell(), 0)

    # ── Fallos de storage.open ───────────────────────────────────────────────

    def test_storage_open_failure_returns_none(self):
        """Si storage.open lanza excepción, retorna None."""
        from apps.business.services import resolve_document_logo_path

        storage = MagicMock()
        storage.open.side_effect = Exception('Connection timeout')
        field = self._make_field(
            name='logos/brand.png',
            path_exc=NotImplementedError(),
            storage=storage,
        )

        result = resolve_document_logo_path(field)
        self.assertIsNone(result)

    def test_storage_open_failure_logs_warning(self):
        """Si storage.open falla, se loguea un warning con exc_info."""
        from apps.business.services import resolve_document_logo_path

        storage = MagicMock()
        storage.open.side_effect = OSError('S3 unreachable')
        field = self._make_field(
            name='logos/brand.png',
            path_exc=NotImplementedError(),
            storage=storage,
        )

        with patch('apps.business.services.logger') as mock_logger:
            resolve_document_logo_path(field)

        mock_logger.warning.assert_called()
        # Verificar que exc_info=True fue pasado
        call_kwargs = mock_logger.warning.call_args[1]
        self.assertTrue(call_kwargs.get('exc_info'))

    def test_no_storage_attribute_returns_none(self):
        """Si no hay atributo storage (además de .path fallando), retorna None."""
        from apps.business.services import resolve_document_logo_path

        field = MagicMock(spec=[])  # sin ningún atributo
        field.name = 'logos/logo.png'
        type(field).path = PropertyMock(side_effect=NotImplementedError())
        # getattr(field, 'storage', None) devolverá None por el spec=[]

        with patch('apps.business.services.logger'):
            result = resolve_document_logo_path(field)

        self.assertIsNone(result)

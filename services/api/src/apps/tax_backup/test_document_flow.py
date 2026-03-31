"""
Respaldo Impositivo — Document upload, processing, delete & profile consistency tests.

Covers the full flow fixed in the bytes-vs-str sprint:
  1. Upload PDF → document created with file on disk
  2. Processing resolves bytes correctly (no str leak)
  3. Delete removes document + physical file + recalculates profile
  4. Profile state stays consistent after add/remove

Run with:
    python manage.py test apps.tax_backup.test_document_flow
"""
import os
from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.business.models import Business
from apps.treasury.models import Expense
from apps.treasury.extractors.qr_adapter import QRExtractor
from apps.treasury.extractors.ocr_adapter import OCRExtractor
from apps.treasury.extractors.text_adapter import TextLayerExtractor

from apps.tax_backup.models import (
    AllocationType,
    ExpenseFiscalProfile,
    FiscalDocument,
    FiscalStatus,
    ParseStatus,
    SourceType,
    TaxStatus,
)
from apps.tax_backup.file_utils import resolve_file_field, guess_mime_type, ResolvedFile


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_business(name='DocFlow Biz'):
    b, _ = Business.objects.get_or_create(
        name=name, defaults={'slug': name.lower().replace(' ', '-')},
    )
    return b


def _make_expense(business, amount=Decimal('1000')):
    return Expense.objects.create(
        business=business, name='Gasto test', amount=amount, due_date=date.today(),
    )


def _make_profile(business, expense=None, **kw):
    if expense is None:
        expense = _make_expense(business)
    defaults = {
        'business': business,
        'expense': expense,
        'source_type': SourceType.EXPENSE,
        'allocation_type': AllocationType.BUSINESS,
    }
    defaults.update(kw)
    return ExpenseFiscalProfile.objects.create(**defaults)


def _make_pdf_file(name='test.pdf', size=2048):
    """SimpleUploadedFile with a valid-ish PDF header."""
    return SimpleUploadedFile(name, b'%PDF-1.4 ' + b'\x00' * (size - 9), content_type='application/pdf')


def _make_image_file(name='test.png'):
    """Minimal 1×1 PNG."""
    png = (
        b'\x89PNG\r\n\x1a\n'
        b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
        b'\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N'
        b'\x00\x00\x00\x00IEND\xaeB\x60\x82'
    )
    return SimpleUploadedFile(name, png, content_type='image/png')


# ─────────────────────────────────────────────────────────────────────────
# 1. file_utils — guess_mime_type
# ─────────────────────────────────────────────────────────────────────────

class GuessMimeTypeTest(TestCase):
    def test_pdf(self):
        self.assertEqual(guess_mime_type('factura.pdf'), 'application/pdf')

    def test_jpg(self):
        self.assertEqual(guess_mime_type('foto.jpg'), 'image/jpeg')

    def test_jpeg(self):
        self.assertEqual(guess_mime_type('foto.jpeg'), 'image/jpeg')

    def test_png(self):
        self.assertEqual(guess_mime_type('ticket.png'), 'image/png')

    def test_webp(self):
        self.assertEqual(guess_mime_type('scan.webp'), 'image/webp')

    def test_unknown_extension(self):
        self.assertEqual(guess_mime_type('data.xyz'), 'application/octet-stream')

    def test_case_insensitive(self):
        self.assertEqual(guess_mime_type('FACTURA.PDF'), 'application/pdf')


# ─────────────────────────────────────────────────────────────────────────
# 2. file_utils — resolve_file_field (local storage)
# ─────────────────────────────────────────────────────────────────────────

class ResolveFileFieldTest(TestCase):
    def test_returns_none_for_empty_field(self):
        self.assertIsNone(resolve_file_field(None))

    def test_returns_none_for_field_without_name(self):
        mock_field = MagicMock()
        mock_field.name = ''
        self.assertIsNone(resolve_file_field(mock_field))

    def test_resolves_pdf_from_local_storage(self):
        """A FiscalDocument with a real file on disk resolves to bytes."""
        biz = _make_business('ResolveTest')
        profile = _make_profile(biz)
        doc = FiscalDocument.objects.create(
            fiscal_profile=profile,
            document_type='factura',
            file=_make_pdf_file(),
        )
        resolved = resolve_file_field(doc.file)
        self.assertIsNotNone(resolved)
        self.assertIsInstance(resolved.file_bytes, bytes)
        self.assertGreater(resolved.size, 0)
        self.assertEqual(resolved.mime_type, 'application/pdf')
        self.assertIsNotNone(resolved.local_path)
        self.assertTrue(os.path.isfile(resolved.local_path))
        # Cleanup
        doc.file.delete(save=False)

    def test_resolves_image_from_local_storage(self):
        biz = _make_business('ResolveImgTest')
        profile = _make_profile(biz)
        doc = FiscalDocument.objects.create(
            fiscal_profile=profile,
            document_type='ticket',
            file=_make_image_file(),
        )
        resolved = resolve_file_field(doc.file)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.mime_type, 'image/png')
        self.assertIsInstance(resolved.file_bytes, bytes)
        # PNG magic bytes
        self.assertTrue(resolved.file_bytes[:4] == b'\x89PNG')
        doc.file.delete(save=False)


# ─────────────────────────────────────────────────────────────────────────
# 3. Document upload + processing (mocked extraction)
# ─────────────────────────────────────────────────────────────────────────

class DocumentUploadProcessingTest(TestCase):
    """Tests that _run_document_extraction receives bytes, not str."""

    def setUp(self):
        self.biz = _make_business('UploadProc')
        self.profile = _make_profile(self.biz)

    @patch('apps.treasury.extractors.extract_document')
    def test_extraction_receives_bytes(self, mock_extract):
        """The orchestrator must receive bytes, never a string path."""
        mock_extract.return_value = {
            'extraction_source': 'ocr',
            'normalized_data': {
                'issuer_tax_id': '20-12345678-9',
                'total_amount': '1000',
                'document_type': 'Factura A',
                'document_number': '0001-00001234',
                'issue_date': '2026-01-15',
            },
            'errors': [],
        }

        doc = FiscalDocument.objects.create(
            fiscal_profile=self.profile,
            document_type='otro',
            file=_make_pdf_file(),
        )

        # Simulate what the view does
        from apps.tax_backup.views import _run_document_extraction
        request = MagicMock()
        request.FILES = {'file': _make_pdf_file()}
        _run_document_extraction(doc, request)

        # Verify extract_document was called with bytes
        mock_extract.assert_called_once()
        call_args = mock_extract.call_args
        file_data_arg = call_args[0][0]
        self.assertIsInstance(file_data_arg, bytes, 'extract_document must receive bytes, not str')

        # Verify fields were populated
        doc.refresh_from_db()
        self.assertEqual(doc.parse_status, ParseStatus.PARSED)
        self.assertIsNone(doc.processing_error)
        self.assertEqual(doc.issuer_tax_id, '20-12345678-9')
        self.assertEqual(doc.invoice_number, '0001-00001234')
        self.assertEqual(doc.document_type, 'factura')
        self.assertTrue(doc.is_fiscal_document)

        doc.file.delete(save=False)

    @patch('apps.treasury.extractors.extract_document')
    def test_extraction_failure_sets_processing_error(self, mock_extract):
        """When extraction raises, parse_status=failed and processing_error is set."""
        mock_extract.side_effect = RuntimeError('Tesseract not found')

        doc = FiscalDocument.objects.create(
            fiscal_profile=self.profile,
            document_type='otro',
            file=_make_pdf_file(),
        )

        from apps.tax_backup.views import _run_document_extraction
        request = MagicMock()
        request.FILES = {'file': _make_pdf_file()}
        _run_document_extraction(doc, request)

        doc.refresh_from_db()
        self.assertEqual(doc.parse_status, ParseStatus.FAILED)
        self.assertIn('Tesseract not found', doc.processing_error)

        doc.file.delete(save=False)

    @patch('apps.treasury.extractors.extract_document')
    def test_extraction_no_data_sets_specific_error(self, mock_extract):
        """When extraction returns source=none, processing_error explains why."""
        mock_extract.return_value = {
            'extraction_source': 'none',
            'normalized_data': {},
            'errors': [],
        }

        doc = FiscalDocument.objects.create(
            fiscal_profile=self.profile,
            document_type='otro',
            file=_make_pdf_file(),
        )

        from apps.tax_backup.views import _run_document_extraction
        request = MagicMock()
        request.FILES = {'file': _make_pdf_file()}
        _run_document_extraction(doc, request)

        doc.refresh_from_db()
        self.assertEqual(doc.parse_status, ParseStatus.FAILED)
        self.assertIn('no encontró datos', doc.processing_error)

        doc.file.delete(save=False)


# ─────────────────────────────────────────────────────────────────────────
# 4. Document delete + profile consistency
# ─────────────────────────────────────────────────────────────────────────

class DocumentDeleteTest(TestCase):
    def setUp(self):
        self.biz = _make_business('DeleteTest')
        self.profile = _make_profile(self.biz)

    def test_delete_removes_document_and_file(self):
        doc = FiscalDocument.objects.create(
            fiscal_profile=self.profile,
            document_type='factura',
            is_fiscal_document=True,
            file=_make_pdf_file(),
        )
        file_path = doc.file.path
        self.assertTrue(os.path.isfile(file_path))

        # Delete
        doc.file.delete(save=False)
        doc.delete()

        self.assertFalse(os.path.isfile(file_path))
        self.assertEqual(FiscalDocument.objects.filter(pk=doc.pk).count(), 0)

    def test_profile_state_after_last_doc_removed(self):
        """After removing the last document, profile should reflect no docs."""
        doc = FiscalDocument.objects.create(
            fiscal_profile=self.profile,
            document_type='factura',
            is_fiscal_document=True,
            issuer_tax_id='20-12345678-9',
            total=Decimal('1000'),
            file=_make_pdf_file(),
        )

        # Profile has 1 doc
        self.profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=self.profile.pk)
        self.assertEqual(self.profile.documents.count(), 1)

        # Delete the document
        doc.file.delete(save=False)
        doc.delete()

        # Refresh
        self.profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=self.profile.pk)
        self.assertEqual(self.profile.documents.count(), 0)

    def test_profile_state_with_remaining_docs(self):
        """After removing one doc, remaining docs still present."""
        doc1 = FiscalDocument.objects.create(
            fiscal_profile=self.profile,
            document_type='factura',
            is_fiscal_document=True,
            file=_make_pdf_file('doc1.pdf'),
        )
        doc2 = FiscalDocument.objects.create(
            fiscal_profile=self.profile,
            document_type='recibo',
            is_fiscal_document=False,
            file=_make_pdf_file('doc2.pdf'),
        )

        # Delete first
        doc1.file.delete(save=False)
        doc1.delete()

        self.profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=self.profile.pk)
        self.assertEqual(self.profile.documents.count(), 1)
        self.assertEqual(self.profile.documents.first().pk, doc2.pk)

        doc2.file.delete(save=False)


# ─────────────────────────────────────────────────────────────────────────
# 5. image_utils type guard
# ─────────────────────────────────────────────────────────────────────────

class ImageUtilsTypeGuardTest(TestCase):
    """Verifies image_utils rejects string input (the original bug)."""

    def test_rejects_string_input(self):
        from apps.treasury.extractors.image_utils import images_from_file
        result = images_from_file('/some/path.pdf', 'application/pdf')  # type: ignore
        self.assertEqual(result, [])

    def test_accepts_bytes_png(self):
        from apps.treasury.extractors.image_utils import images_from_file
        png = (
            b'\x89PNG\r\n\x1a\n'
            b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
            b'\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N'
            b'\x00\x00\x00\x00IEND\xaeB\x60\x82'
        )
        result = images_from_file(png, 'image/png')
        self.assertEqual(len(result), 1)


# ─────────────────────────────────────────────────────────────────────────
# 6. processing_error field exists on model
# ─────────────────────────────────────────────────────────────────────────

class ProcessingErrorFieldTest(TestCase):
    def test_field_exists_and_nullable(self):
        biz = _make_business('FieldTest')
        profile = _make_profile(biz)
        doc = FiscalDocument.objects.create(
            fiscal_profile=profile,
            document_type='otro',
            file=_make_pdf_file(),
        )
        self.assertIsNone(doc.processing_error)

        doc.processing_error = 'Test error message'
        doc.save(update_fields=['processing_error'])
        doc.refresh_from_db()
        self.assertEqual(doc.processing_error, 'Test error message')

        doc.file.delete(save=False)

    def test_parse_status_choices(self):
        self.assertEqual(ParseStatus.MANUAL, 'manual')
        self.assertEqual(ParseStatus.PENDING, 'pending')
        self.assertEqual(ParseStatus.PARSED, 'parsed')
        self.assertEqual(ParseStatus.FAILED, 'failed')


# ─────────────────────────────────────────────────────────────────────────
# 7. QR adapter — AFIP v2 nroDocRec/tipoDocRec handling
# ─────────────────────────────────────────────────────────────────────────

class QRAdapterAfipV2Test(TestCase):
    """Tests for _map_afip_fields handling of tipoDocRec + nroDocRec."""

    def test_cuitRec_takes_priority(self):
        from apps.treasury.extractors.qr_adapter import _map_afip_fields
        data = {
            'cuit': 30712345678,
            'cuitRec': 20111111119,
            'nroDocRec': 20222222228,
            'tipoDocRec': 80,
            'importe': 1500,
        }
        result = _map_afip_fields(data)
        self.assertEqual(result['buyer_tax_id'], '20111111119')

    def test_nroDocRec_fallback_when_no_cuitRec(self):
        from apps.treasury.extractors.qr_adapter import _map_afip_fields
        data = {
            'cuit': 30712345678,
            'nroDocRec': 20000000001,
            'tipoDocRec': 80,
            'tipoCmp': 11,
            'ptoVta': 4,
            'nroCmp': 1234,
            'importe': 3200.50,
            'moneda': 'PES',
            'fecha': '2025-04-10',
        }
        result = _map_afip_fields(data)
        self.assertEqual(result['buyer_tax_id'], '20000000001')
        self.assertEqual(result['issuer_tax_id'], '30712345678')
        self.assertEqual(result['document_type'], 'Factura C')
        self.assertEqual(result['currency'], 'ARS')

    def test_nroDocRec_zero_ignored(self):
        from apps.treasury.extractors.qr_adapter import _map_afip_fields
        data = {
            'cuit': 30712345678,
            'nroDocRec': 0,
            'tipoDocRec': 99,
            'importe': 500,
        }
        result = _map_afip_fields(data)
        self.assertNotIn('buyer_tax_id', result)

    def test_no_buyer_fields_at_all(self):
        from apps.treasury.extractors.qr_adapter import _map_afip_fields
        data = {'cuit': 30712345678, 'importe': 100}
        result = _map_afip_fields(data)
        self.assertNotIn('buyer_tax_id', result)


# ─────────────────────────────────────────────────────────────────────────
# 8. OCR parser — CUIT-anchored name extraction
# ─────────────────────────────────────────────────────────────────────────

class OCRParserCUITAnchoredNameTest(TestCase):
    """Tests for _parse_ocr_text with CUIT-anchored name extraction."""

    def test_two_cuits_distinguished(self):
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = (
            "CUIT: 30-71234567-8\n"
            "Razón Social: ACME CORP SRL\n"
            "FACTURA A\n"
            "CUIT: 20-12345678-9\n"
            "Razón Social: JUAN PEREZ\n"
            "Total: $15000.00\n"
        )
        result = _parse_ocr_text(text)
        self.assertEqual(result['issuer_tax_id'], '30-71234567-8')
        self.assertEqual(result['buyer_tax_id'], '20-12345678-9')

    def test_issuer_name_backward_from_cuit(self):
        """AFIP standard layout: name label ABOVE the CUIT line."""
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = (
            "Razón Social: DISTRIBUIDORA NORTE SRL\n"
            "Domicilio Comercial: Av. San Martín 1234\n"
            "CUIT: 30-71234567-8\n"
            "Ingresos Brutos: 1\n"
            "FACTURA B\n"
            "Total: $8500.00\n"
        )
        result = _parse_ocr_text(text)
        self.assertEqual(result['issuer_name'], 'DISTRIBUIDORA NORTE SRL')

    def test_issuer_name_forward_from_cuit(self):
        """Non-standard layout: name label BELOW the CUIT line."""
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = (
            "CUIT: 30-71234567-8\n"
            "Razón Social: DISTRIBUIDORA NORTE SRL\n"
            "IVA Responsable Inscripto\n"
            "FACTURA B\n"
            "Fecha: 10/04/2025\n"
            "Total: $8500.00\n"
        )
        result = _parse_ocr_text(text)
        self.assertEqual(result['issuer_name'], 'DISTRIBUIDORA NORTE SRL')

    def test_buyer_name_same_line_as_cuit(self):
        """AFIP standard: buyer CUIT + name on same line."""
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = (
            "Razón Social: EMISORA SA\n"
            "CUIT: 30-71234567-8\n"
            "FACTURA A\n"
            "CUIT: 20-12345678-9 Apellido y Nombre / Razón Social: PRUEBA EMPLEADO\n"
            "Total: $25000.00\n"
        )
        result = _parse_ocr_text(text)
        self.assertEqual(result.get('buyer_name'), 'PRUEBA EMPLEADO')

    def test_buyer_name_next_line_after_cuit(self):
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = (
            "CUIT: 30-71234567-8\n"
            "Razón Social: EMISORA SA\n"
            "FACTURA A\n"
            "CUIT: 20-12345678-9\n"
            "Denominación: COMPRADORA SRL\n"
            "Total: $25000.00\n"
        )
        result = _parse_ocr_text(text)
        self.assertEqual(result.get('issuer_name'), 'EMISORA SA')
        self.assertEqual(result.get('buyer_name'), 'COMPRADORA SRL')

    def test_single_cuit_is_issuer_only(self):
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = (
            "CUIT: 30-71234567-8\n"
            "TICKET\n"
            "Total: $500.00\n"
        )
        result = _parse_ocr_text(text)
        self.assertEqual(result['issuer_tax_id'], '30-71234567-8')
        self.assertNotIn('buyer_tax_id', result)

    def test_same_cuit_twice_not_treated_as_buyer(self):
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = (
            "CUIT: 30-71234567-8\n"
            "Razón Social: EMPRESA X\n"
            "FACTURA C\n"
            "CUIT: 30-71234567-8\n"
            "Total: $1000.00\n"
        )
        result = _parse_ocr_text(text)
        self.assertEqual(result['issuer_tax_id'], '30-71234567-8')
        self.assertNotIn('buyer_tax_id', result)

    def test_amount_with_comma_decimal(self):
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = "Total: $1.500,50\n"
        result = _parse_ocr_text(text)
        self.assertEqual(result['total_amount'], '1500.50')

    def test_real_afip_layout_names(self):
        """Realistic AFIP factura layout: name above issuer CUIT, buyer on CUIT line."""
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = (
            "ORIGINAL\n"
            "\n"
            "CUIT Juridica de Prueba A FACTURA\n"
            "\n"
            "Punto de Venta: 00010 Comp.Nro: 00000094\n"
            "Razón Social: Cuit Juridica de Prueba\n"
            "Domicilio Comercial: 8 De Diciembre 153\n"
            "CUIT: 30000000007\n"
            "Condición frente al IVA: IVA Responsable Inscripto\n"
            "CUIT: 20000000001 Apellido y Nombre / Razón Social: PRUEBA EMPLEADO\n"
            "Total: $12100.00\n"
        )
        result = _parse_ocr_text(text)
        self.assertEqual(result.get('issuer_name'), 'Cuit Juridica de Prueba')
        self.assertEqual(result.get('buyer_name'), 'PRUEBA EMPLEADO')
        self.assertEqual(result.get('issuer_tax_id'), '30-00000000-7')
        self.assertEqual(result.get('buyer_tax_id'), '20-00000000-1')

    def test_contaminated_name_rejected(self):
        """Name with 'Fecha de Emisión' is trimmed by _clean_name, not rejected."""
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = (
            "Razón Social: Cuit] uridica de Prueba Fecha de Emisión: 13/10/2020\n"
            "CUIT: 30000000007\n"
            "CUIT: 20000000001 Apellido y Nombre / Razón Social: PRUEBA EMPLEADO\n"
            "Total: 12100.00\n"
        )
        result = _parse_ocr_text(text)
        # The issuer name should be trimmed at "Fecha de Emisión"
        self.assertEqual(result.get('issuer_name'), 'Cuit uridica de Prueba')
        self.assertNotIn('Fecha', result.get('issuer_name', ''))
        self.assertEqual(result.get('buyer_name'), 'PRUEBA EMPLEADO')

    def test_forward_search_does_not_cross_buyer_section(self):
        """Issuer forward search must stop before buyer CUIT line."""
        from apps.treasury.extractors.ocr_adapter import _parse_ocr_text
        text = (
            "CUIT: 30-71234567-8\n"
            "FACTURA A\n"
            "CUIT: 20-12345678-9\n"
            "Razón Social: BUYER ONLY NAME\n"
            "Total: $1000.00\n"
        )
        result = _parse_ocr_text(text)
        # Issuer name should NOT pick up the buyer's name
        self.assertNotIn('issuer_name', result)
        self.assertEqual(result.get('buyer_name'), 'BUYER ONLY NAME')


# ─────────────────────────────────────────────────────────────────────────
# 8b. Name cleaning and validation
# ─────────────────────────────────────────────────────────────────────────

class NameCleaningValidationTest(TestCase):
    """Tests for _clean_name and _is_valid_name."""

    def test_clean_trims_at_fecha_de_emision(self):
        from apps.treasury.extractors.ocr_adapter import _clean_name
        self.assertEqual(
            _clean_name('ACME SRL Fecha de Emisión: 13/10/2020'),
            'ACME SRL',
        )

    def test_clean_trims_at_cuit_label(self):
        from apps.treasury.extractors.ocr_adapter import _clean_name
        self.assertEqual(_clean_name('Test Name   CUIT: 12345'), 'Test Name')

    def test_clean_trims_at_date_pattern(self):
        from apps.treasury.extractors.ocr_adapter import _clean_name
        self.assertEqual(_clean_name('Corp SA 15/03/2025'), 'Corp SA')

    def test_clean_removes_brackets(self):
        from apps.treasury.extractors.ocr_adapter import _clean_name
        self.assertEqual(_clean_name('Cuit] uridica'), 'Cuit uridica')
        self.assertEqual(_clean_name('[Test Name]'), 'Test Name')

    def test_clean_collapses_whitespace(self):
        from apps.treasury.extractors.ocr_adapter import _clean_name
        self.assertEqual(_clean_name('Name   With    Spaces'), 'Name With Spaces')

    def test_valid_name_rejects_empty(self):
        from apps.treasury.extractors.ocr_adapter import _is_valid_name
        self.assertFalse(_is_valid_name(''))
        self.assertFalse(_is_valid_name(None))

    def test_valid_name_rejects_short(self):
        from apps.treasury.extractors.ocr_adapter import _is_valid_name
        self.assertFalse(_is_valid_name('AB'))

    def test_valid_name_rejects_too_many_digits(self):
        from apps.treasury.extractors.ocr_adapter import _is_valid_name
        self.assertFalse(_is_valid_name('Company 12345'))

    def test_valid_name_rejects_contaminated(self):
        from apps.treasury.extractors.ocr_adapter import _is_valid_name
        self.assertFalse(_is_valid_name('Name Fecha de Emisión extra'))
        self.assertFalse(_is_valid_name('IVA Responsable Inscripto'))
        self.assertFalse(_is_valid_name('Domicilio Comercial test'))

    def test_valid_name_accepts_normal(self):
        from apps.treasury.extractors.ocr_adapter import _is_valid_name
        self.assertTrue(_is_valid_name('ACME CORP SRL'))
        self.assertTrue(_is_valid_name('PRUEBA EMPLEADO'))
        self.assertTrue(_is_valid_name('Cuit Juridica de Prueba'))


# ─────────────────────────────────────────────────────────────────────────
# 9. Orchestrator — needs_ocr triggers for missing names
# ─────────────────────────────────────────────────────────────────────────

class OrchestratorPipelineTest(TestCase):
    """Tests the QR → TextLayer → OCR pipeline and merge priority."""

    @patch.object(OCRExtractor, 'extract')
    @patch.object(TextLayerExtractor, 'extract')
    @patch.object(QRExtractor, 'extract')
    def test_text_layer_fills_names_after_qr(self, mock_qr, mock_text, mock_ocr):
        from apps.treasury.extractors.orchestrator import DocumentExtractionOrchestrator
        from apps.treasury.extractors.base import ExtractionResult

        mock_qr.return_value = ExtractionResult(
            source='qr', success=True,
            parsed_fields={
                'issuer_tax_id': '30-71234567-8',
                'total_amount': '1500',
                'document_number': '00004-00001234',
                'buyer_tax_id': '20-00000000-1',
            },
        )
        mock_text.return_value = ExtractionResult(
            source='text_layer', success=True,
            parsed_fields={
                'issuer_name': 'ACME CORP SRL',
                'buyer_name': 'JUAN PEREZ',
            },
        )

        orch = DocumentExtractionOrchestrator()
        result = orch.extract(b'fake-pdf', 'application/pdf')

        # Text-layer provided names, QR provided structural data
        self.assertEqual(result['parsed_fields']['issuer_tax_id'], '30-71234567-8')
        self.assertEqual(result['parsed_fields']['issuer_name'], 'ACME CORP SRL')
        self.assertEqual(result['parsed_fields']['buyer_name'], 'JUAN PEREZ')
        self.assertEqual(result['extraction_source'], 'mixed')
        # OCR should NOT have run (text-layer provided names + QR provided IDs)
        mock_ocr.assert_not_called()

    @patch.object(OCRExtractor, 'extract')
    @patch.object(TextLayerExtractor, 'extract')
    @patch.object(QRExtractor, 'extract')
    def test_ocr_fallback_when_text_layer_fails(self, mock_qr, mock_text, mock_ocr):
        from apps.treasury.extractors.orchestrator import DocumentExtractionOrchestrator
        from apps.treasury.extractors.base import ExtractionResult

        mock_qr.return_value = ExtractionResult(
            source='qr', success=True,
            parsed_fields={
                'issuer_tax_id': '30-71234567-8',
                'total_amount': '1500',
                'buyer_tax_id': '20-00000000-1',
            },
        )
        mock_text.return_value = ExtractionResult(
            source='text_layer', success=False,
            errors=['PDF has no text layer'],
        )
        mock_ocr.return_value = ExtractionResult(
            source='ocr', success=True,
            parsed_fields={
                'issuer_name': 'FROM OCR FALLBACK',
            },
        )

        orch = DocumentExtractionOrchestrator()
        result = orch.extract(b'fake-pdf', 'application/pdf')

        # OCR was called because text-layer failed and issuer_name is missing
        mock_ocr.assert_called_once()
        self.assertEqual(result['parsed_fields']['issuer_name'], 'FROM OCR FALLBACK')
        self.assertEqual(result['extraction_source'], 'mixed')

    @patch.object(OCRExtractor, 'extract')
    @patch.object(TextLayerExtractor, 'extract')
    @patch.object(QRExtractor, 'extract')
    def test_qr_fields_not_overwritten_by_text_layer_or_ocr(self, mock_qr, mock_text, mock_ocr):
        from apps.treasury.extractors.orchestrator import DocumentExtractionOrchestrator
        from apps.treasury.extractors.base import ExtractionResult

        mock_qr.return_value = ExtractionResult(
            source='qr', success=True,
            parsed_fields={
                'issuer_tax_id': '30-71234567-8',
                'total_amount': '1500',
            },
        )
        mock_text.return_value = ExtractionResult(
            source='text_layer', success=True,
            parsed_fields={
                'issuer_tax_id': '20-99999999-0',  # different — should NOT overwrite
                'issuer_name': 'FROM TEXT LAYER',
            },
        )
        mock_ocr.return_value = ExtractionResult(
            source='ocr', success=True,
            parsed_fields={
                'issuer_name': 'FROM OCR',  # should NOT overwrite text-layer value
            },
        )

        orch = DocumentExtractionOrchestrator()
        result = orch.extract(b'fake-pdf', 'application/pdf')

        # QR value preserved
        self.assertEqual(result['parsed_fields']['issuer_tax_id'], '30-71234567-8')
        # Text-layer value preserved (not overwritten by OCR)
        self.assertEqual(result['parsed_fields']['issuer_name'], 'FROM TEXT LAYER')

    @patch.object(TextLayerExtractor, 'extract')
    @patch.object(QRExtractor, 'extract')
    def test_text_layer_not_called_for_images(self, mock_qr, mock_text):
        from apps.treasury.extractors.orchestrator import DocumentExtractionOrchestrator
        from apps.treasury.extractors.base import ExtractionResult

        mock_qr.return_value = ExtractionResult(
            source='qr', success=False,
            errors=['No QR found'],
        )

        orch = DocumentExtractionOrchestrator()
        # image/jpeg — text-layer should NOT be called
        result = orch.extract(b'fake-image', 'image/jpeg')

        mock_text.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────
# 10. Full extraction → model save includes buyer_name
# ─────────────────────────────────────────────────────────────────────────

class ExtractionBuyerNamePersistenceTest(TestCase):
    """Tests that buyer_name from extraction is saved to the model."""

    def setUp(self):
        self.biz = _make_business('BuyerNameTest')
        self.profile = _make_profile(self.biz)

    @patch('apps.treasury.extractors.extract_document')
    def test_buyer_name_persisted(self, mock_extract):
        mock_extract.return_value = {
            'extraction_source': 'mixed',
            'normalized_data': {
                'issuer_tax_id': '30-71234567-8',
                'total_amount': '1500',
                'document_type': 'Factura A',
                'document_number': '00004-00001234',
                'issue_date': '2025-04-10',
                'buyer_tax_id': '20-00000000-1',
                'buyer_name': 'COMPRADORA SRL',
                'issuer_name': 'VENDEDORA SA',
            },
            'errors': [],
        }

        doc = FiscalDocument.objects.create(
            fiscal_profile=self.profile,
            document_type='otro',
            file=_make_pdf_file(),
        )

        from apps.tax_backup.views import _run_document_extraction
        request = MagicMock()
        request.FILES = {'file': _make_pdf_file()}
        _run_document_extraction(doc, request)

        doc.refresh_from_db()
        self.assertEqual(doc.buyer_name, 'COMPRADORA SRL')
        self.assertEqual(doc.issuer_name, 'VENDEDORA SA')
        self.assertEqual(doc.buyer_tax_id, '20-00000000-1')
        self.assertEqual(doc.parse_status, ParseStatus.PARSED)

        doc.file.delete(save=False)

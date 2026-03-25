"""
Sprint 2 — ExpenseDocument layer tests.
Run with: python manage.py test apps.treasury.tests.test_expense_document
"""
from decimal import Decimal
from datetime import date, datetime, timezone as tz
from io import BytesIO

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError

from apps.business.models import Business
from apps.treasury.models import (
    Account,
    Expense,
    ExpenseDocument,
    FixedExpense,
    FixedExpensePeriod,
    TransactionCategory,
    EXPENSE_DOCUMENT_ALLOWED_TYPES,
    EXPENSE_DOCUMENT_MAX_SIZE_BYTES,
)
from django.contrib.auth import get_user_model

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_business(name='DocTest Biz'):
    b, _ = Business.objects.get_or_create(name=name)
    return b


def make_user(email='doctest@test.com'):
    u, _ = User.objects.get_or_create(email=email, defaults={'username': email})
    return u


def make_account(business, name='Caja'):
    return Account.objects.create(
        business=business, name=name, type='cash', currency='ARS', opening_balance=Decimal('10000'),
    )


def make_expense(business, name='Gasto Test', amount=Decimal('500')):
    return Expense.objects.create(
        business=business, name=name, amount=amount,
        due_date=date(2026, 3, 25), status=Expense.Status.PENDING,
    )


def make_fixed_expense(business, name='Alquiler'):
    fe, _ = FixedExpense.objects.get_or_create(
        business=business, name=name,
        defaults={'default_amount': Decimal('1000'), 'due_day': 10},
    )
    return fe


def make_fep(business, name='Alquiler'):
    fe = make_fixed_expense(business, name)
    fep, _ = FixedExpensePeriod.objects.get_or_create(
        fixed_expense=fe, period=date(2026, 3, 1),
        defaults={'amount': Decimal('1000'), 'status': FixedExpensePeriod.Status.PENDING},
    )
    return fep


def make_pdf(name='comprobante.pdf', size=1024):
    return SimpleUploadedFile(name, b'%PDF-' + b'x' * (size - 5), content_type='application/pdf')


def make_jpg(name='foto.jpg', size=1024):
    return SimpleUploadedFile(name, b'\xff\xd8\xff' + b'x' * (size - 3), content_type='image/jpeg')


def make_png(name='scan.png', size=1024):
    return SimpleUploadedFile(name, b'\x89PNG' + b'x' * (size - 4), content_type='image/png')


# ---------------------------------------------------------------------------
# Model constraint tests
# ---------------------------------------------------------------------------

class ExpenseDocumentConstraintsTest(TestCase):
    """DB-level constraints for ExpenseDocument."""

    def setUp(self):
        self.business = make_business('Constraint Biz')
        self.user = make_user('constraint@test.com')
        self.expense = make_expense(self.business)
        self.fep = make_fep(self.business)

    def test_create_with_expense_origin(self):
        doc = ExpenseDocument.objects.create(
            business=self.business,
            expense=self.expense,
            file=make_pdf(),
            original_filename='fact.pdf',
            mime_type='application/pdf',
            size_bytes=1024,
            uploaded_by=self.user,
        )
        self.assertIsNotNone(doc.pk)
        self.assertEqual(doc.expense_id, self.expense.id)
        self.assertIsNone(doc.fixed_expense_period_id)

    def test_create_with_fep_origin(self):
        doc = ExpenseDocument.objects.create(
            business=self.business,
            fixed_expense_period=self.fep,
            file=make_pdf(),
            original_filename='recibo.pdf',
            mime_type='application/pdf',
            size_bytes=1024,
            uploaded_by=self.user,
        )
        self.assertIsNotNone(doc.pk)
        self.assertIsNone(doc.expense_id)
        self.assertEqual(doc.fixed_expense_period_id, self.fep.id)

    def test_both_origins_set_raises_db_error(self):
        """CheckConstraint: cannot set both expense AND fep."""
        with self.assertRaises(IntegrityError):
            ExpenseDocument.objects.create(
                business=self.business,
                expense=self.expense,
                fixed_expense_period=self.fep,
                file=make_pdf(),
                original_filename='invalid.pdf',
                mime_type='application/pdf',
                size_bytes=1024,
            )

    def test_no_origin_raises_db_error(self):
        """CheckConstraint: must set at least one origin."""
        with self.assertRaises(IntegrityError):
            ExpenseDocument.objects.create(
                business=self.business,
                file=make_pdf(),
                original_filename='orphan.pdf',
                mime_type='application/pdf',
                size_bytes=1024,
            )

    def test_multiple_documents_per_expense_allowed(self):
        """Multiple docs per same origin is allowed."""
        for i in range(3):
            ExpenseDocument.objects.create(
                business=self.business,
                expense=self.expense,
                file=make_pdf(f'doc_{i}.pdf'),
                original_filename=f'doc_{i}.pdf',
                mime_type='application/pdf',
                size_bytes=1024,
            )
        self.assertEqual(self.expense.documents.count(), 3)

    def test_default_status_is_uploaded(self):
        doc = ExpenseDocument.objects.create(
            business=self.business,
            expense=self.expense,
            file=make_pdf(),
            original_filename='test.pdf',
            mime_type='application/pdf',
            size_bytes=1024,
        )
        self.assertEqual(doc.status, ExpenseDocument.Status.UPLOADED)

    def test_default_document_kind_is_other(self):
        doc = ExpenseDocument.objects.create(
            business=self.business,
            expense=self.expense,
            file=make_pdf(),
            original_filename='test.pdf',
            mime_type='application/pdf',
            size_bytes=1024,
        )
        self.assertEqual(doc.document_kind, ExpenseDocument.DocumentKind.OTHER)


# ---------------------------------------------------------------------------
# Ownership / cross-business validation tests
# ---------------------------------------------------------------------------

class ExpenseDocumentOwnershipTest(TestCase):
    """Business isolation — documents must belong to same business as origin."""

    def setUp(self):
        self.biz_a = make_business('Biz A')
        self.biz_b = make_business('Biz B')
        self.expense_a = make_expense(self.biz_a, 'Gasto A')
        self.expense_b = make_expense(self.biz_b, 'Gasto B')
        self.fep_a = make_fep(self.biz_a, 'Alquiler A')
        self.fep_b = make_fep(self.biz_b, 'Alquiler B')

    def test_document_business_matches_expense(self):
        """Creating a document on same business as expense works."""
        doc = ExpenseDocument.objects.create(
            business=self.biz_a,
            expense=self.expense_a,
            file=make_pdf(),
            original_filename='ok.pdf',
            mime_type='application/pdf',
            size_bytes=1024,
        )
        self.assertEqual(doc.business_id, self.expense_a.business_id)

    def test_cross_business_expense_detected_via_property(self):
        """The origin_business_id property detects mismatch."""
        doc = ExpenseDocument(
            business=self.biz_a,
            expense=self.expense_b,
            file=make_pdf(),
            original_filename='cross.pdf',
            mime_type='application/pdf',
            size_bytes=1024,
        )
        self.assertNotEqual(doc.business_id, doc.origin_business_id)

    def test_cross_business_fep_detected_via_property(self):
        doc = ExpenseDocument(
            business=self.biz_a,
            fixed_expense_period=self.fep_b,
            file=make_pdf(),
            original_filename='cross.pdf',
            mime_type='application/pdf',
            size_bytes=1024,
        )
        self.assertNotEqual(doc.business_id, doc.origin_business_id)


# ---------------------------------------------------------------------------
# Serializer validation tests
# ---------------------------------------------------------------------------

class ExpenseDocumentSerializerTest(TestCase):
    """Serializer-level validations for ExpenseDocumentUploadSerializer."""

    def setUp(self):
        self.biz = make_business('Serializer Biz')
        self.user = make_user('serializer@test.com')
        self.expense = make_expense(self.biz)
        self.fep = make_fep(self.biz, 'Internet')

    def _validate(self, data, business=None):
        from apps.treasury.serializers import ExpenseDocumentUploadSerializer

        class FakeRequest:
            def __init__(self, biz, user):
                self.business = biz
                self.user = user

        request = FakeRequest(business or self.biz, self.user)
        ser = ExpenseDocumentUploadSerializer(data=data, context={'request': request})
        return ser

    def test_valid_pdf_expense_upload(self):
        ser = self._validate({
            'file': make_pdf(),
            'expense': self.expense.id,
        })
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_valid_jpg_fep_upload(self):
        ser = self._validate({
            'file': make_jpg(),
            'fixed_expense_period': self.fep.id,
        })
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_both_origins_fails(self):
        ser = self._validate({
            'file': make_pdf(),
            'expense': self.expense.id,
            'fixed_expense_period': self.fep.id,
        })
        self.assertFalse(ser.is_valid())

    def test_no_origin_fails(self):
        ser = self._validate({
            'file': make_pdf(),
        })
        self.assertFalse(ser.is_valid())

    def test_invalid_mime_type_rejected(self):
        exe_file = SimpleUploadedFile('malware.exe', b'\x00' * 100, content_type='application/x-msdownload')
        ser = self._validate({
            'file': exe_file,
            'expense': self.expense.id,
        })
        self.assertFalse(ser.is_valid())
        self.assertIn('file', ser.errors)

    def test_oversized_file_rejected(self):
        big_file = SimpleUploadedFile(
            'huge.pdf',
            b'%PDF-' + b'x' * EXPENSE_DOCUMENT_MAX_SIZE_BYTES,
            content_type='application/pdf',
        )
        ser = self._validate({
            'file': big_file,
            'expense': self.expense.id,
        })
        self.assertFalse(ser.is_valid())
        self.assertIn('file', ser.errors)

    def test_cross_business_expense_rejected(self):
        other_biz = make_business('Other Biz Serializer')
        other_expense = make_expense(other_biz, 'Gasto Ajeno')
        ser = self._validate({
            'file': make_pdf(),
            'expense': other_expense.id,
        })
        self.assertFalse(ser.is_valid())
        self.assertIn('expense', ser.errors)

    def test_cross_business_fep_rejected(self):
        other_biz = make_business('Other FEP Biz')
        other_fep = make_fep(other_biz, 'Servicio Ajeno')
        ser = self._validate({
            'file': make_pdf(),
            'fixed_expense_period': other_fep.id,
        })
        self.assertFalse(ser.is_valid())
        self.assertIn('fixed_expense_period', ser.errors)

    def test_webp_accepted(self):
        webp = SimpleUploadedFile('photo.webp', b'RIFF' + b'\x00' * 100, content_type='image/webp')
        ser = self._validate({
            'file': webp,
            'expense': self.expense.id,
        })
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_png_accepted(self):
        ser = self._validate({
            'file': make_png(),
            'expense': self.expense.id,
        })
        self.assertTrue(ser.is_valid(), ser.errors)


# ---------------------------------------------------------------------------
# Archive / lifecycle tests
# ---------------------------------------------------------------------------

class ExpenseDocumentLifecycleTest(TestCase):
    """Status transitions: uploaded → archived and back."""

    def setUp(self):
        self.biz = make_business('Lifecycle Biz')
        self.user = make_user('lifecycle@test.com')
        self.expense = make_expense(self.biz)

    def _make_doc(self, **kwargs):
        defaults = dict(
            business=self.biz,
            expense=self.expense,
            file=make_pdf(),
            original_filename='document.pdf',
            mime_type='application/pdf',
            size_bytes=1024,
            uploaded_by=self.user,
        )
        defaults.update(kwargs)
        return ExpenseDocument.objects.create(**defaults)

    def test_archive_document(self):
        doc = self._make_doc()
        doc.status = ExpenseDocument.Status.ARCHIVED
        doc.save(update_fields=['status', 'updated_at'])
        doc.refresh_from_db()
        self.assertEqual(doc.status, ExpenseDocument.Status.ARCHIVED)

    def test_unarchive_document(self):
        doc = self._make_doc(status=ExpenseDocument.Status.ARCHIVED)
        doc.status = ExpenseDocument.Status.UPLOADED
        doc.save(update_fields=['status', 'updated_at'])
        doc.refresh_from_db()
        self.assertEqual(doc.status, ExpenseDocument.Status.UPLOADED)

    def test_delete_document(self):
        doc = self._make_doc()
        doc_id = doc.id
        doc.file.delete(save=False)
        doc.delete()
        self.assertFalse(ExpenseDocument.objects.filter(id=doc_id).exists())

    def test_origin_property_returns_expense(self):
        doc = self._make_doc()
        self.assertEqual(doc.origin, self.expense)

    def test_origin_property_returns_fep(self):
        fep = make_fep(self.biz, 'Luz')
        doc = self._make_doc(expense=None, fixed_expense_period=fep)
        self.assertEqual(doc.origin, fep)


# ---------------------------------------------------------------------------
# Integration: documents_count in serializers
# ---------------------------------------------------------------------------

class ExpenseDocumentSerializerIntegrationTest(TestCase):
    """Ensure documents_count and latest_document appear in Expense/FEP serializers."""

    def setUp(self):
        self.biz = make_business('Integration Biz')
        self.user = make_user('integration@test.com')
        self.expense = make_expense(self.biz)
        self.fep = make_fep(self.biz, 'Gas')

    def test_expense_serializer_has_documents_count(self):
        from apps.treasury.serializers import ExpenseSerializer
        data = ExpenseSerializer(self.expense).data
        self.assertIn('documents_count', data)
        self.assertEqual(data['documents_count'], 0)

    def test_expense_serializer_documents_count_increments(self):
        from apps.treasury.serializers import ExpenseSerializer
        ExpenseDocument.objects.create(
            business=self.biz, expense=self.expense,
            file=make_pdf(), original_filename='a.pdf',
            mime_type='application/pdf', size_bytes=100,
        )
        ExpenseDocument.objects.create(
            business=self.biz, expense=self.expense,
            file=make_pdf('b.pdf'), original_filename='b.pdf',
            mime_type='application/pdf', size_bytes=200,
        )
        data = ExpenseSerializer(self.expense).data
        self.assertEqual(data['documents_count'], 2)

    def test_expense_serializer_archived_excluded_from_count(self):
        from apps.treasury.serializers import ExpenseSerializer
        ExpenseDocument.objects.create(
            business=self.biz, expense=self.expense,
            file=make_pdf(), original_filename='active.pdf',
            mime_type='application/pdf', size_bytes=100,
        )
        ExpenseDocument.objects.create(
            business=self.biz, expense=self.expense,
            file=make_pdf('old.pdf'), original_filename='old.pdf',
            mime_type='application/pdf', size_bytes=200,
            status=ExpenseDocument.Status.ARCHIVED,
        )
        data = ExpenseSerializer(self.expense).data
        self.assertEqual(data['documents_count'], 1)

    def test_expense_serializer_latest_document(self):
        from apps.treasury.serializers import ExpenseSerializer
        ExpenseDocument.objects.create(
            business=self.biz, expense=self.expense,
            file=make_pdf(), original_filename='latest.pdf',
            mime_type='application/pdf', size_bytes=300,
            document_kind=ExpenseDocument.DocumentKind.INVOICE,
        )
        data = ExpenseSerializer(self.expense).data
        self.assertIsNotNone(data['latest_document'])
        self.assertEqual(data['latest_document']['original_filename'], 'latest.pdf')
        self.assertEqual(data['latest_document']['document_kind'], 'invoice')

    def test_fep_serializer_has_documents_count(self):
        from apps.treasury.serializers import FixedExpensePeriodSerializer
        data = FixedExpensePeriodSerializer(self.fep).data
        self.assertIn('documents_count', data)
        self.assertEqual(data['documents_count'], 0)

    def test_fep_serializer_documents_count_increments(self):
        from apps.treasury.serializers import FixedExpensePeriodSerializer
        ExpenseDocument.objects.create(
            business=self.biz, fixed_expense_period=self.fep,
            file=make_pdf(), original_filename='a.pdf',
            mime_type='application/pdf', size_bytes=100,
        )
        data = FixedExpensePeriodSerializer(self.fep).data
        self.assertEqual(data['documents_count'], 1)


# ---------------------------------------------------------------------------
# Inventory gap fix tests (Payment creation on stock replenishment)
# ---------------------------------------------------------------------------

class ReplenishmentPaymentGapTest(TestCase):
    """
    Sprint 2 gap fix: create_stock_replenishment must create a Payment entity
    alongside the auto-generated Expense, and void_stock_replenishment must
    void it.
    """

    def setUp(self):
        from apps.catalog.models import Product
        self.biz = make_business('Repl Payment Biz')
        self.user = make_user('repl_pay@test.com')
        self.account = make_account(self.biz)
        self.product = Product.objects.create(
            business=self.biz, name='Harina', sku='HARINA',
            cost=Decimal('100'), price=Decimal('200'),
        )

    def _create_replenishment(self):
        from apps.inventory.services import create_stock_replenishment
        return create_stock_replenishment(
            business=self.biz,
            supplier_name='Proveedor Test',
            invoice_number='PAY-001',
            account=self.account,
            items=[{'product_id': str(self.product.id), 'quantity': 5, 'unit_cost': '100'}],
            created_by=self.user,
        )

    def test_replenishment_creates_payment(self):
        from apps.treasury.models import Payment
        repl = self._create_replenishment()
        expense = Expense.objects.get(
            source_type='stock_replenishment', source_id=str(repl.id),
        )
        payments = Payment.objects.filter(expense=expense, status=Payment.Status.COMPLETED)
        self.assertEqual(payments.count(), 1)

    def test_payment_links_to_same_transaction(self):
        from apps.treasury.models import Payment
        repl = self._create_replenishment()
        expense = Expense.objects.get(
            source_type='stock_replenishment', source_id=str(repl.id),
        )
        payment = Payment.objects.get(expense=expense, status=Payment.Status.COMPLETED)
        self.assertEqual(payment.transaction_id, repl.transaction_id)

    def test_payment_amount_matches_total(self):
        from apps.treasury.models import Payment
        repl = self._create_replenishment()
        expense = Expense.objects.get(
            source_type='stock_replenishment', source_id=str(repl.id),
        )
        payment = Payment.objects.get(expense=expense, status=Payment.Status.COMPLETED)
        self.assertEqual(payment.amount, Decimal('500.0000'))

    def test_payment_business_matches(self):
        from apps.treasury.models import Payment
        repl = self._create_replenishment()
        expense = Expense.objects.get(
            source_type='stock_replenishment', source_id=str(repl.id),
        )
        payment = Payment.objects.get(expense=expense, status=Payment.Status.COMPLETED)
        self.assertEqual(payment.business_id, self.biz.id)

    def test_void_replenishment_voids_payment(self):
        from apps.treasury.models import Payment
        from apps.inventory.services import void_stock_replenishment
        repl = self._create_replenishment()
        expense = Expense.objects.get(
            source_type='stock_replenishment', source_id=str(repl.id),
        )
        void_stock_replenishment(replenishment=repl, reason='Error de carga', voided_by=self.user)
        payment = Payment.objects.get(expense=expense)
        self.assertEqual(payment.status, Payment.Status.VOIDED)

    def test_void_idempotent_for_payment(self):
        from apps.treasury.models import Payment
        from apps.inventory.services import void_stock_replenishment
        repl = self._create_replenishment()
        void_stock_replenishment(replenishment=repl, reason='Error', voided_by=self.user)
        void_stock_replenishment(replenishment=repl, reason='Error duplicado', voided_by=self.user)
        expense = Expense.objects.get(
            source_type='stock_replenishment', source_id=str(repl.id),
        )
        self.assertEqual(
            Payment.objects.filter(expense=expense).count(), 1,
        )


# ===========================================================================
# Sprint 3 — Document Processing Pipeline Tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Extractor unit tests
# ---------------------------------------------------------------------------

class ExtractorParsingTest(TestCase):
    """Unit tests for treasury.extractors parsing helpers."""

    def test_parse_afip_qr_valid(self):
        import base64, json
        from apps.treasury.extractors import _parse_afip_qr

        afip_data = {
            'ver': 1, 'fecha': '2026-01-15', 'cuit': 30712345678,
            'ptoVta': 1, 'tipoCmp': 6, 'nroCmp': 1234,
            'importe': 1500.50, 'moneda': 'PES', 'ctz': 1,
            'cuitRec': 20345678901,
        }
        payload_b64 = base64.b64encode(json.dumps(afip_data).encode()).decode()
        url = f'https://www.afip.gob.ar/fe/qr/?p={payload_b64}'

        result = _parse_afip_qr(url)
        self.assertEqual(result['issuer_tax_id'], '30712345678')
        self.assertEqual(result['issue_date'], '2026-01-15')
        self.assertEqual(result['document_type'], 'Factura B')
        self.assertEqual(result['document_number'], '00001-00001234')
        self.assertEqual(result['total_amount'], '1500.5')
        self.assertEqual(result['currency'], 'ARS')
        self.assertEqual(result['buyer_tax_id'], '20345678901')

    def test_parse_afip_qr_raw_json(self):
        import json
        from apps.treasury.extractors import _parse_afip_qr

        raw_json = json.dumps({
            'cuit': 20123456789, 'importe': 250, 'tipoCmp': 1, 'moneda': 'DOL',
        })
        result = _parse_afip_qr(raw_json)
        self.assertEqual(result['issuer_tax_id'], '20123456789')
        self.assertEqual(result['document_type'], 'Factura A')
        self.assertEqual(result['currency'], 'USD')

    def test_parse_afip_qr_plain_text_returns_payload(self):
        from apps.treasury.extractors import _parse_afip_qr
        result = _parse_afip_qr('not-a-url-and-not-json')
        self.assertEqual(result['qr_payload'], 'not-a-url-and-not-json')
        self.assertNotIn('issuer_tax_id', result)

    def test_parse_ocr_text_cuit(self):
        from apps.treasury.extractors import _parse_ocr_text
        result = _parse_ocr_text('CUIT: 30-71234567-8  Factura B')
        self.assertEqual(result['issuer_tax_id'], '30-71234567-8')

    def test_parse_ocr_text_document_number(self):
        from apps.treasury.extractors import _parse_ocr_text
        result = _parse_ocr_text('Nro: 0001-00005678')
        self.assertEqual(result['document_number'], '00001-00005678')

    def test_parse_ocr_text_total_amount_ar_format(self):
        from apps.treasury.extractors import _parse_ocr_text
        result = _parse_ocr_text('Total: $ 1.234,56')
        self.assertEqual(result['total_amount'], '1234.56')

    def test_parse_ocr_text_date(self):
        from apps.treasury.extractors import _parse_ocr_text
        result = _parse_ocr_text('Fecha de Emisión: 15/03/2026')
        self.assertEqual(result['issue_date'], '2026-03-15')

    def test_parse_ocr_text_document_type_factura_a(self):
        from apps.treasury.extractors import _parse_ocr_text
        result = _parse_ocr_text('FACTURA A\nNro: 0005-00001234')
        self.assertEqual(result['document_type'], 'Factura A')

    def test_parse_ocr_text_issuer_name(self):
        from apps.treasury.extractors import _parse_ocr_text
        result = _parse_ocr_text('Razón Social: Mi Empresa S.R.L.\nCUIT: 30-12345678-9')
        self.assertEqual(result['issuer_name'], 'Mi Empresa S.R.L.')

    def test_normalize_amount_ar_format(self):
        from apps.treasury.extractors import _normalize_amount
        self.assertEqual(_normalize_amount('1.234,56'), '1234.56')

    def test_normalize_amount_us_format(self):
        from apps.treasury.extractors import _normalize_amount
        self.assertEqual(_normalize_amount('1,234.56'), '1234.56')

    def test_normalize_amount_simple_comma(self):
        from apps.treasury.extractors import _normalize_amount
        self.assertEqual(_normalize_amount('1234,56'), '1234.56')

    def test_normalize_amount_invalid(self):
        from apps.treasury.extractors import _normalize_amount
        self.assertIsNone(_normalize_amount('abc'))


class ExtractDocumentOrchestratorTest(TestCase):
    """Test the extract_document() orchestrator with mocked extractors."""

    def test_qr_only_result(self):
        from unittest.mock import patch
        from apps.treasury.extractors import extract_document

        qr_result = {
            'qr_payloads': ['https://afip...'],
            'parsed_fields': {
                'issuer_tax_id': '30712345678',
                'total_amount': '1500',
                'document_number': '00001-00001234',
            },
        }
        with patch('apps.treasury.extractors.extract_qr', return_value=qr_result), \
             patch('apps.treasury.extractors.extract_ocr', return_value=None):
            result = extract_document('/fake/path.pdf', 'application/pdf')

        self.assertEqual(result['extraction_source'], 'qr')
        self.assertEqual(result['normalized_data']['issuer_tax_id'], '30712345678')
        self.assertEqual(result['errors'], [])

    def test_ocr_fallback_when_no_qr(self):
        from unittest.mock import patch
        from apps.treasury.extractors import extract_document

        ocr_result = {
            'ocr_text': 'FACTURA B\nTotal: $500',
            'parsed_fields': {
                'document_type': 'Factura B',
                'total_amount': '500',
            },
        }
        with patch('apps.treasury.extractors.extract_qr', return_value=None), \
             patch('apps.treasury.extractors.extract_ocr', return_value=ocr_result):
            result = extract_document('/fake/path.jpg', 'image/jpeg')

        self.assertEqual(result['extraction_source'], 'ocr')
        self.assertEqual(result['normalized_data']['document_type'], 'Factura B')

    def test_mixed_when_qr_partial(self):
        from unittest.mock import patch
        from apps.treasury.extractors import extract_document

        qr_result = {
            'qr_payloads': ['data'],
            'parsed_fields': {'document_number': '00001-00001234'},
            # Missing issuer_tax_id and total_amount → triggers OCR
        }
        ocr_result = {
            'ocr_text': 'CUIT: 30-12345678-9\nTotal: $2000',
            'parsed_fields': {
                'issuer_tax_id': '30-12345678-9',
                'total_amount': '2000',
            },
        }
        with patch('apps.treasury.extractors.extract_qr', return_value=qr_result), \
             patch('apps.treasury.extractors.extract_ocr', return_value=ocr_result):
            result = extract_document('/fake/path.pdf', 'application/pdf')

        self.assertEqual(result['extraction_source'], 'mixed')
        # QR field preserved
        self.assertEqual(result['normalized_data']['document_number'], '00001-00001234')
        # OCR filled gaps
        self.assertEqual(result['normalized_data']['issuer_tax_id'], '30-12345678-9')

    def test_none_when_both_fail(self):
        from unittest.mock import patch
        from apps.treasury.extractors import extract_document

        with patch('apps.treasury.extractors.extract_qr', return_value=None), \
             patch('apps.treasury.extractors.extract_ocr', return_value=None):
            result = extract_document('/fake/path.pdf', 'application/pdf')

        self.assertEqual(result['extraction_source'], 'none')
        self.assertEqual(result['errors'], [])

    def test_error_in_qr_captured(self):
        from unittest.mock import patch
        from apps.treasury.extractors import extract_document

        with patch('apps.treasury.extractors.extract_qr', side_effect=RuntimeError('boom')), \
             patch('apps.treasury.extractors.extract_ocr', return_value=None):
            result = extract_document('/fake/path.pdf', 'application/pdf')

        self.assertEqual(result['extraction_source'], 'none')
        self.assertTrue(any('QR extraction error' in e for e in result['errors']))


# ---------------------------------------------------------------------------
# Celery task tests (synchronous — no broker needed)
# ---------------------------------------------------------------------------

class ProcessExpenseDocumentTaskTest(TestCase):
    """Test the process_expense_document Celery task."""

    def setUp(self):
        self.biz = make_business('Task Biz')
        self.user = make_user('task@test.com')
        self.expense = make_expense(self.biz)

    def _make_doc(self, **kwargs):
        defaults = dict(
            business=self.biz,
            expense=self.expense,
            file=make_pdf(),
            original_filename='test.pdf',
            mime_type='application/pdf',
            size_bytes=1024,
            uploaded_by=self.user,
            status=ExpenseDocument.Status.QUEUED,
        )
        defaults.update(kwargs)
        return ExpenseDocument.objects.create(**defaults)

    def test_task_processes_document_successfully(self):
        from unittest.mock import patch
        from apps.treasury.tasks import process_expense_document

        doc = self._make_doc()
        extraction_result = {
            'extraction_source': 'qr',
            'raw_extraction': {'qr': {'qr_payloads': ['test']}},
            'normalized_data': {'issuer_tax_id': '30712345678', 'total_amount': '1500'},
            'errors': [],
        }
        with patch('apps.treasury.extractors.extract_document', return_value=extraction_result):
            result = process_expense_document(doc.id)

        doc.refresh_from_db()
        self.assertEqual(doc.status, ExpenseDocument.Status.PROCESSED)
        self.assertEqual(doc.extraction_source, 'qr')
        self.assertEqual(doc.normalized_data['issuer_tax_id'], '30712345678')
        self.assertIsNotNone(doc.processed_at)
        self.assertIsNone(doc.processing_errors)
        self.assertEqual(result['status'], 'processed')

    def test_task_records_failure(self):
        from unittest.mock import patch
        from apps.treasury.tasks import process_expense_document

        doc = self._make_doc()
        with patch('apps.treasury.extractors.extract_document', side_effect=RuntimeError('corrupt')):
            # Disable retry to test failure path directly
            with patch.object(process_expense_document, 'max_retries', 0):
                result = process_expense_document(doc.id)

        doc.refresh_from_db()
        self.assertEqual(doc.status, ExpenseDocument.Status.FAILED)
        self.assertIn('corrupt', doc.processing_errors[0])
        self.assertIsNotNone(doc.processed_at)
        self.assertEqual(result['status'], 'failed')

    def test_task_with_missing_document(self):
        from apps.treasury.tasks import process_expense_document
        result = process_expense_document(99999)
        self.assertEqual(result['status'], 'error')

    def test_task_preserves_errors_from_extraction(self):
        from unittest.mock import patch
        from apps.treasury.tasks import process_expense_document

        doc = self._make_doc()
        extraction_result = {
            'extraction_source': 'ocr',
            'raw_extraction': {'ocr': {'ocr_text': 'some text'}},
            'normalized_data': {'total_amount': '500'},
            'errors': ['QR extraction error: pyzbar failed'],
        }
        with patch('apps.treasury.extractors.extract_document', return_value=extraction_result):
            process_expense_document(doc.id)

        doc.refresh_from_db()
        self.assertEqual(doc.status, ExpenseDocument.Status.PROCESSED)
        self.assertIsNotNone(doc.processing_errors)
        self.assertIn('QR extraction error', doc.processing_errors[0])


# ---------------------------------------------------------------------------
# File validation (Sprint 3 hardening: magic bytes)
# ---------------------------------------------------------------------------

class FileValidationTest(TestCase):
    """Centralized file validation with magic byte checking."""

    def test_valid_pdf_passes(self):
        from apps.treasury.file_validation import validate_expense_document_file
        f = make_pdf()
        result = validate_expense_document_file(f)
        self.assertEqual(result, f)

    def test_valid_jpg_passes(self):
        from apps.treasury.file_validation import validate_expense_document_file
        f = make_jpg()
        result = validate_expense_document_file(f)
        self.assertEqual(result, f)

    def test_valid_png_passes(self):
        from apps.treasury.file_validation import validate_expense_document_file
        f = make_png()
        result = validate_expense_document_file(f)
        self.assertEqual(result, f)

    def test_invalid_mime_rejected(self):
        from rest_framework import serializers as drf_ser
        from apps.treasury.file_validation import validate_expense_document_file
        exe = SimpleUploadedFile('bad.exe', b'\x00' * 100, content_type='application/x-msdownload')
        with self.assertRaises(drf_ser.ValidationError):
            validate_expense_document_file(exe)

    def test_oversized_file_rejected(self):
        from rest_framework import serializers as drf_ser
        from apps.treasury.file_validation import validate_expense_document_file
        big = SimpleUploadedFile(
            'big.pdf', b'%PDF-' + b'x' * (10 * 1024 * 1024 + 1),
            content_type='application/pdf',
        )
        with self.assertRaises(drf_ser.ValidationError):
            validate_expense_document_file(big)

    def test_mismatched_magic_rejected(self):
        """File with PDF content_type but JPEG magic bytes is rejected."""
        from rest_framework import serializers as drf_ser
        from apps.treasury.file_validation import validate_expense_document_file
        fake_pdf = SimpleUploadedFile(
            'fake.pdf', b'\xff\xd8\xff' + b'x' * 100, content_type='application/pdf',
        )
        with self.assertRaises(drf_ser.ValidationError):
            validate_expense_document_file(fake_pdf)


# ---------------------------------------------------------------------------
# Processing field read-only in serializer (PATCH mutation prevention)
# ---------------------------------------------------------------------------

class ExpenseDocumentReadOnlyFieldsTest(TestCase):
    """Ensure processing fields cannot be set via API serializer."""

    def test_processing_fields_are_read_only(self):
        from apps.treasury.serializers import ExpenseDocumentSerializer
        ro = ExpenseDocumentSerializer.Meta.read_only_fields
        for field in ('raw_extraction', 'normalized_data', 'processing_errors',
                      'processed_at', 'extraction_source'):
            self.assertIn(field, ro)

    def test_origin_fields_are_read_only(self):
        from apps.treasury.serializers import ExpenseDocumentSerializer
        ro = ExpenseDocumentSerializer.Meta.read_only_fields
        for field in ('expense', 'fixed_expense_period', 'file'):
            self.assertIn(field, ro)


class ReplenishmentIdempotencyTest(TestCase):
    """Idempotency test for replenishment payment creation."""

    def setUp(self):
        from apps.catalog.models import Product
        self.biz = make_business('Idempotent Biz')
        self.user = make_user('idemp@test.com')
        self.account = make_account(self.biz)
        self.product = Product.objects.create(
            business=self.biz, name='Azucar', sku='AZUCAR',
            cost=Decimal('100'), price=Decimal('200'),
        )

    def _create_replenishment(self):
        from apps.inventory.services import create_stock_replenishment
        return create_stock_replenishment(
            business=self.biz,
            supplier_name='Proveedor Test',
            invoice_number='IDEMP-001',
            account=self.account,
            items=[{'product_id': str(self.product.id), 'quantity': 5, 'unit_cost': '100'}],
            created_by=self.user,
        )

    def test_idempotent_no_duplicate_payment_on_retry(self):
        """If create_stock_replenishment is called and the Expense already exists
        with a completed Payment (e.g. retry), no duplicate Payment is created."""
        from apps.treasury.models import Payment
        repl = self._create_replenishment()
        expense = Expense.objects.get(
            source_type='stock_replenishment', source_id=str(repl.id),
        )
        # Verify exactly 1 payment
        self.assertEqual(
            Payment.objects.filter(expense=expense, status=Payment.Status.COMPLETED).count(),
            1,
        )

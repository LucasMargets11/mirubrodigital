"""
Respaldo Impositivo — Tests for Export / Report / Filters
Run with: python manage.py test apps.tax_backup.test_exports
"""
import csv
import io
import zipfile
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.business.models import Business
from apps.treasury.models import Expense

from .models import (
    AllocationType,
    ExpenseFiscalProfile,
    FiscalDocument,
    TaxStatus,
)
from .filters import build_period_queryset, parse_period_params
from .exports import (
    sanitize_filename,
    deduplicate_filename,
    generate_csv_rows,
    build_zip_buffer,
    MAX_FILES_IN_ZIP,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def make_business(name='Export Biz'):
    b, _ = Business.objects.get_or_create(
        name=name,
        defaults={'slug': name.lower().replace(' ', '-')},
    )
    return b


def make_expense(business, name='Gasto export', amount=Decimal('1000'), due_date=None):
    return Expense.objects.create(
        business=business,
        name=name,
        amount=amount,
        due_date=due_date or date.today(),
    )


def make_profile(business, expense=None, **kwargs):
    if expense is None:
        expense = make_expense(business)
    defaults = {
        'business': business,
        'expense': expense,
        'allocation_type': AllocationType.BUSINESS,
    }
    defaults.update(kwargs)
    return ExpenseFiscalProfile.objects.create(**defaults)


def make_fiscal_doc(profile, filename='test.pdf', content=b'%PDF-fake', is_fiscal=True, **kwargs):
    defaults = {
        'fiscal_profile': profile,
        'document_type': 'factura',
        'is_fiscal_document': is_fiscal,
        'file': SimpleUploadedFile(filename, content, content_type='application/pdf'),
    }
    defaults.update(kwargs)
    return FiscalDocument.objects.create(**defaults)


# ─────────────────────────────────────────────────────────────────────────
# Filename Sanitization Tests
# ─────────────────────────────────────────────────────────────────────────

class SanitizeFilenameTest(TestCase):

    def test_basic_filename(self):
        self.assertEqual(sanitize_filename('factura.pdf'), 'factura.pdf')

    def test_strips_path_components(self):
        self.assertEqual(sanitize_filename('../../etc/passwd'), 'passwd')
        self.assertEqual(sanitize_filename('/tmp/evil.pdf'), 'evil.pdf')

    def test_removes_unsafe_characters(self):
        result = sanitize_filename('factura<>:"|?*.pdf')
        self.assertNotIn('<', result)
        self.assertNotIn('>', result)
        self.assertNotIn('|', result)
        self.assertIn('.pdf', result)

    def test_empty_becomes_documento(self):
        self.assertEqual(sanitize_filename(''), 'documento')
        self.assertEqual(sanitize_filename('...'), 'documento')

    def test_truncation(self):
        long_name = 'a' * 300 + '.pdf'
        result = sanitize_filename(long_name)
        self.assertLessEqual(len(result), 200)

    def test_unicode_stripped(self):
        result = sanitize_filename('facturá_ñ.pdf')
        # Non-ASCII removed, should still work
        self.assertIn('.pdf', result)

    def test_windows_path_separators(self):
        result = sanitize_filename('C:\\Users\\test\\doc.pdf')
        # On Linux os.path.basename doesn't split backslashes;
        # sanitize_filename strips them via the unsafe-char regex.
        self.assertNotIn('\\', result)
        self.assertIn('doc.pdf', result)


class DeduplicateFilenameTest(TestCase):

    def test_first_occurrence_unchanged(self):
        seen = {}
        self.assertEqual(deduplicate_filename('file.pdf', seen), 'file.pdf')

    def test_second_occurrence_gets_suffix(self):
        seen = {}
        deduplicate_filename('file.pdf', seen)
        self.assertEqual(deduplicate_filename('file.pdf', seen), 'file_1.pdf')

    def test_third_occurrence(self):
        seen = {}
        deduplicate_filename('file.pdf', seen)
        deduplicate_filename('file.pdf', seen)
        self.assertEqual(deduplicate_filename('file.pdf', seen), 'file_2.pdf')

    def test_no_extension(self):
        seen = {}
        deduplicate_filename('readme', seen)
        self.assertEqual(deduplicate_filename('readme', seen), 'readme_1')


# ─────────────────────────────────────────────────────────────────────────
# Period Filter Tests
# ─────────────────────────────────────────────────────────────────────────

class ParsePeriodParamsTest(TestCase):

    def test_no_params(self):
        result = parse_period_params({})
        self.assertIsNone(result['month'])
        self.assertIsNone(result['year'])
        self.assertIsNone(result['tax_status'])

    def test_valid_month_year(self):
        result = parse_period_params({'month': '6', 'year': '2025'})
        self.assertEqual(result['month'], 6)
        self.assertEqual(result['year'], 2025)

    def test_month_without_year_raises(self):
        with self.assertRaises(ValueError):
            parse_period_params({'month': '6'})

    def test_year_without_month_raises(self):
        with self.assertRaises(ValueError):
            parse_period_params({'year': '2025'})

    def test_invalid_month_raises(self):
        with self.assertRaises(ValueError):
            parse_period_params({'month': '13', 'year': '2025'})

    def test_invalid_year_raises(self):
        with self.assertRaises(ValueError):
            parse_period_params({'month': '6', 'year': '1999'})

    def test_non_numeric_raises(self):
        with self.assertRaises(ValueError):
            parse_period_params({'month': 'abc', 'year': '2025'})

    def test_tax_status_passed_through(self):
        result = parse_period_params({'tax_status': 'respaldado'})
        self.assertEqual(result['tax_status'], 'respaldado')


class BuildPeriodQuerysetTest(TestCase):

    def setUp(self):
        self.biz = make_business('Filter Biz')
        self.p1 = make_profile(self.biz)
        self.p2 = make_profile(self.biz, tax_status=TaxStatus.BACKED)

    def test_no_filters_returns_all(self):
        qs = build_period_queryset(self.biz)
        self.assertEqual(qs.count(), 2)

    def test_filter_by_status(self):
        qs = build_period_queryset(self.biz, tax_status='respaldado')
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().tax_status, TaxStatus.BACKED)

    def test_filter_by_period(self):
        today = date.today()
        qs = build_period_queryset(self.biz, month=today.month, year=today.year)
        self.assertEqual(qs.count(), 2)

    def test_filter_by_different_month_returns_empty(self):
        # Expenses have due_date=today; filtering by a different month should return 0
        qs = build_period_queryset(self.biz, month=1, year=2020)
        self.assertEqual(qs.count(), 0)


# ─────────────────────────────────────────────────────────────────────────
# CSV Generation Tests
# ─────────────────────────────────────────────────────────────────────────

class GenerateCsvRowsTest(TestCase):

    def setUp(self):
        self.biz = make_business('CSV Biz')
        self.p1 = make_profile(self.biz)
        make_fiscal_doc(self.p1)

    def test_csv_has_header_and_data(self):
        qs = build_period_queryset(self.biz)
        rows = list(generate_csv_rows(qs))
        self.assertGreaterEqual(len(rows), 2)  # header + at least 1 data row

        # Parse all rows
        combined = ''.join(rows)
        reader = csv.reader(io.StringIO(combined))
        parsed = list(reader)
        self.assertEqual(parsed[0][0], 'ID')  # header
        self.assertEqual(len(parsed), 2)  # header + 1 profile

    def test_csv_empty_queryset(self):
        qs = build_period_queryset(self.biz, month=1, year=2020)
        rows = list(generate_csv_rows(qs))
        combined = ''.join(rows)
        reader = csv.reader(io.StringIO(combined))
        parsed = list(reader)
        self.assertEqual(len(parsed), 1)  # only header

    def test_csv_proper_escaping(self):
        """Commas in expense names should be properly escaped."""
        exp = make_expense(self.biz, name='Gasto, con coma')
        p = make_profile(self.biz, expense=exp)

        qs = ExpenseFiscalProfile.objects.filter(pk=p.pk).select_related('expense')
        rows = list(generate_csv_rows(qs))
        combined = ''.join(rows)
        reader = csv.reader(io.StringIO(combined))
        parsed = list(reader)
        self.assertEqual(len(parsed), 2)
        # The expense name with comma should be properly preserved
        self.assertIn('Gasto, con coma', parsed[1][1])


# ─────────────────────────────────────────────────────────────────────────
# ZIP Generation Tests
# ─────────────────────────────────────────────────────────────────────────

class BuildZipBufferTest(TestCase):

    def setUp(self):
        self.biz = make_business('ZIP Biz')
        self.p1 = make_profile(self.biz)

    def test_zip_with_documents(self):
        make_fiscal_doc(self.p1, filename='factura_a.pdf')
        make_fiscal_doc(self.p1, filename='recibo.pdf')

        qs = build_period_queryset(self.biz)
        buf, count = build_zip_buffer(qs)
        self.assertEqual(count, 2)

        # Verify ZIP structure
        with zipfile.ZipFile(buf, 'r') as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 2)
            for name in names:
                # No absolute paths, no ..
                self.assertFalse(name.startswith('/'))
                self.assertNotIn('..', name)

    def test_zip_empty_returns_zero_count(self):
        qs = build_period_queryset(self.biz, month=1, year=2020)
        buf, count = build_zip_buffer(qs)
        self.assertEqual(count, 0)

    def test_zip_no_documents_returns_zero(self):
        # Profile exists but has no documents
        qs = build_period_queryset(self.biz)
        buf, count = build_zip_buffer(qs)
        self.assertEqual(count, 0)

    def test_zip_duplicate_filenames_get_suffix(self):
        make_fiscal_doc(self.p1, filename='factura.pdf', content=b'%PDF-1')
        make_fiscal_doc(self.p1, filename='factura.pdf', content=b'%PDF-2')

        qs = build_period_queryset(self.biz)
        buf, count = build_zip_buffer(qs)
        self.assertEqual(count, 2)

        with zipfile.ZipFile(buf, 'r') as zf:
            names = zf.namelist()
            self.assertEqual(len(names), 2)
            # Should have different names
            self.assertNotEqual(names[0], names[1])

    def test_zip_path_traversal_prevented(self):
        """Malicious filenames should be sanitized."""
        make_fiscal_doc(self.p1, filename='../../etc/passwd')

        qs = build_period_queryset(self.biz)
        buf, count = build_zip_buffer(qs)
        self.assertEqual(count, 1)

        with zipfile.ZipFile(buf, 'r') as zf:
            for name in zf.namelist():
                self.assertNotIn('..', name)
                self.assertFalse(name.startswith('/'))


# ─────────────────────────────────────────────────────────────────────────
# Monthly Report Data Tests
# ─────────────────────────────────────────────────────────────────────────

class MonthlyReportDataTest(TestCase):
    """Tests for the data that monthly-report endpoint would return."""

    def setUp(self):
        self.biz = make_business('Report Biz')
        exp1 = make_expense(self.biz, name='Gasto 1', amount=Decimal('1000'))
        exp2 = make_expense(self.biz, name='Gasto 2', amount=Decimal('2000'))
        self.p1 = make_profile(
            self.biz, expense=exp1,
            amount_net=Decimal('826.4463'), amount_vat=Decimal('173.5537'),
        )
        self.p2 = make_profile(
            self.biz, expense=exp2, tax_status=TaxStatus.BACKED,
            allocation_type=AllocationType.MIXED,
            amount_net=Decimal('1652.8926'), amount_vat=Decimal('347.1074'),
        )
        make_fiscal_doc(self.p1)
        make_fiscal_doc(self.p2)
        make_fiscal_doc(self.p2, is_fiscal=False)

    def test_aggregation_counts(self):
        qs = build_period_queryset(self.biz)
        self.assertEqual(qs.count(), 2)

    def test_status_breakdown(self):
        from django.db.models import Count
        qs = build_period_queryset(self.biz)
        by_status = dict(
            qs.values('tax_status')
            .annotate(count=Count('id'))
            .values_list('tax_status', 'count')
        )
        # After signal re-evaluation, statuses may change. Key invariant:
        # Two profiles exist and are distributed among valid TaxStatus values.
        self.assertEqual(sum(by_status.values()), 2)
        # All keys must be valid TaxStatus values
        valid = {s.value for s in TaxStatus}
        for k in by_status:
            self.assertIn(k, valid)

    def test_allocation_breakdown(self):
        from django.db.models import Count
        qs = build_period_queryset(self.biz)
        by_alloc = dict(
            qs.values('allocation_type')
            .annotate(count=Count('id'))
            .values_list('allocation_type', 'count')
        )
        self.assertEqual(by_alloc.get('business', 0), 1)
        self.assertEqual(by_alloc.get('mixed', 0), 1)

    def test_amount_aggregation(self):
        from django.db.models import Sum
        qs = build_period_queryset(self.biz)
        amounts = qs.aggregate(
            total_amount=Sum('expense__amount'),
            total_net=Sum('amount_net'),
            total_vat=Sum('amount_vat'),
        )
        self.assertEqual(amounts['total_amount'], Decimal('3000'))
        self.assertAlmostEqual(
            float(amounts['total_net']),
            float(Decimal('2479.3389')),
            places=2,
        )

    def test_document_counts(self):
        qs = build_period_queryset(self.biz)
        profile_ids = list(qs.values_list('id', flat=True))
        doc_qs = FiscalDocument.objects.filter(fiscal_profile_id__in=profile_ids)
        self.assertEqual(doc_qs.count(), 3)
        self.assertEqual(doc_qs.filter(is_fiscal_document=True).count(), 2)

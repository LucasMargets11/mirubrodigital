"""
Respaldo Impositivo — Tests for Checklist Operativo Mensual
Run with: python manage.py test apps.tax_backup.test_checklist
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.business.models import Business
from apps.treasury.models import Expense

from .models import (
    AllocationType,
    DuplicateFlag,
    DuplicateMatchType,
    DuplicateStatus,
    ExpenseFiscalProfile,
    ExpensePaymentDetail,
    FiscalDocument,
    TaxStatus,
)
from .checklist import evaluate_checklist
from .filters import build_period_queryset


# ── Helpers ──────────────────────────────────────────────────────────────

def make_business(name='Checklist Biz'):
    b, _ = Business.objects.get_or_create(
        name=name,
        defaults={'slug': name.lower().replace(' ', '-')},
    )
    return b


def make_expense(business, name='Gasto checklist', amount=Decimal('1000'), due_date=None):
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


def make_fiscal_doc(profile, is_fiscal=True, **kwargs):
    defaults = {
        'fiscal_profile': profile,
        'document_type': 'factura',
        'is_fiscal_document': is_fiscal,
        'file': SimpleUploadedFile('test.pdf', b'%PDF-fake', content_type='application/pdf'),
    }
    defaults.update(kwargs)
    return FiscalDocument.objects.create(**defaults)


def make_payment(profile, **kwargs):
    defaults = {
        'fiscal_profile': profile,
        'payment_method': 'transfer',
        'payment_date': date.today(),
        'amount': Decimal('1000'),
    }
    defaults.update(kwargs)
    return ExpensePaymentDetail.objects.create(**defaults)


# ─────────────────────────────────────────────────────────────────────────
# Rule 1: all_profiles_backed
# ─────────────────────────────────────────────────────────────────────────

class AllProfilesBackedTest(TestCase):

    def setUp(self):
        self.biz = make_business('BackedBiz')

    def test_pass_when_all_backed(self):
        make_profile(self.biz, tax_status=TaxStatus.BACKED)
        make_profile(self.biz, tax_status=TaxStatus.POTENTIALLY_DEDUCTIBLE)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'all_profiles_backed')
        self.assertTrue(item['passed'])

    def test_fail_when_registered(self):
        make_profile(self.biz, tax_status=TaxStatus.BACKED)
        p = make_profile(self.biz, tax_status=TaxStatus.REGISTERED)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'all_profiles_backed')
        self.assertFalse(item['passed'])
        self.assertIn(p.id, item['profile_ids'])

    def test_fail_when_not_backed(self):
        make_profile(self.biz, tax_status=TaxStatus.NOT_BACKED)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'all_profiles_backed')
        self.assertFalse(item['passed'])

    def test_pass_empty_period(self):
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'all_profiles_backed')
        self.assertTrue(item['passed'])


# ─────────────────────────────────────────────────────────────────────────
# Rule 2: no_missing_documents
# ─────────────────────────────────────────────────────────────────────────

class NoMissingDocumentsTest(TestCase):

    def setUp(self):
        self.biz = make_business('DocsBiz')

    def test_pass_all_have_fiscal_doc(self):
        p1 = make_profile(self.biz)
        p2 = make_profile(self.biz, allocation_type=AllocationType.MIXED)
        make_fiscal_doc(p1)
        make_fiscal_doc(p2)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'no_missing_documents')
        self.assertTrue(item['passed'])

    def test_fail_missing_doc(self):
        p1 = make_profile(self.biz)
        make_fiscal_doc(p1)
        p2 = make_profile(self.biz)  # no doc
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'no_missing_documents')
        self.assertFalse(item['passed'])
        self.assertIn(p2.id, item['profile_ids'])

    def test_personal_not_required(self):
        """Personal profiles don't need fiscal docs."""
        make_profile(self.biz, allocation_type=AllocationType.PERSONAL)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'no_missing_documents')
        self.assertTrue(item['passed'])

    def test_non_fiscal_doc_not_counted(self):
        """A non-fiscal doc doesn't satisfy the requirement."""
        p = make_profile(self.biz)
        make_fiscal_doc(p, is_fiscal=False)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'no_missing_documents')
        self.assertFalse(item['passed'])


# ─────────────────────────────────────────────────────────────────────────
# Rule 3: all_payments_covered
# ─────────────────────────────────────────────────────────────────────────

class AllPaymentsCoveredTest(TestCase):

    def setUp(self):
        self.biz = make_business('PayBiz')

    def test_pass_all_have_payment(self):
        p = make_profile(self.biz)
        make_payment(p)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'all_payments_covered')
        self.assertTrue(item['passed'])

    def test_fail_missing_payment(self):
        p = make_profile(self.biz)  # no payment
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'all_payments_covered')
        self.assertFalse(item['passed'])
        self.assertIn(p.id, item['profile_ids'])

    def test_personal_not_required(self):
        make_profile(self.biz, allocation_type=AllocationType.PERSONAL)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'all_payments_covered')
        self.assertTrue(item['passed'])


# ─────────────────────────────────────────────────────────────────────────
# Rule 4: no_pending_reviews
# ─────────────────────────────────────────────────────────────────────────

class NoPendingReviewsTest(TestCase):

    def setUp(self):
        self.biz = make_business('ReviewBiz')

    def test_pass_no_reviews(self):
        make_profile(self.biz, tax_status=TaxStatus.BACKED)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'no_pending_reviews')
        self.assertTrue(item['passed'])

    def test_fail_has_review(self):
        p = make_profile(self.biz, tax_status=TaxStatus.NEEDS_REVIEW)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'no_pending_reviews')
        self.assertFalse(item['passed'])
        self.assertIn(p.id, item['profile_ids'])


# ─────────────────────────────────────────────────────────────────────────
# Rule 6: no_open_duplicates
# ─────────────────────────────────────────────────────────────────────────

class NoOpenDuplicatesTest(TestCase):

    def setUp(self):
        self.biz = make_business('DupeBiz')

    def test_pass_no_duplicates(self):
        make_profile(self.biz)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'no_open_duplicates')
        self.assertTrue(item['passed'])

    def test_fail_pending_duplicate(self):
        p1 = make_profile(self.biz)
        p2 = make_profile(self.biz)
        # Ensure canonical order
        low, high = sorted([p1, p2], key=lambda p: p.id)
        DuplicateFlag.objects.create(
            fiscal_profile=low,
            matched_profile=high,
            match_type=DuplicateMatchType.EXACT_AMOUNT_DATE,
            status=DuplicateStatus.PENDING,
        )
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'no_open_duplicates')
        self.assertFalse(item['passed'])

    def test_pass_dismissed_duplicate(self):
        p1 = make_profile(self.biz)
        p2 = make_profile(self.biz)
        low, high = sorted([p1, p2], key=lambda p: p.id)
        DuplicateFlag.objects.create(
            fiscal_profile=low,
            matched_profile=high,
            match_type=DuplicateMatchType.EXACT_AMOUNT_DATE,
            status=DuplicateStatus.DISMISSED,
        )
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        item = next(i for i in result['items'] if i['key'] == 'no_open_duplicates')
        self.assertTrue(item['passed'])


# ─────────────────────────────────────────────────────────────────────────
# Aggregate checklist result
# ─────────────────────────────────────────────────────────────────────────

class EvaluateChecklistTest(TestCase):

    def setUp(self):
        self.biz = make_business('AggregateBiz')

    def test_empty_period_all_pass(self):
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        self.assertTrue(result['ready'])
        self.assertEqual(result['score'], 5)
        self.assertEqual(result['total'], 5)
        self.assertEqual(len(result['items']), 5)

    def test_period_string_format(self):
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs, month=4, year=2026)
        self.assertEqual(result['period'], '2026-04')

    def test_period_none_when_no_params(self):
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        self.assertIsNone(result['period'])

    def test_score_counts_passed(self):
        # Create a profile with status=REGISTERED (fails rule 1) and no docs (fails rule 2)
        # and no payments (fails rule 3)
        make_profile(self.biz, tax_status=TaxStatus.REGISTERED)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        self.assertFalse(result['ready'])
        # Rule 1 fails (REGISTERED), rule 2 fails (no fiscal doc), rule 3 fails (no payment)
        # Rules 4, 5 pass
        self.assertEqual(result['score'], 2)

    def test_ready_true_when_all_pass(self):
        p = make_profile(self.biz, tax_status=TaxStatus.BACKED)
        # Create a *complete* fiscal doc so rule engine keeps BACKED status
        make_fiscal_doc(
            p,
            issuer_tax_id='20-12345678-9',
            buyer_tax_id='30-98765432-1',
            total=Decimal('1000'),
        )
        make_payment(p)
        # Refresh to get signal-evaluated status
        p.refresh_from_db()
        self.assertEqual(p.tax_status, TaxStatus.BACKED)
        qs = build_period_queryset(self.biz)
        result = evaluate_checklist(self.biz, qs)
        self.assertTrue(result['ready'])
        self.assertEqual(result['score'], 5)

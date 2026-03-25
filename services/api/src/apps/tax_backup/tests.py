"""
Respaldo Impositivo — Tests
Run with: python manage.py test apps.tax_backup.tests
"""
from decimal import Decimal
from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.business.models import Business
from apps.treasury.models import Expense, TransactionCategory, FixedExpense, FixedExpensePeriod
from apps.tax_backup.models import (
    AllocationType,
    DuplicateFlag,
    DuplicateMatchType,
    DuplicateStatus,
    ExpenseFiscalProfile,
    ExpensePaymentDetail,
    FiscalDocument,
    SourceType,
    TaxStatus,
    TaxStatusLog,
)
from apps.tax_backup.rules import (
    RuleResult,
    create_duplicate_flags,
    detect_duplicates,
    evaluate_tax_status,
    rule_amount_mismatch,
    rule_backed,
    rule_capital_asset_review,
    rule_mixed_allocation,
    rule_no_fiscal_document,
    rule_personal_allocation,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def make_business(name='Test Biz'):
    b, _ = Business.objects.get_or_create(
        name=name,
        defaults={'slug': name.lower().replace(' ', '-')},
    )
    return b


def make_expense(business, name='Gasto prueba', amount=Decimal('1000'), due_date=None):
    return Expense.objects.create(
        business=business,
        name=name,
        amount=amount,
        due_date=due_date or date.today(),
    )


def make_profile(business, expense=None, fixed_expense_period=None, **kwargs):
    """Create a fiscal profile. Supports both expense and fixed_expense_period origins."""
    if expense is None and fixed_expense_period is None:
        expense = make_expense(business)
    source_type = SourceType.FIXED_EXPENSE_PERIOD if fixed_expense_period else SourceType.EXPENSE
    defaults = {
        'business': business,
        'expense': expense,
        'fixed_expense_period': fixed_expense_period,
        'source_type': source_type,
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


# ─────────────────────────────────────────────────────────────────────────
# Rule Engine Tests
# ─────────────────────────────────────────────────────────────────────────

class RulePersonalAllocationTest(TestCase):
    def setUp(self):
        self.biz = make_business('Biz Rules Personal')
        self.profile = make_profile(self.biz, allocation_type=AllocationType.PERSONAL)

    def test_personal_returns_not_backed(self):
        result = rule_personal_allocation(self.profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, TaxStatus.NOT_BACKED)
        self.assertEqual(result.rule_code, 'RULE_PERSONAL')

    def test_business_returns_none(self):
        self.profile.allocation_type = AllocationType.BUSINESS
        result = rule_personal_allocation(self.profile)
        self.assertIsNone(result)


class RuleNoFiscalDocumentTest(TestCase):
    def setUp(self):
        self.biz = make_business('Biz Rules NoDoc')
        self.profile = make_profile(self.biz)

    def test_no_docs_returns_not_backed(self):
        result = rule_no_fiscal_document(self.profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, TaxStatus.NOT_BACKED)
        self.assertEqual(result.rule_code, 'RULE_NO_DOC')

    def test_non_fiscal_doc_returns_not_backed(self):
        make_fiscal_doc(self.profile, is_fiscal=False)
        self.profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=self.profile.pk)
        result = rule_no_fiscal_document(self.profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_code, 'RULE_NO_FISCAL_DOC')

    def test_fiscal_doc_returns_none(self):
        make_fiscal_doc(self.profile, is_fiscal=True)
        self.profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=self.profile.pk)
        result = rule_no_fiscal_document(self.profile)
        self.assertIsNone(result)


class RuleCapitalAssetTest(TestCase):
    def setUp(self):
        self.biz = make_business('Biz Rules Capital')

    def test_capital_asset_needs_review(self):
        profile = make_profile(self.biz, is_capital_asset=True)
        result = rule_capital_asset_review(profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, TaxStatus.NEEDS_REVIEW)

    def test_non_capital_returns_none(self):
        profile = make_profile(self.biz, is_capital_asset=False)
        result = rule_capital_asset_review(profile)
        self.assertIsNone(result)


class RuleMixedAllocationTest(TestCase):
    def setUp(self):
        self.biz = make_business('Biz Rules Mixed')
        self.profile = make_profile(self.biz, allocation_type=AllocationType.MIXED)

    def test_mixed_with_fiscal_doc_potentially_deductible(self):
        make_fiscal_doc(self.profile, is_fiscal=True)
        self.profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=self.profile.pk)
        result = rule_mixed_allocation(self.profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, TaxStatus.POTENTIALLY_DEDUCTIBLE)

    def test_mixed_without_fiscal_doc_returns_none(self):
        result = rule_mixed_allocation(self.profile)
        self.assertIsNone(result)


class RuleAmountMismatchTest(TestCase):
    def setUp(self):
        self.biz = make_business('Biz Rules Amount')
        expense = make_expense(self.biz, amount=Decimal('1000'))
        self.profile = make_profile(self.biz, expense=expense)

    def test_matching_amount_returns_none(self):
        make_fiscal_doc(self.profile, total=Decimal('1000'))
        self.profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=self.profile.pk)
        result = rule_amount_mismatch(self.profile)
        self.assertIsNone(result)

    def test_mismatched_amount_needs_review(self):
        make_fiscal_doc(self.profile, total=Decimal('500'))
        self.profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=self.profile.pk)
        result = rule_amount_mismatch(self.profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, TaxStatus.NEEDS_REVIEW)
        self.assertEqual(result.rule_code, 'RULE_AMOUNT_MISMATCH')


class RuleBackedTest(TestCase):
    def setUp(self):
        self.biz = make_business('Biz Rules Backed')
        self.profile = make_profile(self.biz, allocation_type=AllocationType.BUSINESS)

    def test_complete_fiscal_doc_returns_backed(self):
        make_fiscal_doc(
            self.profile,
            is_fiscal=True,
            issuer_tax_id='20-12345678-9',
            buyer_tax_id='20-98765432-1',
            total=Decimal('1000'),
        )
        self.profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=self.profile.pk)
        result = rule_backed(self.profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, TaxStatus.BACKED)

    def test_incomplete_fiscal_doc_returns_none(self):
        make_fiscal_doc(self.profile, is_fiscal=True, issuer_tax_id='20-12345678-9')
        self.profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=self.profile.pk)
        result = rule_backed(self.profile)
        self.assertIsNone(result)


class EvaluateTaxStatusIntegrationTest(TestCase):
    """Verifica la cadena completa de reglas."""

    def setUp(self):
        self.biz = make_business('Biz Evaluate')

    def test_new_profile_no_docs_is_not_backed(self):
        profile = make_profile(self.biz)
        profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=profile.pk)
        result = evaluate_tax_status(profile)
        self.assertEqual(result.status, TaxStatus.NOT_BACKED)

    def test_personal_overrides_everything(self):
        profile = make_profile(self.biz, allocation_type=AllocationType.PERSONAL)
        make_fiscal_doc(profile, is_fiscal=True, issuer_tax_id='x', buyer_tax_id='y', total=Decimal('1'))
        profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=profile.pk)
        result = evaluate_tax_status(profile)
        self.assertEqual(result.status, TaxStatus.NOT_BACKED)
        self.assertEqual(result.rule_code, 'RULE_PERSONAL')

    def test_backed_full_flow(self):
        expense = make_expense(self.biz, amount=Decimal('1000'))
        profile = make_profile(self.biz, expense=expense, allocation_type=AllocationType.BUSINESS)
        make_fiscal_doc(
            profile,
            is_fiscal=True,
            issuer_tax_id='20-12345678-9',
            buyer_tax_id='20-98765432-1',
            total=Decimal('1000'),
        )
        profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=profile.pk)
        result = evaluate_tax_status(profile)
        self.assertEqual(result.status, TaxStatus.BACKED)


# ─────────────────────────────────────────────────────────────────────────
# DuplicateFlag Tests
# ─────────────────────────────────────────────────────────────────────────

class DuplicateFlagCanonicalPairTest(TestCase):
    def setUp(self):
        self.biz = make_business('Biz Dup')
        self.p1 = make_profile(self.biz)
        self.p2 = make_profile(self.biz)

    def test_save_normalizes_order(self):
        """fiscal_profile_id siempre debe ser < matched_profile_id."""
        flag = DuplicateFlag.objects.create(
            fiscal_profile=self.p2,
            matched_profile=self.p1,
            match_type=DuplicateMatchType.EXACT_AMOUNT_DATE,
        )
        self.assertLess(flag.fiscal_profile_id, flag.matched_profile_id)

    def test_unique_constraint_prevents_mirror(self):
        DuplicateFlag.objects.create(
            fiscal_profile=self.p1,
            matched_profile=self.p2,
            match_type=DuplicateMatchType.EXACT_AMOUNT_DATE,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            DuplicateFlag.objects.create(
                fiscal_profile=self.p2,
                matched_profile=self.p1,
                match_type=DuplicateMatchType.EXACT_AMOUNT_DATE,
            )


class DuplicateDetectionTest(TestCase):
    def setUp(self):
        self.biz = make_business('Biz Detect')
        self.p1 = make_profile(self.biz)
        self.p2 = make_profile(self.biz)

    def test_detect_duplicates_by_invoice_data(self):
        common = {
            'issuer_tax_id': '20-12345678-9',
            'invoice_number': 'A-0001-00001234',
            'issue_date': date(2025, 6, 15),
            'total': Decimal('5000'),
            'is_fiscal_document': True,
        }
        make_fiscal_doc(self.p1, **common)
        make_fiscal_doc(self.p2, **common)

        matches = detect_duplicates(self.p1)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0].pk, self.p2.pk)

    def test_create_duplicate_flags_idempotent(self):
        common = {
            'issuer_tax_id': '20-12345678-9',
            'invoice_number': 'A-0001-00001234',
            'issue_date': date(2025, 6, 15),
            'total': Decimal('5000'),
            'is_fiscal_document': True,
        }
        make_fiscal_doc(self.p1, **common)
        make_fiscal_doc(self.p2, **common)

        # Signals already fire create_duplicate_flags on FiscalDocument save,
        # so at this point flags may already exist. The key invariant is
        # that calling again produces no new flags (idempotency).
        existing = DuplicateFlag.objects.count()
        self.assertGreaterEqual(existing, 1)

        flags_new = create_duplicate_flags(self.p1)
        self.assertEqual(len(flags_new), 0)

        self.assertEqual(DuplicateFlag.objects.count(), existing)


# ─────────────────────────────────────────────────────────────────────────
# TaxStatusLog Tests
# ─────────────────────────────────────────────────────────────────────────

class TaxStatusLogTest(TestCase):
    def test_log_created_on_status_change(self):
        biz = make_business('Biz Log')
        expense = make_expense(biz, amount=Decimal('1000'))
        profile = make_profile(biz, expense=expense)
        # Inicialmente registrado, sin docs → rule engine lo pasa a not_backed
        profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=profile.pk)
        result = evaluate_tax_status(profile)
        # Simular el cambio
        old = profile.tax_status
        profile.tax_status = result.status
        profile.save(update_fields=['tax_status'])
        TaxStatusLog.objects.create(
            fiscal_profile=profile,
            previous_status=old,
            new_status=result.status,
            rule_code=result.rule_code,
        )
        self.assertEqual(TaxStatusLog.objects.filter(fiscal_profile=profile).count(), 1)
        log = TaxStatusLog.objects.first()
        self.assertEqual(log.new_status, TaxStatus.NOT_BACKED)


# ─────────────────────────────────────────────────────────────────────────
# Model Basics
# ─────────────────────────────────────────────────────────────────────────

class ExpenseFiscalProfileModelTest(TestCase):
    def test_str_representation(self):
        biz = make_business('Biz Str')
        profile = make_profile(biz)
        self.assertIn('FiscalProfile', str(profile))

    def test_default_tax_status_is_registered(self):
        biz = make_business('Biz Default')
        profile = make_profile(biz)
        self.assertEqual(profile.tax_status, TaxStatus.REGISTERED)


class PaymentDetailModelTest(TestCase):
    def test_create_payment_detail(self):
        biz = make_business('Biz Pay')
        profile = make_profile(biz)
        pd = ExpensePaymentDetail.objects.create(
            fiscal_profile=profile,
            payment_method='transfer',
            payment_date=date.today(),
            amount=Decimal('500'),
            reference='CBU-001',
        )
        self.assertIn('Transferencia', str(pd))


# ─────────────────────────────────────────────────────────────────────────
# Dual Origin Tests
# ─────────────────────────────────────────────────────────────────────────

class DualOriginModelTest(TestCase):
    """Tests for the dual-origin (expense | fixed_expense_period) model."""

    def setUp(self):
        self.biz = make_business('Biz Dual')

    def test_expense_origin_source_properties(self):
        expense = make_expense(self.biz, name='Test Expense', amount=Decimal('2000'))
        profile = make_profile(self.biz, expense=expense)
        self.assertEqual(profile.source_type, SourceType.EXPENSE)
        self.assertEqual(profile.source_name, 'Test Expense')
        self.assertEqual(profile.source_amount, Decimal('2000'))

    def test_fixed_expense_period_origin_source_properties(self):
        fe = FixedExpense.objects.create(
            business=self.biz, name='Alquiler', default_amount=Decimal('50000'),
            frequency='monthly', due_day=5,
        )
        fep = FixedExpensePeriod.objects.create(
            fixed_expense=fe, period=date(2025, 6, 1),
            amount=Decimal('50000'), status='pending',
        )
        profile = make_profile(self.biz, expense=None, fixed_expense_period=fep)
        self.assertEqual(profile.source_type, SourceType.FIXED_EXPENSE_PERIOD)
        self.assertIn('Alquiler', profile.source_name)
        self.assertEqual(profile.source_amount, Decimal('50000'))

    def test_exactly_one_source_constraint(self):
        """Cannot have both expense AND fixed_expense_period set."""
        expense = make_expense(self.biz)
        fe = FixedExpense.objects.create(
            business=self.biz, name='Servicio', default_amount=Decimal('1000'),
            frequency='monthly', due_day=1,
        )
        fep = FixedExpensePeriod.objects.create(
            fixed_expense=fe, period=date(2025, 1, 1),
            amount=Decimal('1000'), status='pending',
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ExpenseFiscalProfile.objects.create(
                business=self.biz,
                expense=expense,
                fixed_expense_period=fep,
                source_type=SourceType.EXPENSE,
            )


# ─────────────────────────────────────────────────────────────────────────
# Auto-Provisioning Service Tests
# ─────────────────────────────────────────────────────────────────────────

class AutoProvisioningTest(TestCase):
    """Tests for ensure_fiscal_profile_for_* services."""

    def setUp(self):
        self.biz = make_business('Biz AutoProv')

    def test_ensure_for_paid_expense(self):
        from apps.tax_backup.services import ensure_fiscal_profile_for_expense
        expense = make_expense(self.biz, amount=Decimal('3000'))
        expense.status = Expense.Status.PAID
        expense.save()
        profile = ensure_fiscal_profile_for_expense(expense)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.source_type, SourceType.EXPENSE)
        self.assertEqual(profile.expense, expense)

    def test_ensure_for_unpaid_expense_returns_none(self):
        from apps.tax_backup.services import ensure_fiscal_profile_for_expense
        expense = make_expense(self.biz)
        profile = ensure_fiscal_profile_for_expense(expense)
        self.assertIsNone(profile)

    def test_ensure_idempotent(self):
        from apps.tax_backup.services import ensure_fiscal_profile_for_expense
        expense = make_expense(self.biz)
        expense.status = Expense.Status.PAID
        expense.save()
        p1 = ensure_fiscal_profile_for_expense(expense)
        p2 = ensure_fiscal_profile_for_expense(expense)
        self.assertEqual(p1.pk, p2.pk)
        self.assertEqual(ExpenseFiscalProfile.objects.filter(expense=expense).count(), 1)

    def test_ensure_for_paid_fixed_expense_period(self):
        from apps.tax_backup.services import ensure_fiscal_profile_for_fixed_expense_period
        fe = FixedExpense.objects.create(
            business=self.biz, name='Seguros', default_amount=Decimal('8000'),
            frequency='monthly', due_day=15,
        )
        fep = FixedExpensePeriod.objects.create(
            fixed_expense=fe, period=date(2025, 7, 1),
            amount=Decimal('8000'), status=FixedExpensePeriod.Status.PAID,
        )
        profile = ensure_fiscal_profile_for_fixed_expense_period(fep)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.source_type, SourceType.FIXED_EXPENSE_PERIOD)
        self.assertEqual(profile.fixed_expense_period, fep)


# ─────────────────────────────────────────────────────────────────────────
# Plans Alias Resolution Tests
# ─────────────────────────────────────────────────────────────────────────

class PlanEntitlementAliasTest(TestCase):
    """Tests for plan alias resolution in entitlements."""

    def test_start_resolves_to_starter(self):
        from apps.business.entitlements import get_plan_entitlements
        start_ents = get_plan_entitlements('start')
        starter_ents = get_plan_entitlements('starter')
        self.assertEqual(start_ents, starter_ents)

    def test_plus_resolves_to_business(self):
        from apps.business.entitlements import get_plan_entitlements
        plus_ents = get_plan_entitlements('plus')
        biz_ents = get_plan_entitlements('business')
        self.assertEqual(plus_ents, biz_ents)

    def test_starter_has_basic_entitlements(self):
        from apps.business.entitlements import get_plan_entitlements
        ents = get_plan_entitlements('starter')
        self.assertIn('gestion.products', ents)
        self.assertNotIn('gestion.treasury', ents)

    def test_business_has_tax_backup(self):
        from apps.business.entitlements import get_plan_entitlements
        ents = get_plan_entitlements('business')
        self.assertIn('gestion.tax_backup', ents)


# ─────────────────────────────────────────────────────────────────────────
# Serializer source_* Contract Tests
# ─────────────────────────────────────────────────────────────────────────

class SourceFieldsSerializerTest(TestCase):
    """Verify serializers return canonical source_* fields for both origins."""

    def setUp(self):
        self.biz = make_business('Biz Serializer')

    def _serialize_list(self, profile):
        from apps.tax_backup.serializers import ExpenseFiscalProfileListSerializer
        qs = ExpenseFiscalProfile.objects.select_related(
            'expense', 'fixed_expense_period__fixed_expense',
        ).filter(pk=profile.pk)
        return ExpenseFiscalProfileListSerializer(qs.first()).data

    def _serialize_detail(self, profile):
        from apps.tax_backup.serializers import ExpenseFiscalProfileSerializer
        qs = ExpenseFiscalProfile.objects.select_related(
            'expense', 'fixed_expense_period__fixed_expense',
        ).prefetch_related('documents', 'payment_details', 'status_logs').filter(pk=profile.pk)
        return ExpenseFiscalProfileSerializer(qs.first()).data

    def test_expense_origin_list_fields(self):
        expense = make_expense(self.biz, name='Gasto X', amount=Decimal('1500'), due_date=date(2026, 3, 15))
        profile = make_profile(self.biz, expense=expense)
        data = self._serialize_list(profile)
        self.assertEqual(data['source_type'], 'expense')
        self.assertEqual(data['source_name'], 'Gasto X')
        self.assertEqual(Decimal(data['source_amount']), Decimal('1500'))
        self.assertEqual(data['source_due_date'], '2026-03-15')
        self.assertIsNone(data['source_period_label'])
        self.assertEqual(data['source_status'], 'pending')

    def test_fixed_expense_period_origin_list_fields(self):
        fe = FixedExpense.objects.create(
            business=self.biz, name='Alquiler', default_amount=Decimal('50000'),
            frequency='monthly', due_day=5,
        )
        fep = FixedExpensePeriod.objects.create(
            fixed_expense=fe, period=date(2026, 3, 1),
            amount=Decimal('50000'), status='pending',
        )
        profile = make_profile(self.biz, expense=None, fixed_expense_period=fep)
        data = self._serialize_list(profile)
        self.assertEqual(data['source_type'], 'fixed_expense_period')
        self.assertIn('Alquiler', data['source_name'])
        self.assertEqual(Decimal(data['source_amount']), Decimal('50000'))
        self.assertEqual(data['source_period_label'], '2026-03')
        self.assertEqual(data['source_status'], 'pending')

    def test_expense_origin_detail_fields(self):
        expense = make_expense(self.biz, name='Detalle Y', amount=Decimal('2500'))
        profile = make_profile(self.biz, expense=expense)
        data = self._serialize_detail(profile)
        self.assertEqual(data['source_type'], 'expense')
        self.assertEqual(data['source_name'], 'Detalle Y')
        self.assertEqual(Decimal(data['source_amount']), Decimal('2500'))
        self.assertIsNone(data['source_period_label'])

    def test_fixed_expense_period_origin_detail_fields(self):
        fe = FixedExpense.objects.create(
            business=self.biz, name='Internet', default_amount=Decimal('8000'),
            frequency='monthly', due_day=10,
        )
        fep = FixedExpensePeriod.objects.create(
            fixed_expense=fe, period=date(2026, 1, 1),
            amount=Decimal('8000'), status='paid',
        )
        profile = make_profile(self.biz, expense=None, fixed_expense_period=fep)
        data = self._serialize_detail(profile)
        self.assertEqual(data['source_type'], 'fixed_expense_period')
        self.assertIn('Internet', data['source_name'])
        self.assertEqual(Decimal(data['source_amount']), Decimal('8000'))
        self.assertEqual(data['source_period_label'], '2026-01')
        self.assertEqual(data['source_status'], 'paid')

    def test_source_name_never_empty(self):
        expense = make_expense(self.biz, name='Non-empty', amount=Decimal('100'))
        profile = make_profile(self.biz, expense=expense)
        data = self._serialize_list(profile)
        self.assertTrue(len(data['source_name']) > 0)

    def test_source_amount_not_null_when_origin_has_amount(self):
        expense = make_expense(self.biz, amount=Decimal('999'))
        profile = make_profile(self.biz, expense=expense)
        data = self._serialize_list(profile)
        self.assertIsNotNone(data['source_amount'])

from django.contrib import admin

from .models import (
    DuplicateFlag,
    ExpenseFiscalProfile,
    ExpensePaymentDetail,
    FiscalDocument,
    RecurringServiceProfile,
    ServicePeriodAlert,
    TaxStatusLog,
)


@admin.register(ExpenseFiscalProfile)
class ExpenseFiscalProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'expense', 'fixed_expense_period', 'source_type', 'business', 'tax_status', 'allocation_type', 'created_at')
    list_filter = ('source_type', 'tax_status', 'allocation_type', 'is_capital_asset')
    search_fields = ('expense__name', 'fixed_expense_period__fixed_expense__name')
    raw_id_fields = ('expense', 'fixed_expense_period', 'business', 'created_by')


@admin.register(RecurringServiceProfile)
class RecurringServiceProfileAdmin(admin.ModelAdmin):
    """Legacy table — kept for DB compat. No production creation path."""
    list_display = ('id', 'fixed_expense', 'business', 'provider_name', 'needs_monthly_invoice')
    list_filter = ('needs_monthly_invoice',)
    search_fields = ('provider_name', 'provider_tax_id')
    raw_id_fields = ('fixed_expense', 'business')


@admin.register(FiscalDocument)
class FiscalDocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'fiscal_profile', 'document_type', 'invoice_number', 'total', 'is_fiscal_document')
    list_filter = ('document_type', 'is_fiscal_document', 'parse_status')
    raw_id_fields = ('fiscal_profile',)


@admin.register(ExpensePaymentDetail)
class ExpensePaymentDetailAdmin(admin.ModelAdmin):
    list_display = ('id', 'fiscal_profile', 'payment_method', 'payment_date', 'amount')
    list_filter = ('payment_method',)
    raw_id_fields = ('fiscal_profile',)


@admin.register(TaxStatusLog)
class TaxStatusLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'fiscal_profile', 'previous_status', 'new_status', 'rule_code', 'created_at')
    list_filter = ('new_status', 'rule_code')
    raw_id_fields = ('fiscal_profile',)


@admin.register(ServicePeriodAlert)
class ServicePeriodAlertAdmin(admin.ModelAdmin):
    """Legacy table — kept for DB compat. No production creation path."""
    list_display = ('id', 'service_profile', 'alert_type', 'status', 'created_at')
    list_filter = ('alert_type', 'status')
    raw_id_fields = ('service_profile', 'fixed_expense_period')


@admin.register(DuplicateFlag)
class DuplicateFlagAdmin(admin.ModelAdmin):
    list_display = ('id', 'fiscal_profile', 'matched_profile', 'match_type', 'status', 'created_at')
    list_filter = ('match_type', 'status')
    raw_id_fields = ('fiscal_profile', 'matched_profile')

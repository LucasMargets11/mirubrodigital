from django.contrib import admin
from .models import Account, TransactionCategory, Transaction, ExpenseTemplate, Expense, Employee, PayrollPayment, TreasurySettings

@admin.register(TreasurySettings)
class TreasurySettingsAdmin(admin.ModelAdmin):
    list_display = ('business',)

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'business', 'is_active', 'opening_balance')
    list_filter = ('business', 'type', 'is_active')
    search_fields = ('name',)

@admin.register(TransactionCategory)
class TransactionCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'direction', 'business', 'is_active')
    list_filter = ('business', 'direction', 'is_active')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('occurred_at', 'direction', 'amount', 'account', 'status')
    list_filter = ('business', 'direction', 'status', 'account')
    search_fields = ('description', 'reference_id')

@admin.register(ExpenseTemplate)
class ExpenseTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'amount', 'frequency', 'due_day')
    list_filter = ('business', 'frequency')

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('name', 'amount', 'due_date', 'status', 'business')
    list_filter = ('business', 'status')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'business', 'pay_frequency', 'is_active')
    list_filter = ('business', 'is_active')

@admin.register(PayrollPayment)
class PayrollPaymentAdmin(admin.ModelAdmin):
    list_display = ('employee', 'amount', 'paid_at', 'business')
    list_filter = ('business', 'employee')

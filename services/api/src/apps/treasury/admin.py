from django.contrib import admin
from .models import Account, TransactionCategory, Transaction, ExpenseTemplate, Expense, Employee, PayrollPayment, TreasurySettings, FixedExpense, FixedExpensePeriod

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

@admin.register(FixedExpense)
class FixedExpenseAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'default_amount', 'due_day', 'is_active')
    list_filter = ('business', 'is_active')
    search_fields = ('name',)

@admin.register(FixedExpensePeriod)
class FixedExpensePeriodAdmin(admin.ModelAdmin):
    list_display = ('fixed_expense', 'period', 'amount', 'status', 'due_date', 'paid_at')
    list_filter = ('status', 'fixed_expense__business', 'period')
    search_fields = ('fixed_expense__name',)

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

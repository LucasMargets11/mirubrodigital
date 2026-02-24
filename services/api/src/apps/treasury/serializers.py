from rest_framework import serializers
from django.db import models as db_models
from .models import Account, TransactionCategory, Transaction, ExpenseTemplate, Expense, Employee, PayrollPayment, FixedExpense, FixedExpensePeriod, TreasurySettings, Budget
from apps.business.models import Business

class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = '__all__'
        read_only_fields = ('business', 'created_at', 'updated_at')

    def get_balance(self, obj):
        posted = obj.transactions.filter(status='posted')
        in_total = posted.filter(direction=Transaction.Direction.IN).aggregate(s=db_models.Sum('amount'))['s'] or 0
        out_total = posted.filter(direction=Transaction.Direction.OUT).aggregate(s=db_models.Sum('amount'))['s'] or 0
        return float(obj.opening_balance) + float(in_total) - float(out_total)

class TransactionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionCategory
        fields = '__all__'
        read_only_fields = ('business',)

class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    transaction_type = serializers.SerializerMethodField()
    reference_details = serializers.SerializerMethodField()
    related_account_name = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = '__all__'
        read_only_fields = ('business', 'created_at', 'created_by', 'transfer_group_id', 'status')

    def get_created_by_name(self, obj):
        if obj.created_by:
            return getattr(obj.created_by, 'get_full_name', lambda: str(obj.created_by))()
        return None

    def get_transaction_type(self, obj):
        """Determine the type of transaction for better UI display"""
        if obj.transfer_group_id:
            return 'transfer'
        if obj.reference_type == 'expense':
            return 'expense'
        if obj.reference_type == 'fixed_expense_period':
            return 'fixed_expense'
        if obj.reference_type == 'payroll':
            return 'payroll'
        if obj.reference_type == 'sale':
            return 'sale'
        if obj.reference_type == 'reconciliation':
            return 'reconciliation'
        if obj.reference_type == 'stock_replenishment':
            return 'stock_replenishment'
        return 'other'

    def get_related_account_name(self, obj):
        """For transfers: return the name of the other-side account."""
        if not obj.transfer_group_id:
            return None
        try:
            other = Transaction.objects.filter(
                transfer_group_id=obj.transfer_group_id
            ).exclude(pk=obj.pk).select_related('account').first()
            if other:
                return other.account.name
        except Exception:
            pass
        return None

    def get_reference_details(self, obj):
        """Get additional details about the referenced entity"""
        if not obj.reference_type or not obj.reference_id:
            return None

        try:
            if obj.reference_type == 'expense':
                expense = Expense.objects.filter(id=obj.reference_id).first()
                if expense:
                    return {'name': expense.name, 'due_date': expense.due_date.isoformat()}
            elif obj.reference_type == 'fixed_expense_period':
                period = FixedExpensePeriod.objects.select_related('fixed_expense').filter(id=obj.reference_id).first()
                if period:
                    return {
                        'name': period.fixed_expense.name,
                        'period': period.period.strftime('%Y-%m'),
                        'due_date': period.due_date.isoformat() if period.due_date else None
                    }
            elif obj.reference_type == 'payroll':
                payment = PayrollPayment.objects.select_related('employee').filter(id=obj.reference_id).first()
                if payment:
                    return {'employee_name': payment.employee.full_name}
            elif obj.reference_type == 'stock_replenishment':
                try:
                    from apps.inventory.models import StockReplenishment
                    repl = StockReplenishment.objects.filter(id=obj.reference_id).first()
                    if repl:
                        return {
                            'supplier_name': repl.supplier_name,
                            'invoice_number': repl.invoice_number,
                            'occurred_at': repl.occurred_at.isoformat(),
                            'status': repl.status,
                        }
                except Exception:
                    pass
        except Exception:
            pass

        return None

class ExpenseTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseTemplate
        fields = '__all__'
        read_only_fields = ('business',)

class ExpenseSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    paid_account_name = serializers.CharField(source='paid_account.name', read_only=True, allow_null=True)
    source_details = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = (
            'business', 'created_at', 'paid_at', 'paid_account',
            'payment_transaction', 'source_type', 'source_id', 'is_auto_generated',
        )

    def get_source_details(self, obj):
        """Return extra info about the auto-generation source for frontend links/badges."""
        if obj.source_type != 'stock_replenishment' or not obj.source_id:
            return None
        try:
            from apps.inventory.models import StockReplenishment
            repl = StockReplenishment.objects.filter(id=obj.source_id).only(
                'id', 'supplier_name', 'invoice_number', 'occurred_at', 'status'
            ).first()
            if not repl:
                return None
            return {
                'type': 'stock_replenishment',
                'id': str(repl.id),
                'label': f'Reposición — {repl.supplier_name}' + (
                    f' ({repl.invoice_number})' if repl.invoice_number else ''
                ),
                'supplier_name': repl.supplier_name,
                'invoice_number': repl.invoice_number,
                'occurred_at': repl.occurred_at.isoformat(),
                'status': repl.status,
                # frontend route hint so UI can build the link without hard-coding it
                'route_hint': f'inventory/replenishments/{repl.id}',
            }
        except Exception:
            return None

class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = '__all__'
        read_only_fields = ('business',)

class PayrollPaymentSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = PayrollPayment
        fields = '__all__'
        read_only_fields = ('business', 'created_at', 'transaction')

class FixedExpenseSerializer(serializers.ModelSerializer):
    current_period_status = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    
    class Meta:
        model = FixedExpense
        fields = '__all__'
        read_only_fields = ('business', 'created_at', 'updated_at')
    
    def get_current_period_status(self, obj):
        """Get status of current month's period"""
        from datetime import date
        current_period = date.today().replace(day=1)
        period = obj.periods.filter(period=current_period).first()
        if period:
            return {
                'status': period.status,
                'amount': str(period.amount),
                'paid_at': period.paid_at,
                'id': period.id
            }
        return {'status': 'not_created'}

class FixedExpensePeriodSerializer(serializers.ModelSerializer):
    fixed_expense_name = serializers.CharField(source='fixed_expense.name', read_only=True)
    paid_account_name = serializers.CharField(source='paid_account.name', read_only=True, allow_null=True)
    period_display = serializers.SerializerMethodField()
    
    class Meta:
        model = FixedExpensePeriod
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'paid_at', 'paid_account', 'payment_transaction', 'status')
    
    def get_period_display(self, obj):
        """Return period in YYYY-MM format"""
        return obj.period.strftime('%Y-%m')


class TreasurySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreasurySettings
        fields = '__all__'
        read_only_fields = ('business',)


class BudgetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    spent = serializers.SerializerMethodField()
    percentage = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = '__all__'
        read_only_fields = ('business', 'created_at', 'updated_at')

    def get_spent(self, obj):
        """Calculate amount spent in this category for the budget month."""
        from django.db.models import Sum
        from datetime import date
        month_start = date(obj.year, obj.month, 1)
        from calendar import monthrange
        last_day = monthrange(obj.year, obj.month)[1]
        month_end = date(obj.year, obj.month, last_day)
        result = Transaction.objects.filter(
            business=obj.business,
            category=obj.category,
            direction=Transaction.Direction.OUT,
            status=Transaction.Status.POSTED,
            occurred_at__date__gte=month_start,
            occurred_at__date__lte=month_end,
        ).aggregate(total=Sum('amount'))['total'] or 0
        return float(result)

    def get_percentage(self, obj):
        spent = self.get_spent(obj)
        if not obj.limit_amount or obj.limit_amount == 0:
            return None
        return round((spent / float(obj.limit_amount)) * 100, 1)

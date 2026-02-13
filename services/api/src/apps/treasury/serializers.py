from rest_framework import serializers
from django.db import models as db_models
from .models import Account, TransactionCategory, Transaction, ExpenseTemplate, Expense, Employee, PayrollPayment, FixedExpense, FixedExpensePeriod
from apps.business.models import Business

class AccountSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = '__all__'
        read_only_fields = ('business', 'created_at', 'updated_at')

    def get_balance(self, obj):
        in_total = obj.transactions.filter(direction=Transaction.Direction.IN).aggregate(s=db_models.Sum('amount'))['s'] or 0
        out_total = obj.transactions.filter(direction=Transaction.Direction.OUT).aggregate(s=db_models.Sum('amount'))['s'] or 0
        return obj.opening_balance + in_total - out_total

class TransactionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionCategory
        fields = '__all__'
        read_only_fields = ('business',)

class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    # Handle user name safely if user is null
    created_by_name = serializers.SerializerMethodField()
    transaction_type = serializers.SerializerMethodField()
    reference_details = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = '__all__'
        read_only_fields = ('business', 'created_at', 'created_by', 'transfer_group_id', 'status')

    def get_created_by_name(self, obj):
        if obj.created_by:
            # Assuming user model has get_full_name or similar, or just return username/email
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
        return 'other'
    
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
                period = FixedExpensePeriod.objects.filter(id=obj.reference_id).first()
                if period:
                    return {
                        'name': period.fixed_expense.name,
                        'period': period.period.strftime('%Y-%m'),
                        'due_date': period.due_date.isoformat() if period.due_date else None
                    }
            elif obj.reference_type == 'payroll':
                payment = PayrollPayment.objects.filter(id=obj.reference_id).first()
                if payment:
                    return {'employee_name': payment.employee.full_name}
        except:
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

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = ('business', 'created_at', 'paid_at', 'paid_account', 'payment_transaction')

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

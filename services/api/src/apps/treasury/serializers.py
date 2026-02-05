from rest_framework import serializers
from django.db import models as db_models
from .models import Account, TransactionCategory, Transaction, ExpenseTemplate, Expense, Employee, PayrollPayment
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

    class Meta:
        model = Transaction
        fields = '__all__'
        read_only_fields = ('business', 'created_at', 'created_by', 'transfer_group_id', 'status')

    def get_created_by_name(self, obj):
        if obj.created_by:
            # Assuming user model has get_full_name or similar, or just return username/email
             return getattr(obj.created_by, 'get_full_name', lambda: str(obj.created_by))()
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

from rest_framework import serializers
from django.db import models as db_models
from .models import (
    Account, TransactionCategory, Transaction, ExpenseTemplate, Expense,
    Employee, PayrollPayment, FixedExpense, FixedExpensePeriod,
    TreasurySettings, Budget, Payment, ExpenseDocument,
    EXPENSE_DOCUMENT_ALLOWED_TYPES, EXPENSE_DOCUMENT_MAX_SIZE_BYTES,
)
from .file_validation import validate_expense_document_file
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
    template_name = serializers.CharField(source='template.name', read_only=True)  # DEPRECATED — transitional
    category_name = serializers.CharField(source='category.name', read_only=True)
    # Legacy fields kept for frontend compat — computed from Payment when available
    paid_account_name = serializers.CharField(source='paid_account.name', read_only=True, allow_null=True)
    source_details = serializers.SerializerMethodField()
    # Sprint 1: expose payment_id for new frontend paths
    payment_id = serializers.SerializerMethodField()
    # Sprint 2: document layer
    documents_count = serializers.SerializerMethodField()
    latest_document = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = (
            'business', 'created_at', 'paid_at', 'paid_account',
            'payment_transaction', 'source_type', 'source_id', 'is_auto_generated',
        )

    def get_payment_id(self, obj):
        """Return the active Payment ID — uses annotation if available."""
        if hasattr(obj, '_payment_id'):
            return obj._payment_id
        payment = obj.payments.filter(status='completed').first() if hasattr(obj, 'payments') else None
        return payment.id if payment else None

    def get_documents_count(self, obj):
        if hasattr(obj, '_documents_count'):
            return obj._documents_count
        return obj.documents.exclude(status='archived').count()

    def get_latest_document(self, obj):
        if hasattr(obj, '_latest_doc_id'):
            if obj._latest_doc_id is None:
                return None
            return {
                'id': obj._latest_doc_id,
                'original_filename': obj._latest_doc_filename,
                'mime_type': obj._latest_doc_mime,
                'document_kind': obj._latest_doc_kind,
                'created_at': obj._latest_doc_created.isoformat() if obj._latest_doc_created else None,
            }
        doc = obj.documents.exclude(status='archived').order_by('-created_at').first()
        if not doc:
            return None
        return {
            'id': doc.id,
            'original_filename': doc.original_filename,
            'mime_type': doc.mime_type,
            'document_kind': doc.document_kind,
            'created_at': doc.created_at.isoformat(),
        }

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
    # Legacy fields kept for frontend compat
    paid_account_name = serializers.CharField(source='paid_account.name', read_only=True, allow_null=True)
    period_display = serializers.SerializerMethodField()
    # Sprint 1: expose payment_id for new frontend paths
    payment_id = serializers.SerializerMethodField()
    # Sprint 2: document layer
    documents_count = serializers.SerializerMethodField()
    latest_document = serializers.SerializerMethodField()
    
    class Meta:
        model = FixedExpensePeriod
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'paid_at', 'paid_account', 'payment_transaction', 'status')
    
    def get_period_display(self, obj):
        """Return period in YYYY-MM format"""
        return obj.period.strftime('%Y-%m')

    def get_payment_id(self, obj):
        """Return the active Payment ID — uses annotation if available."""
        if hasattr(obj, '_payment_id'):
            return obj._payment_id
        payment = obj.payments.filter(status='completed').first() if hasattr(obj, 'payments') else None
        return payment.id if payment else None

    def get_documents_count(self, obj):
        if hasattr(obj, '_documents_count'):
            return obj._documents_count
        return obj.documents.exclude(status='archived').count()

    def get_latest_document(self, obj):
        if hasattr(obj, '_latest_doc_id'):
            if obj._latest_doc_id is None:
                return None
            return {
                'id': obj._latest_doc_id,
                'original_filename': obj._latest_doc_filename,
                'mime_type': obj._latest_doc_mime,
                'document_kind': obj._latest_doc_kind,
                'created_at': obj._latest_doc_created.isoformat() if obj._latest_doc_created else None,
            }
        doc = obj.documents.exclude(status='archived').order_by('-created_at').first()
        if not doc:
            return None
        return {
            'id': doc.id,
            'original_filename': doc.original_filename,
            'mime_type': doc.mime_type,
            'document_kind': doc.document_kind,
            'created_at': doc.created_at.isoformat(),
        }


class TreasurySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TreasurySettings
        fields = '__all__'
        read_only_fields = ('business',)


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for the Payment entity (Sprint 1)."""
    expense_name = serializers.SerializerMethodField()
    fixed_expense_period_label = serializers.SerializerMethodField()
    account_name = serializers.CharField(source='account.name', read_only=True, allow_null=True)
    transaction_id = serializers.IntegerField(source='transaction.id', read_only=True, allow_null=True)

    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = (
            'business', 'created_at', 'updated_at', 'is_backfilled',
        )

    def get_expense_name(self, obj):
        if obj.expense_id and obj.expense:
            return obj.expense.name
        return None

    def get_fixed_expense_period_label(self, obj):
        if obj.fixed_expense_period_id and obj.fixed_expense_period:
            fep = obj.fixed_expense_period
            return f'{fep.fixed_expense.name} — {fep.period.strftime("%Y-%m")}'
        return None


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


# ─────────────────────────────────────────────────────────────────────────────
# ExpenseDocument — capa documental (Sprint 2)
# ─────────────────────────────────────────────────────────────────────────────

class ExpenseDocumentSerializer(serializers.ModelSerializer):
    """Serializer for expense documents / receipts (detail view)."""
    file_url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.SerializerMethodField()
    origin_type = serializers.SerializerMethodField()
    origin_label = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseDocument
        fields = (
            'id', 'business', 'expense', 'fixed_expense_period',
            'file', 'file_url', 'original_filename', 'mime_type', 'size_bytes',
            'document_kind', 'status', 'notes', 'uploaded_by', 'uploaded_by_name',
            'origin_type', 'origin_label',
            # Processing fields (Sprint 3) — included in detail, excluded in list
            'normalized_data', 'processing_errors',
            'processed_at', 'extraction_source',
            'created_at', 'updated_at',
        )
        read_only_fields = (
            'business', 'expense', 'fixed_expense_period',
            'original_filename', 'mime_type', 'size_bytes',
            'file', 'uploaded_by', 'created_at', 'updated_at',
            # Processing fields (Sprint 3) — set by pipeline only
            'normalized_data', 'processing_errors',
            'processed_at', 'extraction_source',
        )

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return getattr(obj.uploaded_by, 'get_full_name', lambda: str(obj.uploaded_by))()
        return None

    def get_origin_type(self, obj):
        if obj.expense_id:
            return 'expense'
        if obj.fixed_expense_period_id:
            return 'fixed_expense_period'
        return None

    def get_origin_label(self, obj):
        if obj.expense_id and obj.expense:
            return obj.expense.name
        if obj.fixed_expense_period_id and obj.fixed_expense_period:
            fep = obj.fixed_expense_period
            return f'{fep.fixed_expense.name} — {fep.period.strftime("%Y-%m")}'
        return None


class ExpenseDocumentListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — excludes raw_extraction & normalized_data."""
    file_url = serializers.SerializerMethodField()
    origin_type = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseDocument
        fields = (
            'id', 'expense', 'fixed_expense_period',
            'file_url', 'original_filename', 'mime_type', 'size_bytes',
            'document_kind', 'status', 'extraction_source',
            'processed_at', 'created_at',
            'origin_type',
        )

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None

    def get_origin_type(self, obj):
        if obj.expense_id:
            return 'expense'
        if obj.fixed_expense_period_id:
            return 'fixed_expense_period'
        return None


class ExpenseDocumentUploadSerializer(serializers.Serializer):
    """Minimal serializer for the upload action (multipart form)."""
    file = serializers.FileField()
    expense = serializers.PrimaryKeyRelatedField(
        queryset=Expense.objects.none(), required=False, allow_null=True,
    )
    fixed_expense_period = serializers.PrimaryKeyRelatedField(
        queryset=FixedExpensePeriod.objects.none(), required=False, allow_null=True,
    )
    document_kind = serializers.ChoiceField(
        choices=ExpenseDocument.DocumentKind.choices,
        default=ExpenseDocument.DocumentKind.OTHER,
    )
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        business = getattr(request, 'business', None) if request else None
        if business:
            self.fields['expense'].queryset = Expense.objects.filter(business=business)
            self.fields['fixed_expense_period'].queryset = (
                FixedExpensePeriod.objects.filter(fixed_expense__business=business)
            )

    def validate_file(self, value):
        return validate_expense_document_file(value)

    def validate(self, attrs):
        expense = attrs.get('expense')
        fep = attrs.get('fixed_expense_period')
        has_expense = expense is not None
        has_fep = fep is not None
        if has_expense == has_fep:
            raise serializers.ValidationError(
                'Debe especificar exactamente un origen: expense o fixed_expense_period.'
            )
        return attrs

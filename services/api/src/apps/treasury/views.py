import csv
import uuid
import logging
from decimal import Decimal
from datetime import date, timedelta
from calendar import monthrange

from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from django.db import transaction
from django.db.models import Sum, Q
from django.http import StreamingHttpResponse
from django.utils import timezone

from apps.accounts.permissions import HasBusinessMembership, HasPermission, HasEntitlement
from .models import (
    Account, TransactionCategory, Transaction, ExpenseTemplate,
    Expense, Employee, PayrollPayment, FixedExpense, FixedExpensePeriod,
    TreasurySettings, Budget
)
from .serializers import (
    AccountSerializer, TransactionCategorySerializer, TransactionSerializer,
    ExpenseTemplateSerializer, ExpenseSerializer, EmployeeSerializer, PayrollPaymentSerializer,
    FixedExpenseSerializer, FixedExpensePeriodSerializer,
    TreasurySettingsSerializer, BudgetSerializer
)

logger = logging.getLogger(__name__)


class TreasuryPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200

class BaseTreasuryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
    required_entitlement = 'gestion.treasury'
    required_permission = 'view_finance' 
    
    permission_map = {
        'GET': 'view_finance',
        'POST': 'manage_finance',
        'PUT': 'manage_finance',
        'PATCH': 'manage_finance',
        'DELETE': 'manage_finance',
    }

    def get_queryset(self):
        business = getattr(self.request, 'business', None)
        if hasattr(self.queryset.model, 'business'):
            return self.queryset.filter(business=business)
        return self.queryset

    def perform_create(self, serializer):
        business = getattr(self.request, 'business', None)
        serializer.save(business=business)

class AccountViewSet(BaseTreasuryViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission], url_path='reconcile')
    def reconcile(self, request, pk=None):
        self.required_entitlement = 'gestion.treasury'
        self.required_permission = 'manage_finance' 
        
        account = self.get_object()
        real_balance = request.data.get('real_balance')
        occurred_at = request.data.get('occurred_at', timezone.now())

        if real_balance is None:
            return Response({'error': 'real_balance is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
             real_balance = Decimal(str(real_balance))
        except:
             return Response({'error': 'Invalid real_balance'}, status=status.HTTP_400_BAD_REQUEST)
        
        transactions = Transaction.objects.filter(account=account, status=Transaction.Status.POSTED)
        
        in_total = transactions.filter(direction=Transaction.Direction.IN).aggregate(s=Sum('amount'))['s'] or 0
        out_total = transactions.filter(direction=Transaction.Direction.OUT).aggregate(s=Sum('amount'))['s'] or 0
        
        # NOTE: Ignoring ADJUST direction for calculation as decided, using IN/OUT for reconciliation entries
        current_balance = account.opening_balance + in_total - out_total
        
        diff = real_balance - current_balance
        
        if diff == 0:
            return Response({'message': 'Balances match', 'balance': current_balance})
        
        direction = Transaction.Direction.IN if diff > 0 else Transaction.Direction.OUT
        abs_diff = abs(diff)
        
        Transaction.objects.create(
            business=account.business,
            account=account,
            direction=direction,
            amount=abs_diff,
            occurred_at=occurred_at,
            description="Conciliación de saldo",
            reference_type='reconciliation',
            created_by=request.user,
            status=Transaction.Status.POSTED
        )
        
        return Response({'message': 'Reconciled', 'diff': diff, 'new_balance': real_balance})

class TransactionCategoryViewSet(BaseTreasuryViewSet):
    queryset = TransactionCategory.objects.all()
    serializer_class = TransactionCategorySerializer

class TransactionViewSet(BaseTreasuryViewSet):
    queryset = Transaction.objects.all().select_related('account', 'category', 'created_by')
    serializer_class = TransactionSerializer
    pagination_class = TreasuryPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['description', 'reference_type', 'reference_id']

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        account_id = params.get('account')
        if account_id:
            qs = qs.filter(account_id=account_id)

        direction = params.get('direction')
        if direction:
            qs = qs.filter(direction=direction)

        category_id = params.get('category')
        if category_id:
            qs = qs.filter(category_id=category_id)

        date_from = params.get('date_from')
        if date_from:
            qs = qs.filter(occurred_at__date__gte=date_from)

        date_to = params.get('date_to')
        if date_to:
            qs = qs.filter(occurred_at__date__lte=date_to)

        txn_status = params.get('status')
        if txn_status:
            qs = qs.filter(status=txn_status)

        return qs.order_by('-occurred_at')

    def perform_create(self, serializer):
        serializer.save(business=self.request.business, created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """Anular una transacción. Revierte gastos/sueldos asociados si aplica."""
        self.required_permission = 'manage_finance'

        txn = self.get_object()
        if txn.status == Transaction.Status.VOIDED:
            return Response({'error': 'La transacción ya está anulada'}, status=status.HTTP_400_BAD_REQUEST)

        void_reason = request.data.get('reason', '').strip()

        with transaction.atomic():
            txn.status = Transaction.Status.VOIDED
            if void_reason:
                suffix = f' [ANULADO: {void_reason}]'
                txn.description = (txn.description or '') + suffix
            txn.save(update_fields=['status', 'description'])

            # Revert linked expense
            if txn.reference_type == 'expense' and txn.reference_id:
                expense = Expense.objects.filter(id=txn.reference_id).first()
                if expense and expense.status == Expense.Status.PAID:
                    expense.status = Expense.Status.PENDING
                    expense.paid_at = None
                    expense.paid_account = None
                    expense.payment_transaction = None
                    expense.save(update_fields=['status', 'paid_at', 'paid_account', 'payment_transaction'])

            # Revert linked fixed expense period
            if txn.reference_type == 'fixed_expense_period' and txn.reference_id:
                period = FixedExpensePeriod.objects.filter(id=txn.reference_id).first()
                if period and period.status == FixedExpensePeriod.Status.PAID:
                    period.status = FixedExpensePeriod.Status.PENDING
                    period.paid_at = None
                    period.paid_account = None
                    period.payment_transaction = None
                    period.save(update_fields=['status', 'paid_at', 'paid_account', 'payment_transaction'])

            # Detach linked payroll payment
            if txn.reference_type == 'payroll' and txn.reference_id:
                payment = PayrollPayment.objects.filter(id=txn.reference_id).first()
                if payment:
                    payment.transaction = None
                    payment.save(update_fields=['transaction'])

        return Response(TransactionSerializer(txn).data)

    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        """Export current filtered transactions as CSV."""
        qs = self.get_queryset().select_related('account', 'category', 'created_by')

        def rows():
            yield ','.join(['ID', 'Fecha', 'Dirección', 'Cuenta', 'Categoría', 'Descripción', 'Monto', 'Estado', 'Tipo', 'Creado por']) + '\n'
            for t in qs.iterator(chunk_size=500):
                row = [
                    str(t.id),
                    t.occurred_at.strftime('%Y-%m-%d %H:%M'),
                    t.direction,
                    t.account.name,
                    t.category.name if t.category else '',
                    (t.description or '').replace(',', ';'),
                    str(t.amount),
                    t.status,
                    t.reference_type or '',
                    str(t.created_by) if t.created_by else '',
                ]
                yield ','.join(row) + '\n'

        response = StreamingHttpResponse(rows(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="movimientos.csv"'
        return response

    @action(detail=False, methods=['get'], url_path='monthly-report')
    def monthly_report(self, request):
        """Monthly cashflow report: last 12 months IN/OUT/result per month."""
        business = getattr(request, 'business', None)
        today = date.today()
        results = []

        for i in range(11, -1, -1):
            # Go back i months from current month
            year = today.year
            month = today.month - i
            while month <= 0:
                month += 12
                year -= 1

            month_start = date(year, month, 1)
            last_day = monthrange(year, month)[1]
            month_end = date(year, month, last_day)

            qs = Transaction.objects.filter(
                business=business,
                status=Transaction.Status.POSTED,
                occurred_at__date__gte=month_start,
                occurred_at__date__lte=month_end,
            )
            income = qs.filter(direction=Transaction.Direction.IN).aggregate(s=Sum('amount'))['s'] or 0
            expense = qs.filter(direction=Transaction.Direction.OUT).aggregate(s=Sum('amount'))['s'] or 0

            results.append({
                'year': year,
                'month': month,
                'label': month_start.strftime('%b %Y'),
                'income': float(income),
                'expense': float(expense),
                'result': float(income) - float(expense),
            })

        return Response(results)

    @action(detail=False, methods=['post'], url_path='transfer')
    def transfer(self, request):
        self.required_permission = 'manage_finance'

        from_account_id = request.data.get('from_account')
        to_account_id = request.data.get('to_account')
        amount = request.data.get('amount')
        occurred_at = request.data.get('occurred_at', timezone.now())
        description = request.data.get('description', 'Transferencia interna')

        if not (from_account_id and to_account_id and amount):
            return Response({'error': 'Faltan campos requeridos'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(amount))
        except Exception:
            return Response({'error': 'Monto inválido'}, status=status.HTTP_400_BAD_REQUEST)

        if str(from_account_id) == str(to_account_id):
            return Response({'error': 'Las cuentas de origen y destino deben ser diferentes'}, status=status.HTTP_400_BAD_REQUEST)

        business = getattr(request, 'business', None)

        try:
            from_account = Account.objects.get(id=from_account_id, business=business)
            to_account = Account.objects.get(id=to_account_id, business=business)
        except Account.DoesNotExist:
            return Response({'error': 'Cuenta inválida'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            group_id = uuid.uuid4()

            out_txn = Transaction.objects.create(
                business=business,
                account=from_account,
                direction=Transaction.Direction.OUT,
                amount=amount,
                occurred_at=occurred_at,
                description=f"{description} → {to_account.name}",
                transfer_group_id=group_id,
                created_by=request.user
            )

            in_txn = Transaction.objects.create(
                business=business,
                account=to_account,
                direction=Transaction.Direction.IN,
                amount=amount,
                occurred_at=occurred_at,
                description=f"{description} ← {from_account.name}",
                transfer_group_id=group_id,
                created_by=request.user
            )

        return Response({
            'message': 'Transferencia exitosa',
            'transfer_group_id': str(group_id),
            'out': TransactionSerializer(out_txn).data,
            'in': TransactionSerializer(in_txn).data,
        })

class ExpenseTemplateViewSet(BaseTreasuryViewSet):
    queryset = ExpenseTemplate.objects.all()
    serializer_class = ExpenseTemplateSerializer

    @action(detail=False, methods=['post'], url_path='generate-month')
    def generate_for_month(self, request):
        # MVP Placeholder: logic to checking and creating pending expenses
        # Not implementing full logic as it requires complex date math and checking existing
        return Response({'message': 'Not implemented in MVP'}, status=status.HTTP_501_NOT_IMPLEMENTED)

class ExpenseViewSet(BaseTreasuryViewSet):
    queryset = Expense.objects.all().select_related('category', 'paid_account', 'payment_transaction')
    serializer_class = ExpenseSerializer
    pagination_class = TreasuryPagination

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        exp_status = params.get('status')
        if exp_status:
            qs = qs.filter(status=exp_status)

        category_id = params.get('category')
        if category_id:
            qs = qs.filter(category_id=category_id)

        date_from = params.get('date_from')
        if date_from:
            qs = qs.filter(due_date__gte=date_from)

        date_to = params.get('date_to')
        if date_to:
            qs = qs.filter(due_date__lte=date_to)

        # Filter by auto-generation source type (e.g. ?source_type=stock_replenishment)
        source_type = params.get('source_type')
        if source_type:
            qs = qs.filter(source_type=source_type)

        # ?is_auto_generated=true|false
        is_auto = params.get('is_auto_generated')
        if is_auto is not None:
            qs = qs.filter(is_auto_generated=is_auto.lower() == 'true')

        return qs.order_by('-due_date')

    def perform_create(self, serializer):
        amount = serializer.validated_data.get('amount')
        if amount and amount <= 0:
            raise serializers.ValidationError({'amount': 'El monto debe ser mayor que cero'})
        super().perform_create(serializer)

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        self.required_permission = 'manage_finance'

        expense = self.get_object()

        # Auto-generated expenses are already "paid" via the linked financial movement.
        # Prevent creating a duplicate transaction.
        if expense.is_auto_generated:
            return Response(
                {'error': 'Este gasto fue generado automáticamente y ya se encuentra vinculado a su movimiento financiero. No se puede pagar manualmente.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Idempotency check
        if expense.status == Expense.Status.PAID:
             return Response({'error': 'Expense already paid'}, status=status.HTTP_400_BAD_REQUEST)

        account_id = request.data.get('account_id')
        if not account_id:
            return Response({'error': 'Account required'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate account exists and belongs to same business
        try:
            account = Account.objects.get(id=account_id, business=expense.business)
        except Account.DoesNotExist:
            return Response({'error': 'Invalid account'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            trx = Transaction.objects.create(
                business=expense.business,
                account=account,
                direction=Transaction.Direction.OUT,
                amount=expense.amount,
                occurred_at=timezone.now(),
                category=expense.category,
                description=f"Pago gasto: {expense.name}",
                reference_type='expense',
                reference_id=str(expense.id),
                created_by=request.user
            )
            
            expense.status = Expense.Status.PAID
            expense.paid_at = timezone.now()
            expense.paid_account = account
            expense.payment_transaction = trx
            expense.save()
            
        return Response(ExpenseSerializer(expense).data)

class EmployeeViewSet(BaseTreasuryViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer

    def perform_destroy(self, instance):
        """Don't delete employees with payments — just deactivate."""
        if instance.payments.exists():
            instance.is_active = False
            instance.save(update_fields=['is_active'])
        else:
            instance.delete()


class PayrollPaymentViewSet(BaseTreasuryViewSet):
    queryset = PayrollPayment.objects.all().select_related('employee', 'account', 'transaction')
    serializer_class = PayrollPaymentSerializer
    pagination_class = TreasuryPagination

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        employee_id = params.get('employee')
        if employee_id:
            qs = qs.filter(employee_id=employee_id)

        date_from = params.get('date_from')
        if date_from:
            qs = qs.filter(paid_at__date__gte=date_from)

        date_to = params.get('date_to')
        if date_to:
            qs = qs.filter(paid_at__date__lte=date_to)

        return qs.order_by('-paid_at')

    def perform_create(self, serializer):
        amount = serializer.validated_data.get('amount')
        if amount and amount <= 0:
            raise serializers.ValidationError({'amount': 'El monto debe ser mayor que cero'})

        account = serializer.validated_data.get('account')
        if account and account.business != self.request.business:
            raise serializers.ValidationError({'account': 'Cuenta inválida'})

        employee = serializer.validated_data.get('employee')
        if employee and employee.business != self.request.business:
            raise serializers.ValidationError({'employee': 'Empleado inválido'})

        with transaction.atomic():
            payment = serializer.save(business=self.request.business)

            trx = Transaction.objects.create(
                business=payment.business,
                account=payment.account,
                direction=Transaction.Direction.OUT,
                amount=payment.amount,
                occurred_at=payment.paid_at,
                description=f"Pago sueldo: {payment.employee.full_name}",
                reference_type='payroll',
                reference_id=str(payment.id),
                created_by=self.request.user
            )
            payment.transaction = trx
            payment.save(update_fields=['transaction'])

    @action(detail=True, methods=['post'])
    def revert(self, request, pk=None):
        """Revertir un pago de sueldo: anula la transacción OUT asociada."""
        self.required_permission = 'manage_finance'

        payment = self.get_object()
        reason = request.data.get('reason', '').strip()

        with transaction.atomic():
            if payment.transaction and payment.transaction.status == Transaction.Status.POSTED:
                txn = payment.transaction
                txn.status = Transaction.Status.VOIDED
                suffix = f' [REVERTIDO: {reason}]' if reason else ' [REVERTIDO]'
                txn.description = (txn.description or '') + suffix
                txn.save(update_fields=['status', 'description'])

            # Detach transaction and mark payment reverted
            payment.transaction = None
            payment.status = 'reverted'
            payment.save(update_fields=['transaction', 'status'])

        return Response(PayrollPaymentSerializer(payment).data)

class FixedExpenseViewSet(BaseTreasuryViewSet):
    queryset = FixedExpense.objects.all()
    serializer_class = FixedExpenseSerializer
    
    def perform_create(self, serializer):
        """Create fixed expense and optionally generate current period"""
        fixed_expense = serializer.save(business=self.request.business)
        
        # Auto-create current period
        self._ensure_current_period(fixed_expense)
    
    def _ensure_current_period(self, fixed_expense):
        """Ensure current month period exists"""
        current_period_date = date.today().replace(day=1)
        
        period, created = FixedExpensePeriod.objects.get_or_create(
            fixed_expense=fixed_expense,
            period=current_period_date,
            defaults={
                'amount': fixed_expense.default_amount or Decimal('0'),
                'status': FixedExpensePeriod.Status.PENDING
            }
        )
        return period, created
    
    @action(detail=True, methods=['get'])
    def periods(self, request, pk=None):
        """Get all periods for this fixed expense"""
        fixed_expense = self.get_object()
        
        # Ensure current period exists
        self._ensure_current_period(fixed_expense)
        
        # Get periods with optional filtering
        periods = fixed_expense.periods.all()
        
        # Filter by date range if provided
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')
        
        if from_date:
            periods = periods.filter(period__gte=from_date)
        if to_date:
            periods = periods.filter(period__lte=to_date)
        
        serializer = FixedExpensePeriodSerializer(periods, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def ensure_current(self, request, pk=None):
        """Ensure current month period exists (returns it)"""
        fixed_expense = self.get_object()
        period, created = self._ensure_current_period(fixed_expense)

        return Response({
            'created': created,
            'period': FixedExpensePeriodSerializer(period).data
        })

    @action(detail=False, methods=['post'], url_path='ensure-all-current')
    def ensure_all_current(self, request):
        """Ensure current month period exists for ALL active fixed expenses of this business."""
        business = getattr(request, 'business', None)
        fixed_expenses = FixedExpense.objects.filter(business=business, is_active=True)
        created_count = 0
        for fe in fixed_expenses:
            _, was_created = self._ensure_current_period(fe)
            if was_created:
                created_count += 1
        return Response({'message': f'{created_count} periodos creados', 'total': fixed_expenses.count()})

    @action(detail=True, methods=['post'], url_path='generate-periods')
    def generate_periods(self, request, pk=None):
        """Generate the next N periods for this fixed expense (idempotent)."""
        fixed_expense = self.get_object()
        n = int(request.data.get('n', 3))
        if n < 1 or n > 12:
            return Response({'error': 'n must be between 1 and 12'}, status=status.HTTP_400_BAD_REQUEST)

        today = date.today()
        created_periods = []

        for i in range(n):
            year = today.year
            month = today.month + i
            while month > 12:
                month -= 12
                year += 1
            period_date = date(year, month, 1)

            period, created = FixedExpensePeriod.objects.get_or_create(
                fixed_expense=fixed_expense,
                period=period_date,
                defaults={
                    'amount': fixed_expense.default_amount or Decimal('0'),
                    'status': FixedExpensePeriod.Status.PENDING,
                }
            )
            if created:
                created_periods.append(period_date.strftime('%Y-%m'))

        return Response({'created': created_periods, 'total_requested': n})

class FixedExpensePeriodViewSet(BaseTreasuryViewSet):
    queryset = FixedExpensePeriod.objects.all()
    serializer_class = FixedExpensePeriodSerializer
    
    def get_queryset(self):
        """Filter periods by business through fixed_expense"""
        business = getattr(self.request, 'business', None)
        return self.queryset.filter(fixed_expense__business=business)
    
    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        """Pay a fixed expense period"""
        self.required_permission = 'manage_finance'
        
        period = self.get_object()
        
        # Idempotency check
        if period.status == FixedExpensePeriod.Status.PAID:
            return Response({'error': 'Period already paid'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get payment details
        account_id = request.data.get('account_id')
        if not account_id:
            return Response({'error': 'Account required'}, status=status.HTTP_400_BAD_REQUEST)
        
        paid_at = request.data.get('paid_at')
        if paid_at:
            from dateutil import parser
            paid_at = parser.parse(paid_at)
        else:
            paid_at = timezone.now()
        
        # Optional amount override
        amount = request.data.get('amount')
        if amount:
            amount = Decimal(str(amount))
            if amount <= 0:
                return Response({'error': 'Amount must be greater than zero'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            amount = period.amount
        
        # Validate account
        try:
            account = Account.objects.get(id=account_id, business=period.fixed_expense.business)
        except Account.DoesNotExist:
            return Response({'error': 'Invalid account'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create transaction and update period
        with transaction.atomic():
            trx = Transaction.objects.create(
                business=period.fixed_expense.business,
                account=account,
                direction=Transaction.Direction.OUT,
                amount=amount,
                occurred_at=paid_at,
                description=f"Pago {period.fixed_expense.name} - {period.period.strftime('%B %Y')}",
                reference_type='fixed_expense_period',
                reference_id=str(period.id),
                created_by=request.user
            )
            
            period.status = FixedExpensePeriod.Status.PAID
            period.paid_at = paid_at
            period.paid_account = account
            period.payment_transaction = trx
            period.amount = amount  # Update with actual paid amount
            period.save()
        
        return Response(FixedExpensePeriodSerializer(period).data)

    @action(detail=True, methods=['post'], url_path='skip')
    def skip(self, request, pk=None):
        """Mark a period as skipped."""
        self.required_permission = 'manage_finance'

        period = self.get_object()
        if period.status == FixedExpensePeriod.Status.PAID:
            return Response({'error': 'No se puede omitir un periodo ya pagado'}, status=status.HTTP_400_BAD_REQUEST)

        period.status = FixedExpensePeriod.Status.SKIPPED
        period.notes = request.data.get('notes', period.notes)
        period.save(update_fields=['status', 'notes', 'updated_at'])
        return Response(FixedExpensePeriodSerializer(period).data)


class TreasurySettingsViewSet(BaseTreasuryViewSet):
    queryset = TreasurySettings.objects.all()
    serializer_class = TreasurySettingsSerializer

    def get_queryset(self):
        business = getattr(self.request, 'business', None)
        return TreasurySettings.objects.filter(business=business)

    def list(self, request, *args, **kwargs):
        """Return (or auto-create) the single TreasurySettings for this business."""
        business = getattr(request, 'business', None)
        settings_obj, _ = TreasurySettings.objects.get_or_create(business=business)
        serializer = self.get_serializer(settings_obj)
        return Response(serializer.data)

    def perform_create(self, serializer):
        business = getattr(self.request, 'business', None)
        # Ensure only one settings per business
        existing = TreasurySettings.objects.filter(business=business).first()
        if existing:
            existing.__dict__.update(serializer.validated_data)
            existing.save()
        else:
            serializer.save(business=business)

    @action(detail=False, methods=['patch', 'put'], url_path='update')
    def update_settings(self, request):
        """Update the treasury settings for this business."""
        self.required_permission = 'manage_finance'
        business = getattr(request, 'business', None)
        settings_obj, _ = TreasurySettings.objects.get_or_create(business=business)
        serializer = self.get_serializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class BudgetViewSet(BaseTreasuryViewSet):
    queryset = Budget.objects.all().select_related('category')
    serializer_class = BudgetSerializer

    def get_queryset(self):
        business = getattr(self.request, 'business', None)
        qs = Budget.objects.filter(business=business).select_related('category')

        year = self.request.query_params.get('year')
        if year:
            qs = qs.filter(year=year)

        month = self.request.query_params.get('month')
        if month:
            qs = qs.filter(month=month)

        return qs

    def perform_create(self, serializer):
        business = getattr(self.request, 'business', None)
        serializer.save(business=business)

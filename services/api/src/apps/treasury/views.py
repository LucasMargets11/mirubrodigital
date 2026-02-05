from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import HasBusinessMembership, HasPermission
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import Account, TransactionCategory, Transaction, ExpenseTemplate, Expense, Employee, PayrollPayment
from .serializers import (
    AccountSerializer, TransactionCategorySerializer, TransactionSerializer,
    ExpenseTemplateSerializer, ExpenseSerializer, EmployeeSerializer, PayrollPaymentSerializer
)
import uuid
from decimal import Decimal

class BaseTreasuryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]
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

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, HasBusinessMembership, HasPermission], url_path='reconcile')
    def reconcile(self, request, pk=None):
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
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['description', 'reference_type', 'reference_id']

    def get_queryset(self):
        qs = super().get_queryset()
        # Filters
        account_id = self.request.query_params.get('account')
        if account_id:
            qs = qs.filter(account_id=account_id)
        
        direction = self.request.query_params.get('direction')
        if direction:
            qs = qs.filter(direction=direction)
            
        category_id = self.request.query_params.get('category')
        if category_id:
            qs = qs.filter(category_id=category_id)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(occurred_at__gte=date_from)
            
        date_to = self.request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(occurred_at__lte=date_to)
            
        return qs.order_by('-occurred_at')

    def perform_create(self, serializer):
        serializer.save(business=self.request.business, created_by=self.request.user)

    @action(detail=False, methods=['post'], url_path='transfer')
    def transfer(self, request):
        self.required_permission = 'manage_finance' 

        from_account_id = request.data.get('from_account')
        to_account_id = request.data.get('to_account')
        amount = request.data.get('amount')
        date = request.data.get('occurred_at', timezone.now())
        description = request.data.get('description', 'Transferencia')

        if not (from_account_id and to_account_id and amount):
            return Response({'error': 'Missing fields'}, status=status.HTTP_400_BAD_REQUEST)

        try:
             amount = Decimal(str(amount))
        except:
             return Response({'error': 'Invalid amount'}, status=status.HTTP_400_BAD_REQUEST)
             
        if from_account_id == to_account_id:
            return Response({'error': 'Cannot transfer to same account'}, status=status.HTTP_400_BAD_REQUEST)
        
        business = getattr(request, 'business', None)

        with transaction.atomic():
            group_id = uuid.uuid4()
            
            # Helper to get names for description could be nice but skipping for MVP
            
            # OUT
            Transaction.objects.create(
                business=business,
                account_id=from_account_id,
                direction=Transaction.Direction.OUT,
                amount=amount,
                occurred_at=date,
                description=f"{description} (Destino: {to_account_id})", 
                transfer_group_id=group_id,
                created_by=request.user
            )
            
            # IN
            Transaction.objects.create(
                business=business,
                account_id=to_account_id,
                direction=Transaction.Direction.IN,
                amount=amount,
                occurred_at=date,
                description=f"{description} (Origen: {from_account_id})",
                transfer_group_id=group_id,
                created_by=request.user
            )
        
        return Response({'message': 'Transfer successful', 'transfer_group_id': group_id})

class ExpenseTemplateViewSet(BaseTreasuryViewSet):
    queryset = ExpenseTemplate.objects.all()
    serializer_class = ExpenseTemplateSerializer

    @action(detail=False, methods=['post'], url_path='generate-month')
    def generate_for_month(self, request):
        # MVP Placeholder: logic to checking and creating pending expenses
        # Not implementing full logic as it requires complex date math and checking existing
        return Response({'message': 'Not implemented in MVP'}, status=status.HTTP_501_NOT_IMPLEMENTED)

class ExpenseViewSet(BaseTreasuryViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    
    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        self.required_permission = 'manage_finance'
        
        expense = self.get_object()
        if expense.status == Expense.Status.PAID:
             return Response({'error': 'Already paid'}, status=status.HTTP_400_BAD_REQUEST)
        
        account_id = request.data.get('account_id')
        if not account_id:
            return Response({'error': 'Account required'}, status=status.HTTP_400_BAD_REQUEST)
            
        with transaction.atomic():
            trx = Transaction.objects.create(
                business=expense.business,
                account_id=account_id,
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
            expense.paid_account_id = account_id
            expense.payment_transaction = trx
            expense.save()
            
        return Response(ExpenseSerializer(expense).data)

class EmployeeViewSet(BaseTreasuryViewSet):
    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer

class PayrollPaymentViewSet(BaseTreasuryViewSet):
    queryset = PayrollPayment.objects.all()
    serializer_class = PayrollPaymentSerializer
    
    def perform_create(self, serializer):
        # Need account_id for the transaction
        # The PayrollPayment model has 'account' FK.
        # But we need to ensure the Transaction is created.
        
        with transaction.atomic():
             payment = serializer.save(business=self.request.business)
             
             # Create Treasury Transaction
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
             payment.save()

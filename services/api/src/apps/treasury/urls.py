from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AccountViewSet, TransactionCategoryViewSet, TransactionViewSet,
    ExpenseTemplateViewSet, ExpenseViewSet, EmployeeViewSet, PayrollPaymentViewSet,
    FixedExpenseViewSet, FixedExpensePeriodViewSet
)

router = DefaultRouter()
router.register(r'accounts', AccountViewSet)
router.register(r'categories', TransactionCategoryViewSet)
router.register(r'transactions', TransactionViewSet)
router.register(r'expense-templates', ExpenseTemplateViewSet)
router.register(r'expenses', ExpenseViewSet)
router.register(r'employees', EmployeeViewSet)
router.register(r'payroll-payments', PayrollPaymentViewSet)
router.register(r'fixed-expenses', FixedExpenseViewSet)
router.register(r'fixed-expense-periods', FixedExpensePeriodViewSet)

urlpatterns = [
    path('', include(router.urls)),
]

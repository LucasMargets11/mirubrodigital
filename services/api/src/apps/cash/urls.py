from django.urls import path

from .views import (
	ActiveCashSessionView,
	CashMovementView,
	CashPaymentView,
	CashRegisterListView,
	CashSessionCloseView,
	CashSessionCollectPendingView,
	CashSessionOpenView,
	CashSessionSummaryView,
	CashSummaryView,
)

app_name = 'cash'

urlpatterns = [
	path('registers/', CashRegisterListView.as_view(), name='register-list'),
	path('sessions/', CashSessionOpenView.as_view(), name='session-open'),
	path('sessions/active/', ActiveCashSessionView.as_view(), name='session-active'),
	path('summary/', CashSummaryView.as_view(), name='summary'),
	path('sessions/<uuid:pk>/summary/', CashSessionSummaryView.as_view(), name='session-summary'),
	path('sessions/<uuid:pk>/close/', CashSessionCloseView.as_view(), name='session-close'),
	path('sessions/<uuid:pk>/collect-pending/', CashSessionCollectPendingView.as_view(), name='session-collect-pending'),
	path('payments/', CashPaymentView.as_view(), name='payment-list-create'),
	path('movements/', CashMovementView.as_view(), name='movement-list-create'),
]

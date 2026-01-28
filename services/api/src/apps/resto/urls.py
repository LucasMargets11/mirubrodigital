from django.urls import path

from .views import (
	OrderTableAssignmentView,
	RestoOrderCreateView,
	TableConfigurationView,
	TableLayoutView,
	TableListView,
	TableStatusView,
)

app_name = 'resto'

urlpatterns = [
	path('tables/', TableListView.as_view(), name='table-list'),
	path('tables/layout/', TableLayoutView.as_view(), name='table-layout'),
	path('tables/status/', TableStatusView.as_view(), name='table-status'),
	path('tables/config/', TableConfigurationView.as_view(), name='table-config'),
	path('orders/', RestoOrderCreateView.as_view(), name='order-create'),
	path('orders/<uuid:pk>/table/', OrderTableAssignmentView.as_view(), name='order-table'),
]

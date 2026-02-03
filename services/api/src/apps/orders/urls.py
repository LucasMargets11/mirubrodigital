from django.urls import path

from .views import (
	OrderCancelView,
	OrderCloseView,
	OrderCheckoutView,
	OrderDetailView,
	OrderCreateSaleView,
	OrderDraftAssignTableView,
	OrderDraftConfirmView,
	OrderDraftDetailView,
	OrderDraftItemCreateView,
	OrderDraftItemDetailView,
	OrderDraftListCreateView,
	OrderItemCreateView,
	OrderItemDetailView,
	OrderListCreateView,
	OrderInvoiceView,
	OrderPayView,
	OrderStartView,
	OrderStatusUpdateView,
)
from .views_kitchen import (
    KitchenBoardView,
    KitchenItemStatusView,
    KitchenOrderBulkUpdateView
)

app_name = 'orders'

urlpatterns = [
    path('kitchen/board/', KitchenBoardView.as_view(), name='kitchen-board'),
    path('kitchen/items/<uuid:pk>/', KitchenItemStatusView.as_view(), name='kitchen-item-status'),
    path('kitchen/orders/<uuid:pk>/bulk/', KitchenOrderBulkUpdateView.as_view(), name='kitchen-order-bulk'),

	path('drafts/', OrderDraftListCreateView.as_view(), name='order-draft-list'),
	path('drafts/<uuid:pk>/', OrderDraftDetailView.as_view(), name='order-draft-detail'),
	path('drafts/<uuid:pk>/items/', OrderDraftItemCreateView.as_view(), name='order-draft-items'),
	path('drafts/<uuid:pk>/items/<uuid:item_pk>/', OrderDraftItemDetailView.as_view(), name='order-draft-item-detail'),
	path('drafts/<uuid:pk>/assign-table/', OrderDraftAssignTableView.as_view(), name='order-draft-assign-table'),
	path('drafts/<uuid:pk>/confirm/', OrderDraftConfirmView.as_view(), name='order-draft-confirm'),
	path('start/', OrderStartView.as_view(), name='order-start'),
	path('<uuid:pk>/checkout/', OrderCheckoutView.as_view(), name='order-checkout'),
	path('<uuid:pk>/create-sale/', OrderCreateSaleView.as_view(), name='order-create-sale'),
	path('<uuid:pk>/pay/', OrderPayView.as_view(), name='order-pay'),
	path('<uuid:pk>/items/', OrderItemCreateView.as_view(), name='order-items'),
	path('<uuid:pk>/items/<uuid:item_pk>/', OrderItemDetailView.as_view(), name='order-item-detail'),
	path('', OrderListCreateView.as_view(), name='order-list'),
	path('<uuid:pk>/', OrderDetailView.as_view(), name='order-detail'),
	path('<uuid:pk>/status/', OrderStatusUpdateView.as_view(), name='order-status'),
	path('<uuid:pk>/close/', OrderCloseView.as_view(), name='order-close'),
	path('<uuid:pk>/cancel/', OrderCancelView.as_view(), name='order-cancel'),
	path('<uuid:pk>/invoice/', OrderInvoiceView.as_view(), name='order-invoice'),
]

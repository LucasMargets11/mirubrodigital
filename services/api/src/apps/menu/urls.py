from django.urls import path

from .views import (
    MenuCategoryDetailView,
    MenuCategoryListCreateView,
    MenuExportView,
    MenuImportView,
    MenuItemDetailView,
    MenuItemListCreateView,
    MenuStructureView,
)

app_name = 'menu'

urlpatterns = [
    path('categories/', MenuCategoryListCreateView.as_view(), name='category-list'),
    path('categories/<uuid:pk>/', MenuCategoryDetailView.as_view(), name='category-detail'),
    path('items/', MenuItemListCreateView.as_view(), name='item-list'),
    path('items/<uuid:pk>/', MenuItemDetailView.as_view(), name='item-detail'),
    path('structure/', MenuStructureView.as_view(), name='structure'),
    path('import/', MenuImportView.as_view(), name='import'),
    path('export/', MenuExportView.as_view(), name='export'),
]

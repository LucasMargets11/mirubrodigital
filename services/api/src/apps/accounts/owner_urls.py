"""
URLs for Owner Access Management endpoints.
All routes are prefixed with /api/v1/owner/access/
"""
from django.urls import path

from . import owner_views

urlpatterns = [
    # Summary and lists
    path('summary/', owner_views.access_summary, name='owner-access-summary'),
    path('roles/', owner_views.roles_list, name='owner-roles-list'),
    path('roles/<str:role>/', owner_views.role_detail, name='owner-role-detail'),
    path('roles/<str:role>/permissions/', owner_views.update_role_permissions, name='owner-update-role-permissions'),
    path('accounts/', owner_views.accounts_list, name='owner-accounts-list'),
    
    # Account management actions
    path('accounts/<int:user_id>/reset-password/', owner_views.reset_password, name='owner-reset-password'),
    path('accounts/<int:user_id>/disable/', owner_views.disable_account, name='owner-disable-account'),
    
    # Audit logs
    path('audit-logs/', owner_views.audit_logs, name='owner-audit-logs'),
]

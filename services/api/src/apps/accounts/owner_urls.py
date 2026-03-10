"""
URLs for Owner Access Management endpoints.
All routes are prefixed with /api/v1/owner/access/
"""
from django.urls import path

from . import owner_views, employee_views

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

    # Wave 2 — extended owner management (B.1.a)
    path('accounts/<int:user_id>/role/', owner_views.change_role, name='owner-change-role'),
    path('accounts/<int:user_id>/suspend/', owner_views.suspend_member, name='owner-suspend-member'),
    path('accounts/<int:user_id>/', owner_views.remove_member, name='owner-remove-member'),
    
    # Audit logs
    path('audit-logs/', owner_views.audit_logs, name='owner-audit-logs'),

    # Operative employees
    path('employees/', employee_views.employees_list, name='owner-employees-list'),
    path('employees/<uuid:employee_id>/', employee_views.employee_detail, name='owner-employee-detail'),
    path('employees/<uuid:employee_id>/reset-pin/', employee_views.employee_reset_pin, name='owner-employee-reset-pin'),
    path('employees/<uuid:employee_id>/suspend/', employee_views.employee_suspend, name='owner-employee-suspend'),
    path('employees/<uuid:employee_id>/reactivate/', employee_views.employee_reactivate, name='owner-employee-reactivate'),
]

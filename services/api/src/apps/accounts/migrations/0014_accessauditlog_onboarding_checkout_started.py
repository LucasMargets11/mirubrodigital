"""
accounts/migrations/0014_accessauditlog_onboarding_checkout_started.py

Wave 4 — add ONBOARDING_CHECKOUT_STARTED to AccessAuditLog.action choices.

This is a choices-only migration (no DDL change needed — the underlying
CharField stores the raw string; adding a new valid choice is non-breaking
and requires no table alteration).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_backfill_active_users_email_verified'),
    ]

    operations = [
        migrations.AlterField(
            model_name='accessauditlog',
            name='action',
            field=models.CharField(
                max_length=32,
                choices=[
                    # ── Memberships ───────────────────────────────────────────────────
                    ('MEMBERSHIP_CREATED',    'Membership Created'),
                    ('MEMBERSHIP_UPDATED',    'Membership Updated'),
                    ('MEMBERSHIP_DELETED',    'Membership Deleted'),
                    ('MEMBERSHIP_SUSPENDED',  'Membership Suspended'),
                    # ── Contraseñas / acceso admin ────────────────────────────────────
                    ('PASSWORD_RESET',              'Password Reset'),
                    ('PASSWORD_RESET_CONFIRMED',    'Password Reset Confirmed'),
                    ('EMAIL_VERIFICATION_SENT',     'Email Verification Sent'),
                    ('EMAIL_VERIFIED',              'Email Verified'),
                    # ── Cuentas operativas ────────────────────────────────────────────
                    ('EMPLOYEE_CREATED',      'Employee Created'),
                    ('EMPLOYEE_UPDATED',      'Employee Updated'),
                    ('EMPLOYEE_SUSPENDED',    'Employee Suspended'),
                    ('EMPLOYEE_REACTIVATED',  'Employee Reactivated'),
                    ('EMPLOYEE_DELETED',      'Employee Deleted'),
                    ('PIN_RESET',          'PIN Reset'),
                    ('PIN_CHANGED',        'PIN Changed'),
                    ('PIN_ROTATED',        'PIN Rotated'),
                    # ── Roles y permisos ──────────────────────────────────────────────
                    ('ROLE_CHANGED',              'Role Changed'),
                    ('PERMISSION_OVERRIDE_SET',   'Permission Override Set'),
                    ('ROLE_PERMISSIONS_UPDATED',  'Role Permissions Updated'),
                    # ── Caja ─────────────────────────────────────────────────────────
                    ('CASH_SESSION_OPENED',      'Cash Session Opened'),
                    ('CASH_SESSION_CLOSED',      'Cash Session Closed'),
                    ('CASH_SESSION_FORCE_CLOSED','Cash Session Force Closed'),
                    ('CASH_MOVEMENT_CREATED',    'Cash Movement Created'),
                    ('OPERATOR_SESSION_STARTED', 'Operator Session Started'),
                    ('OPERATOR_SESSION_ENDED',   'Operator Session Ended'),
                    # ── Sales POS ─────────────────────────────────────────────────────────
                    ('SALE_CREATED_POS', 'Sale Created (POS)'),
                    # ── Suscripción ───────────────────────────────────────────────────
                    ('SUBSCRIPTION_CREATED',        'Subscription Created'),
                    ('SUBSCRIPTION_STATUS_CHANGED', 'Subscription Status Changed'),
                    ('SUBSCRIPTION_CANCELED',       'Subscription Canceled'),
                    ('TRIAL_STARTED',               'Trial Started'),
                    ('TRIAL_EXPIRED',               'Trial Expired'),
                    # ── Seguridad ─────────────────────────────────────────────────────
                    ('SESSION_REVOKED',   'Session Revoked'),
                    ('SESSIONS_REVOKED',  'Sessions Revoked'),
                    ('LOGIN_FAILED',      'Login Failed'),
                    ('ACCESS_DENIED',     'Access Denied'),
                    # ── Onboarding (Wave 3 / Wave 4) ─────────────────────────────────
                    ('EMAIL_VERIFICATION_BLOCKED',   'Email Verification Blocked'),
                    ('ONBOARDING_SERVICE_SELECTED',  'Onboarding Service Selected'),
                    ('ONBOARDING_CHECKOUT_STARTED',  'Onboarding Checkout Started'),
                    ('ONBOARDING_COMPLETED',         'Onboarding Completed'),
                    # ── Legacy ────────────────────────────────────────────────────────
                    ('ACCOUNT_DISABLED', 'Account Disabled'),
                    ('ACCOUNT_ENABLED',  'Account Enabled'),
                ],
            ),
        ),
    ]

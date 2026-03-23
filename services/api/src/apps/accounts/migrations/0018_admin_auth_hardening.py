"""
Phase 1.1 — Admin authentication hardening.

Adds:
  - MFA fields to AccountProfile (mfa_secret_encrypted, mfa_enabled,
    mfa_recovery_codes, mfa_enrolled_at)
  - Makes AccessAuditLog.business nullable (platform-level events have no business)
  - Extends AccessAuditLog.action choices with admin auth events
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_accountprofile_platform_staff'),
        ('business', '0001_initial'),
    ]

    operations = [
        # ── MFA fields on AccountProfile ──────────────────────────────────
        migrations.AddField(
            model_name='accountprofile',
            name='mfa_secret_encrypted',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Fernet-encrypted TOTP secret for admin MFA.',
            ),
        ),
        migrations.AddField(
            model_name='accountprofile',
            name='mfa_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Whether TOTP MFA is active for this admin user.',
            ),
        ),
        migrations.AddField(
            model_name='accountprofile',
            name='mfa_recovery_codes',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Hashed single-use recovery codes.',
            ),
        ),
        migrations.AddField(
            model_name='accountprofile',
            name='mfa_enrolled_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
            ),
        ),
        # ── Make AccessAuditLog.business nullable ─────────────────────────
        migrations.AlterField(
            model_name='accessauditlog',
            name='business',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='access_audit_logs',
                to='business.business',
            ),
        ),
        # ── Extend action choices ─────────────────────────────────────────
        migrations.AlterField(
            model_name='accessauditlog',
            name='action',
            field=models.CharField(
                max_length=32,
                choices=[
                    ('MEMBERSHIP_CREATED', 'Membership Created'),
                    ('MEMBERSHIP_UPDATED', 'Membership Updated'),
                    ('MEMBERSHIP_DELETED', 'Membership Deleted'),
                    ('MEMBERSHIP_SUSPENDED', 'Membership Suspended'),
                    ('MEMBER_REACTIVATED', 'Member Reactivated'),
                    ('MEMBER_REMOVED', 'Member Removed'),
                    ('USER_CREATED', 'Internal User Created'),
                    ('PASSWORD_RESET', 'Password Reset'),
                    ('PASSWORD_RESET_CONFIRMED', 'Password Reset Confirmed'),
                    ('EMAIL_VERIFICATION_SENT', 'Email Verification Sent'),
                    ('EMAIL_VERIFIED', 'Email Verified'),
                    ('EMPLOYEE_CREATED', 'Employee Created'),
                    ('EMPLOYEE_UPDATED', 'Employee Updated'),
                    ('EMPLOYEE_SUSPENDED', 'Employee Suspended'),
                    ('EMPLOYEE_REACTIVATED', 'Employee Reactivated'),
                    ('EMPLOYEE_DELETED', 'Employee Deleted'),
                    ('PIN_RESET', 'PIN Reset'),
                    ('PIN_CHANGED', 'PIN Changed'),
                    ('PIN_ROTATED', 'PIN Rotated'),
                    ('ROLE_CHANGED', 'Role Changed'),
                    ('PERMISSION_OVERRIDE_SET', 'Permission Override Set'),
                    ('ROLE_PERMISSIONS_UPDATED', 'Role Permissions Updated'),
                    ('CASH_SESSION_OPENED', 'Cash Session Opened'),
                    ('CASH_SESSION_CLOSED', 'Cash Session Closed'),
                    ('CASH_SESSION_FORCE_CLOSED', 'Cash Session Force Closed'),
                    ('CASH_MOVEMENT_CREATED', 'Cash Movement Created'),
                    ('OPERATOR_SESSION_STARTED', 'Operator Session Started'),
                    ('OPERATOR_SESSION_ENDED', 'Operator Session Ended'),
                    ('SALE_CREATED_POS', 'Sale Created (POS)'),
                    ('SUBSCRIPTION_CREATED', 'Subscription Created'),
                    ('SUBSCRIPTION_STATUS_CHANGED', 'Subscription Status Changed'),
                    ('SUBSCRIPTION_CANCELED', 'Subscription Canceled'),
                    ('TRIAL_STARTED', 'Trial Started'),
                    ('TRIAL_EXPIRED', 'Trial Expired'),
                    ('SESSION_REVOKED', 'Session Revoked'),
                    ('SESSIONS_REVOKED', 'Sessions Revoked'),
                    ('LOGIN_FAILED', 'Login Failed'),
                    ('ACCESS_DENIED', 'Access Denied'),
                    ('EMAIL_VERIFICATION_BLOCKED', 'Email Verification Blocked'),
                    ('ONBOARDING_SERVICE_SELECTED', 'Onboarding Service Selected'),
                    ('ONBOARDING_CHECKOUT_STARTED', 'Onboarding Checkout Started'),
                    ('ONBOARDING_COMPLETED', 'Onboarding Completed'),
                    ('ACCOUNT_DISABLED', 'Account Disabled'),
                    ('ACCOUNT_ENABLED', 'Account Enabled'),
                    ('PLATFORM_ADMIN_LOGIN', 'Platform Admin Login'),
                    ('PLATFORM_ADMIN_ACTION', 'Platform Admin Generic Action'),
                    ('PLATFORM_STAFF_GRANTED', 'Platform Staff Access Granted'),
                    ('PLATFORM_STAFF_REVOKED', 'Platform Staff Access Revoked'),
                    ('PLATFORM_ROLE_CHANGED', 'Platform Internal Role Changed'),
                    # Phase 1.1 admin auth hardening
                    ('ADMIN_LOGIN_SUCCESS', 'Admin Login Success'),
                    ('ADMIN_LOGIN_FAILED', 'Admin Login Failed'),
                    ('ADMIN_LOGIN_THROTTLED', 'Admin Login Throttled'),
                    ('ADMIN_LOGIN_COOLDOWN', 'Admin Login Cooldown Triggered'),
                    ('ADMIN_LOGIN_BLOCKED_IP', 'Admin Login Blocked IP'),
                    ('ADMIN_MFA_REQUIRED', 'Admin MFA Required'),
                    ('ADMIN_MFA_SUCCESS', 'Admin MFA Success'),
                    ('ADMIN_MFA_FAILED', 'Admin MFA Failed'),
                    ('ADMIN_MFA_RECOVERY_USED', 'Admin MFA Recovery Code Used'),
                    ('ADMIN_MFA_ENABLED', 'Admin MFA Enabled'),
                    ('ADMIN_MFA_DISABLED', 'Admin MFA Disabled'),
                    ('ADMIN_MFA_RESET', 'Admin MFA Reset'),
                    ('ADMIN_SUSPICIOUS_AUTH', 'Admin Suspicious Auth Pattern'),
                ],
            ),
        ),
    ]

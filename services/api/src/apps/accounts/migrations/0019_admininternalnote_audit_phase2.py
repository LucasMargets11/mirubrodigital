"""
Migration: Create AdminInternalNote model + extend AccessAuditLog ACTION_CHOICES.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0018_admin_auth_hardening'),
    ]

    operations = [
        # ── AdminInternalNote table ──────────────────────────────────────
        migrations.CreateModel(
            name='AdminInternalNote',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('target_type', models.CharField(db_index=True, max_length=64)),
                ('target_id', models.CharField(db_index=True, max_length=64)),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='admin_internal_notes',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='admininternalnote',
            index=models.Index(fields=['target_type', 'target_id'], name='admin_note_target_idx'),
        ),
        # ── Extend ACTION_CHOICES (choices-only, no schema change) ───────
        migrations.AlterField(
            model_name='accessauditlog',
            name='action',
            field=models.CharField(
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
                    # ── Admin Backoffice Phase 2 ──────────────────────────
                    ('ADMIN_CLIENT_VIEWED', 'Admin Client Viewed'),
                    ('ADMIN_SUBSCRIPTION_VIEWED', 'Admin Subscription Viewed'),
                    ('ADMIN_NOTE_CREATED', 'Admin Internal Note Created'),
                ],
                max_length=32,
            ),
        ),
    ]

"""
Adds USER_CREATED, MEMBER_REACTIVATED, MEMBER_REMOVED to AccessAuditLog.ACTION_CHOICES.
Choices-only migration — no schema changes.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_alter_accountprofile_options'),
    ]

    operations = [
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
                ],
                max_length=32,
            ),
        ),
    ]

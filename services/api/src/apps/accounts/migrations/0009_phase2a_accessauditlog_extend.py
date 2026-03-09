# Phase 2A – AccessAuditLog extension
# Adds: actor_type, actor_employee FK, entity_type, entity_id,
#        before_json, after_json + entity index.
# Expands ACTION_CHOICES (AlterField) to include all Phase 1 v2.0 actions.
# All new fields are nullable or have safe defaults → non-destructive on existing data.
# actor_type defaults to 'USER' to preserve semantics of all existing rows.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_phase2a_employeeprofile'),
    ]

    operations = [
        # ── actor_type enum ──────────────────────────────────────────────────
        migrations.AddField(
            model_name='accessauditlog',
            name='actor_type',
            field=models.CharField(
                max_length=16,
                default='USER',
                choices=[
                    ('USER',     'Usuario Admin'),
                    ('EMPLOYEE', 'Empleado Operativo'),
                    ('SYSTEM',   'Sistema / Tarea Automatizada'),
                ],
                help_text='USER for admin actions; EMPLOYEE for POS actions; SYSTEM for tasks.',
            ),
        ),
        # ── actor_employee FK ────────────────────────────────────────────────
        migrations.AddField(
            model_name='accessauditlog',
            name='actor_employee',
            field=models.ForeignKey(
                to='accounts.EmployeeProfile',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='audit_actions_performed',
            ),
        ),
        # ── entity fields ────────────────────────────────────────────────────
        migrations.AddField(
            model_name='accessauditlog',
            name='entity_type',
            field=models.CharField(
                max_length=64,
                blank=True,
                default='',
                help_text='Model name of affected object. e.g. membership, employee_profile.',
            ),
        ),
        migrations.AddField(
            model_name='accessauditlog',
            name='entity_id',
            field=models.CharField(
                max_length=64,
                blank=True,
                default='',
                help_text='PK of the affected object (UUID or int as string).',
            ),
        ),
        # ── diff fields ──────────────────────────────────────────────────────
        migrations.AddField(
            model_name='accessauditlog',
            name='before_json',
            field=models.JSONField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='accessauditlog',
            name='after_json',
            field=models.JSONField(null=True, blank=True),
        ),
        # ── entity lookup index ──────────────────────────────────────────────
        migrations.AddIndex(
            model_name='accessauditlog',
            index=models.Index(
                fields=['entity_type', 'entity_id'],
                name='auditlog_entity_idx',
            ),
        ),
        # ── Expand ACTION_CHOICES to include all Phase 1 v2.0 actions ────────
        # AlterField is Django-only metadata; no DDL executed (VARCHAR choices are not enforced in PG).
        migrations.AlterField(
            model_name='accessauditlog',
            name='action',
            field=models.CharField(
                max_length=32,
                choices=[
                    ('MEMBERSHIP_CREATED',           'Membership Created'),
                    ('MEMBERSHIP_UPDATED',           'Membership Updated'),
                    ('MEMBERSHIP_DELETED',           'Membership Deleted'),
                    ('MEMBERSHIP_SUSPENDED',         'Membership Suspended'),
                    ('PASSWORD_RESET',               'Password Reset'),
                    ('PASSWORD_RESET_CONFIRMED',     'Password Reset Confirmed'),
                    ('EMAIL_VERIFICATION_SENT',      'Email Verification Sent'),
                    ('EMAIL_VERIFIED',               'Email Verified'),
                    ('EMPLOYEE_CREATED',             'Employee Created'),
                    ('EMPLOYEE_UPDATED',             'Employee Updated'),
                    ('EMPLOYEE_SUSPENDED',           'Employee Suspended'),
                    ('EMPLOYEE_DELETED',             'Employee Deleted'),
                    ('PIN_RESET',                    'PIN Reset'),
                    ('PIN_CHANGED',                  'PIN Changed'),
                    ('PIN_ROTATED',                  'PIN Rotated'),
                    ('ROLE_CHANGED',                 'Role Changed'),
                    ('PERMISSION_OVERRIDE_SET',      'Permission Override Set'),
                    ('ROLE_PERMISSIONS_UPDATED',     'Role Permissions Updated'),
                    ('CASH_SESSION_OPENED',          'Cash Session Opened'),
                    ('CASH_SESSION_CLOSED',          'Cash Session Closed'),
                    ('CASH_SESSION_FORCE_CLOSED',    'Cash Session Force Closed'),
                    ('OPERATOR_SESSION_STARTED',     'Operator Session Started'),
                    ('OPERATOR_SESSION_ENDED',       'Operator Session Ended'),
                    ('SUBSCRIPTION_CREATED',         'Subscription Created'),
                    ('SUBSCRIPTION_STATUS_CHANGED',  'Subscription Status Changed'),
                    ('SUBSCRIPTION_CANCELED',        'Subscription Canceled'),
                    ('TRIAL_STARTED',                'Trial Started'),
                    ('TRIAL_EXPIRED',                'Trial Expired'),
                    ('SESSION_REVOKED',              'Session Revoked'),
                    ('SESSIONS_REVOKED',             'Sessions Revoked'),
                    ('LOGIN_FAILED',                 'Login Failed'),
                    ('ACCESS_DENIED',                'Access Denied'),
                    ('ACCOUNT_DISABLED',             'Account Disabled'),
                    ('ACCOUNT_ENABLED',              'Account Enabled'),
                ],
            ),
        ),
    ]

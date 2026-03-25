"""
Phase 3: Support tickets — SupportTicket + TicketMessage models, audit actions.
"""
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0019_admininternalnote_audit_phase2'),
        ('business', '0001_initial'),
        ('billing', '0005_phase2a_subscriptionv2_billing'),
    ]

    operations = [
        # ── SupportTicket ────────────────────────────────────────────────
        migrations.CreateModel(
            name='SupportTicket',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reference', models.CharField(editable=False, help_text='Human-readable reference like TK-0001', max_length=16, unique=True)),
                ('subject', models.CharField(max_length=200)),
                ('status', models.CharField(choices=[
                    ('open', 'Abierto'),
                    ('in_progress', 'En curso'),
                    ('waiting_on_client', 'Esperando cliente'),
                    ('resolved', 'Resuelto'),
                    ('closed', 'Cerrado'),
                ], db_index=True, default='open', max_length=20)),
                ('priority', models.CharField(choices=[
                    ('low', 'Baja'),
                    ('medium', 'Media'),
                    ('high', 'Alta'),
                    ('urgent', 'Urgente'),
                ], db_index=True, default='medium', max_length=10)),
                ('category', models.CharField(choices=[
                    ('billing', 'Facturación / Pagos'),
                    ('technical', 'Problema técnico'),
                    ('account', 'Cuenta / Acceso'),
                    ('feature_request', 'Solicitud de funcionalidad'),
                    ('other', 'Otro'),
                ], db_index=True, default='other', max_length=20)),
                ('contact_email', models.EmailField(blank=True, help_text='Tenant contact email for this ticket', max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='support_tickets', to='business.business')),
                ('subscription', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='support_tickets', to='billing.subscriptionv2')),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_tickets', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_tickets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='supportticket',
            index=models.Index(fields=['status', 'priority'], name='ticket_status_prio_idx'),
        ),
        migrations.AddIndex(
            model_name='supportticket',
            index=models.Index(fields=['business', 'status'], name='ticket_biz_status_idx'),
        ),

        # ── TicketMessage ────────────────────────────────────────────────
        migrations.CreateModel(
            name='TicketMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('body', models.TextField(max_length=5000)),
                ('is_system', models.BooleanField(default=False, help_text='True for auto-generated status-change messages')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='accounts.supportticket')),
                ('author', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ticket_messages', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),

        # ── Audit actions ────────────────────────────────────────────────
        migrations.AlterField(
            model_name='accessauditlog',
            name='action',
            field=models.CharField(
                max_length=32,
                choices=[
                    ('LOGIN', 'Login'),
                    ('LOGOUT', 'Logout'),
                    ('OWNER_REGISTERED', 'Owner Registered'),
                    ('EMPLOYEE_INVITED', 'Employee Invited'),
                    ('EMPLOYEE_ACCEPTED', 'Employee Accepted Invite'),
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
                    ('ADMIN_CLIENT_VIEWED', 'Admin Client Viewed'),
                    ('ADMIN_SUBSCRIPTION_VIEWED', 'Admin Subscription Viewed'),
                    ('ADMIN_NOTE_CREATED', 'Admin Internal Note Created'),
                    ('ADMIN_TICKET_CREATED', 'Admin Ticket Created'),
                    ('ADMIN_TICKET_UPDATED', 'Admin Ticket Updated'),
                    ('ADMIN_TICKET_VIEWED', 'Admin Ticket Viewed'),
                    ('ADMIN_TICKET_MESSAGE', 'Admin Ticket Message Sent'),
                ],
            ),
        ),
    ]

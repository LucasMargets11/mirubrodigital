# Generated migration for AccessAuditLog model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0002_alter_membership_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[
                    ('PASSWORD_RESET', 'Password Reset'),
                    ('PIN_ROTATED', 'PIN Rotated'),
                    ('ACCOUNT_DISABLED', 'Account Disabled'),
                    ('ACCOUNT_ENABLED', 'Account Enabled'),
                    ('ROLE_CHANGED', 'Role Changed'),
                    ('SESSIONS_REVOKED', 'Sessions Revoked'),
                    ('MEMBERSHIP_CREATED', 'Membership Created'),
                    ('MEMBERSHIP_DELETED', 'Membership Deleted'),
                ], max_length=32)),
                ('details', models.JSONField(blank=True, default=dict, help_text='Additional context (e.g., old_role, new_role)')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    help_text='User who performed the action',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='audit_actions_performed',
                    to=settings.AUTH_USER_MODEL
                )),
                ('target_user', models.ForeignKey(
                    help_text='User affected by the action',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='audit_actions_received',
                    to=settings.AUTH_USER_MODEL
                )),
                ('business', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='access_audit_logs',
                    to='business.business'
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='accessauditlog',
            index=models.Index(fields=['business', '-created_at'], name='accounts_ac_busines_idx'),
        ),
        migrations.AddIndex(
            model_name='accessauditlog',
            index=models.Index(fields=['target_user', '-created_at'], name='accounts_ac_target__idx'),
        ),
    ]

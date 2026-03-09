# Phase 2A – Membership model extension
# Adds: status, branch_scope FK, permissions JSONB, created_by_user FK,
#        updated_by_user FK, updated_at + indexes.
# All new fields are nullable or have safe defaults → zero downtime on existing data.
# RISK: AddIndex on large Membership tables may briefly lock; acceptable for typical SaaS.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_accessauditlog_action'),
        # branch_scope FK references business.Business (added in 0015 is fine; table exists from 0001)
        ('business', '0015_phase2a_business_extend'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── status ──────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='membership',
            name='status',
            field=models.CharField(
                max_length=16,
                default='active',
                choices=[
                    ('active',    'Activo'),
                    ('inactive',  'Inactivo'),
                    ('suspended', 'Suspendido'),
                ],
            ),
        ),
        # ── branch_scope ─────────────────────────────────────────────────────
        migrations.AddField(
            model_name='membership',
            name='branch_scope',
            field=models.ForeignKey(
                to='business.Business',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='scoped_memberships',
                help_text='NULL = full tree access. Set to restrict to one branch.',
            ),
        ),
        # ── permissions JSONB ────────────────────────────────────────────────
        migrations.AddField(
            model_name='membership',
            name='permissions',
            field=models.JSONField(null=True, blank=True),
        ),
        # ── created_by_user ──────────────────────────────────────────────────
        migrations.AddField(
            model_name='membership',
            name='created_by_user',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='memberships_created',
            ),
        ),
        # ── updated_by_user ──────────────────────────────────────────────────
        migrations.AddField(
            model_name='membership',
            name='updated_by_user',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='memberships_updated',
            ),
        ),
        # ── updated_at ───────────────────────────────────────────────────────
        migrations.AddField(
            model_name='membership',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        # ── indexes ──────────────────────────────────────────────────────────
        migrations.AddIndex(
            model_name='membership',
            index=models.Index(
                fields=['business', 'status'],
                name='membership_business_status_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='membership',
            index=models.Index(
                fields=['user', 'status'],
                name='membership_user_status_idx',
            ),
        ),
    ]

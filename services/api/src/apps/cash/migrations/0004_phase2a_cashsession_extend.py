# Phase 2A – CashSession extension
# Adds: branch FK, terminal FK (Phase 2A canonical), opened_by_employee FK,
#        closed_by_employee FK, AUDITED status value, new indexes + terminal constraint.
# Legacy fields (opened_by, closed_by, register) remain untouched.
# All new FK fields are nullable → zero risk for existing rows.
# RISK: Adding index on `business, opened_at` may lock briefly on large tables.

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        # Terminal must exist first (cash 0003)
        ('cash', '0003_phase2a_terminal'),
        # EmployeeProfile must exist (accounts 0008)
        ('accounts', '0008_phase2a_employeeprofile'),
        ('business', '0015_phase2a_business_extend'),
    ]

    operations = [
        # ── Add AUDITED to status choices (AlterField = metadata only, no DDL) ──
        migrations.AlterField(
            model_name='cashsession',
            name='status',
            field=models.CharField(
                max_length=16,
                default='open',
                choices=[
                    ('open',    'Abierta'),
                    ('closed',  'Cerrada'),
                    ('audited', 'Auditada'),
                ],
            ),
        ),
        # ── branch FK ────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='cashsession',
            name='branch',
            field=models.ForeignKey(
                to='business.Business',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='branch_cash_sessions',
            ),
        ),
        # ── terminal FK (Phase 2A canonical) ─────────────────────────────────
        migrations.AddField(
            model_name='cashsession',
            name='terminal',
            field=models.ForeignKey(
                to='cash.Terminal',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='cash_sessions',
                help_text='Phase 2A canonical terminal. Coexists with legacy `register`.',
            ),
        ),
        # ── opened_by_employee FK ─────────────────────────────────────────────
        migrations.AddField(
            model_name='cashsession',
            name='opened_by_employee',
            field=models.ForeignKey(
                to='accounts.EmployeeProfile',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='cash_sessions_opened',
            ),
        ),
        # ── closed_by_employee FK ─────────────────────────────────────────────
        migrations.AddField(
            model_name='cashsession',
            name='closed_by_employee',
            field=models.ForeignKey(
                to='accounts.EmployeeProfile',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='cash_sessions_closed',
            ),
        ),
        # ── Partial unique: one OPEN session per Terminal ─────────────────────
        # PostgreSQL NULL semantics: rows where terminal_id IS NULL are excluded
        # from uniqueness check → existing legacy rows (terminal=NULL) are safe.
        migrations.AddConstraint(
            model_name='cashsession',
            constraint=models.UniqueConstraint(
                fields=['terminal'],
                condition=Q(status='open'),
                name='cash_session_one_open_per_terminal',
            ),
        ),
        # ── Performance indexes ──────────────────────────────────────────────
        migrations.AddIndex(
            model_name='cashsession',
            index=models.Index(
                fields=['business', 'status'],
                name='cashsess_biz_stat_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='cashsession',
            index=models.Index(
                fields=['business', 'opened_at'],
                name='cashsess_biz_open_idx',
            ),
        ),
    ]

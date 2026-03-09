# Phase 2A – Create OperatorSession
# New model: who is actively operating a Terminal at a given point in time.
# Decoupled from CashSession: kitchen/server terminals have OperatorSessions
# without any CashSession. cash_session FK is optional.
# Rule enforced at DB level: ONE active (logout_at IS NULL) session per Terminal.

import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        # Terminal (cash 0003) and CashSession extension (cash 0004) must exist
        ('cash', '0004_phase2a_cashsession_extend'),
        # EmployeeProfile (accounts 0008) must exist
        ('accounts', '0008_phase2a_employeeprofile'),
    ]

    operations = [
        migrations.CreateModel(
            name='OperatorSession',
            fields=[
                ('id', models.UUIDField(
                    primary_key=True, default=uuid.uuid4, editable=False, serialize=False,
                )),
                ('terminal', models.ForeignKey(
                    to='cash.Terminal',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='operator_sessions',
                )),
                ('employee', models.ForeignKey(
                    to='accounts.EmployeeProfile',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='operator_sessions',
                )),
                # Optional: only set when terminal_type=CASHIER and a CashSession is open
                ('cash_session', models.ForeignKey(
                    to='cash.CashSession',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='operator_sessions',
                )),
                ('login_at',       models.DateTimeField(auto_now_add=True)),
                ('logout_at',      models.DateTimeField(null=True, blank=True)),
                ('auto_logout_at', models.DateTimeField(null=True, blank=True)),
                ('total_orders',   models.PositiveIntegerField(default=0)),
                ('created_at',     models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'indexes': [
                    models.Index(
                        fields=['terminal', 'logout_at'],
                        name='opsession_terminal_logout_idx',
                    ),
                    models.Index(
                        fields=['employee', 'logout_at'],
                        name='opsession_employee_logout_idx',
                    ),
                ],
                'constraints': [
                    # At most ONE active (logout_at IS NULL) session per Terminal.
                    # Rows with NULL terminal_id are excluded by PG NULL semantics (not applicable
                    # here since terminal is required, but partial condition makes intent explicit).
                    models.UniqueConstraint(
                        fields=['terminal'],
                        condition=Q(logout_at__isnull=True),
                        name='uq_operator_session_active_per_terminal',
                    ),
                ],
            },
        ),
    ]

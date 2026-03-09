# Phase 2A – Create Terminal
# New model: canonical point-of-sale device/terminal.
# Extends (but does not replace) legacy CashRegister in this phase.
# cash_register FK provides a transition link to existing CashRegister rows.
# Full CashRegister → Terminal consolidation is deferred to Phase 2C.
# Fully additive migration – no existing tables modified.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # needs Business (FK) and CashRegister (OneToOneField)
        ('cash', '0002_cashsession_opened_by_name'),
        ('business', '0015_phase2a_business_extend'),
    ]

    operations = [
        migrations.CreateModel(
            name='Terminal',
            fields=[
                ('id', models.UUIDField(
                    primary_key=True, default=uuid.uuid4, editable=False, serialize=False,
                )),
                ('business', models.ForeignKey(
                    to='business.Business',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='terminals',
                )),
                ('branch', models.ForeignKey(
                    to='business.Business',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='branch_terminals',
                )),
                # Transition: link to legacy CashRegister if migrated. NULL for new terminals.
                ('cash_register', models.OneToOneField(
                    to='cash.CashRegister',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='terminal',
                )),
                ('code', models.CharField(max_length=32)),
                ('name', models.CharField(max_length=128)),
                ('terminal_type', models.CharField(
                    max_length=16,
                    default='cashier',
                    choices=[
                        ('cashier',  'Caja'),
                        ('server',   'Mozo / Salón'),
                        ('kitchen',  'Cocina'),
                        ('delivery', 'Delivery'),
                    ],
                )),
                ('shared_mode_enabled',          models.BooleanField(default=False)),
                ('requires_operator_selection',  models.BooleanField(default=False)),
                ('device_token', models.CharField(max_length=256, blank=True)),
                ('is_active',    models.BooleanField(default=True)),
                ('config',       models.JSONField(null=True, blank=True)),
                ('created_at',   models.DateTimeField(auto_now_add=True)),
                ('updated_at',   models.DateTimeField(auto_now=True)),
            ],
            options={
                'indexes': [
                    models.Index(
                        fields=['business', 'is_active'],
                        name='terminal_business_active_idx',
                    ),
                    models.Index(
                        fields=['branch'],
                        name='terminal_branch_idx',
                    ),
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=['business', 'code'],
                        name='uq_terminal_code_per_business',
                    ),
                ],
            },
        ),
    ]

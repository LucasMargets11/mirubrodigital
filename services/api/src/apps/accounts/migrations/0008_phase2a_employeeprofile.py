# Phase 2A – Create EmployeeProfile
# New model: operational identity for POS staff (cashiers, servers, kitchen, delivery).
# No email required. Authentication via employee_code + login_code_hash (PIN).
# Fully additive migration – no existing tables modified.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_phase2a_membership_extend'),
        # business.Business must exist (FK)
        ('business', '0015_phase2a_business_extend'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EmployeeProfile',
            fields=[
                ('id', models.UUIDField(
                    primary_key=True, default=uuid.uuid4, editable=False, serialize=False,
                )),
                ('business', models.ForeignKey(
                    to='business.Business',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='employee_profiles',
                )),
                ('branch', models.ForeignKey(
                    to='business.Business',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='branch_employee_profiles',
                )),
                ('linked_user', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='employee_profiles',
                )),
                ('first_name',  models.CharField(max_length=120)),
                ('last_name',   models.CharField(max_length=120)),
                ('alias',       models.CharField(max_length=80, blank=True)),
                ('employee_code', models.CharField(max_length=20)),
                ('role_type', models.CharField(
                    max_length=20,
                    choices=[
                        ('cashier',    'Cajero'),
                        ('server',     'Mozo / Salón'),
                        ('kitchen',    'Cocina'),
                        ('delivery',   'Delivery'),
                        ('manager_op', 'Encargado Operativo'),
                    ],
                )),
                ('credential_type', models.CharField(
                    max_length=16,
                    default='pin',
                    choices=[
                        ('pin',     'PIN Numérico'),
                        ('qr_code', 'Código QR'),
                        ('nfc_tag', 'Tag NFC'),
                    ],
                )),
                # Hash only. Never indexed. Verified in-memory after fetching by employee_code.
                ('login_code_hash', models.CharField(max_length=256)),
                ('must_change_pin', models.BooleanField(default=False)),
                ('permission_overrides', models.JSONField(null=True, blank=True)),
                ('status', models.CharField(
                    max_length=16,
                    default='active',
                    choices=[
                        ('active',    'Activo'),
                        ('inactive',  'Inactivo'),
                        ('suspended', 'Suspendido'),
                    ],
                )),
                ('created_by_membership', models.ForeignKey(
                    to='accounts.Membership',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='created_employee_profiles',
                )),
                ('updated_by_membership', models.ForeignKey(
                    to='accounts.Membership',
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name='updated_employee_profiles',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'indexes': [
                    models.Index(
                        fields=['business', 'employee_code'],
                        name='employee_code_lookup_idx',
                    ),
                    models.Index(
                        fields=['business', 'status'],
                        name='employee_business_status_idx',
                    ),
                    models.Index(
                        fields=['branch', 'status'],
                        name='employee_branch_status_idx',
                    ),
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=['business', 'employee_code'],
                        name='uq_employee_code_per_business',
                    ),
                ],
            },
        ),
    ]

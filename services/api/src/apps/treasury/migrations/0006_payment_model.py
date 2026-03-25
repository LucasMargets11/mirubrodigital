"""
Sprint 1 — Payment model + ExpenseTemplate frozen

Creates the Payment entity for decoupled payment tracking.
ExpenseTemplate is marked managed=False (table stays, Django ignores it).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('treasury', '0005_expense_auto_source_fields'),
        ('business', '0001_initial'),
    ]

    operations = [
        # ── Create Payment model ──────────────────────────────────────────
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'business',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='treasury_payments',
                        to='business.business',
                    ),
                ),
                (
                    'expense',
                    models.ForeignKey(
                        blank=True,
                        help_text='Gasto puntual pagado (mutuamente excluyente con fixed_expense_period)',
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='payments',
                        to='treasury.expense',
                    ),
                ),
                (
                    'fixed_expense_period',
                    models.ForeignKey(
                        blank=True,
                        help_text='Período de gasto fijo pagado (mutuamente excluyente con expense)',
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='payments',
                        to='treasury.fixedexpenseperiod',
                    ),
                ),
                (
                    'transaction',
                    models.OneToOneField(
                        blank=True,
                        help_text='Transacción financiera asociada al pago',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='payment',
                        to='treasury.transaction',
                    ),
                ),
                (
                    'account',
                    models.ForeignKey(
                        blank=True,
                        help_text='Cuenta desde la que se realizó el pago',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='payments',
                        to='treasury.account',
                    ),
                ),
                ('amount', models.DecimalField(decimal_places=4, max_digits=19)),
                ('currency', models.CharField(default='ARS', max_length=10)),
                (
                    'status',
                    models.CharField(
                        choices=[('completed', 'Completado'), ('voided', 'Anulado')],
                        default='completed',
                        max_length=20,
                    ),
                ),
                ('paid_at', models.DateTimeField()),
                (
                    'is_backfilled',
                    models.BooleanField(
                        default=False,
                        help_text='True si fue generado por el backfill de migración',
                    ),
                ),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'indexes': [
                    models.Index(fields=['business', 'status'], name='payment_biz_status_idx'),
                    models.Index(fields=['business', 'paid_at'], name='payment_biz_paid_idx'),
                ],
                'constraints': [
                    models.CheckConstraint(
                        check=(
                            models.Q(expense__isnull=False, fixed_expense_period__isnull=True)
                            | models.Q(expense__isnull=True, fixed_expense_period__isnull=False)
                        ),
                        name='payment_exactly_one_source',
                    ),
                    models.UniqueConstraint(
                        fields=['expense'],
                        condition=models.Q(status='completed', expense__isnull=False),
                        name='payment_one_completed_per_expense',
                    ),
                    models.UniqueConstraint(
                        fields=['fixed_expense_period'],
                        condition=models.Q(status='completed', fixed_expense_period__isnull=False),
                        name='payment_one_completed_per_fep',
                    ),
                ],
            },
        ),
    ]

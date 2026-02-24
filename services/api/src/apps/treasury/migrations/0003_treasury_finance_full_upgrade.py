"""
Migration: Full finance module upgrade
- TreasurySettings: add card/other/income/expense/payroll account mappings
- FixedExpense: add category FK + extended frequencies (WEEKLY, QUARTERLY, YEARLY)
- Budget: new model for monthly spending limits by category
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('treasury', '0002_alter_account_opening_balance_date_fixedexpense_and_more'),
    ]

    operations = [
        # ── TreasurySettings new FK fields ──────────────────────────────────
        migrations.AddField(
            model_name='treasurysettings',
            name='default_card_account',
            field=models.ForeignKey(
                blank=True,
                help_text='Cuenta destino para pagos con tarjeta',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='treasury.account',
            ),
        ),
        migrations.AddField(
            model_name='treasurysettings',
            name='default_other_account',
            field=models.ForeignKey(
                blank=True,
                help_text='Cuenta destino para otros medios de pago',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='treasury.account',
            ),
        ),
        migrations.AddField(
            model_name='treasurysettings',
            name='default_income_account',
            field=models.ForeignKey(
                blank=True,
                help_text='Cuenta por defecto para ingresos manuales',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='treasury.account',
            ),
        ),
        migrations.AddField(
            model_name='treasurysettings',
            name='default_expense_account',
            field=models.ForeignKey(
                blank=True,
                help_text='Cuenta por defecto para egresos manuales',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='treasury.account',
            ),
        ),
        migrations.AddField(
            model_name='treasurysettings',
            name='default_payroll_account',
            field=models.ForeignKey(
                blank=True,
                help_text='Cuenta por defecto para sueldos',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='treasury.account',
            ),
        ),

        # ── FixedExpense: category FK ────────────────────────────────────────
        migrations.AddField(
            model_name='fixedexpense',
            name='category',
            field=models.ForeignKey(
                blank=True,
                help_text='Categoría para agrupación',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='fixed_expenses',
                to='treasury.transactioncategory',
            ),
        ),

        # ── FixedExpense: extend frequency choices ───────────────────────────
        migrations.AlterField(
            model_name='fixedexpense',
            name='frequency',
            field=models.CharField(
                choices=[
                    ('weekly', 'Semanal'),
                    ('monthly', 'Mensual'),
                    ('quarterly', 'Trimestral'),
                    ('yearly', 'Anual'),
                ],
                default='monthly',
                max_length=20,
            ),
        ),

        # ── Budget model ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Budget',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveSmallIntegerField()),
                ('month', models.PositiveSmallIntegerField(help_text='Mes (1-12)')),
                ('limit_amount', models.DecimalField(decimal_places=4, max_digits=19)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'business',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='treasury_budgets',
                        to='business.business',
                    ),
                ),
                (
                    'category',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='budgets',
                        to='treasury.transactioncategory',
                    ),
                ),
            ],
            options={
                'ordering': ['-year', '-month'],
                'unique_together': {('business', 'year', 'month', 'category')},
            },
        ),

        # ── Performance indexes ───────────────────────────────────────────────
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['business', 'occurred_at'], name='treasury_txn_biz_date_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['business', 'direction', 'status'], name='treasury_txn_dir_status_idx'),
        ),
        migrations.AddIndex(
            model_name='transaction',
            index=models.Index(fields=['business', 'account', 'occurred_at'], name='treasury_txn_acct_date_idx'),
        ),
        migrations.AddIndex(
            model_name='fixedexpenseperiod',
            index=models.Index(fields=['fixed_expense', 'period'], name='treasury_fep_fe_period_idx'),
        ),
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(fields=['business', 'status', 'due_date'], name='treasury_exp_status_due_idx'),
        ),
        # ── PayrollPayment: add status field ────────────────────────────────
        migrations.AddField(
            model_name='payrollpayment',
            name='status',
            field=models.CharField(
                choices=[('paid', 'Paid'), ('reverted', 'Reverted')],
                default='paid',
                max_length=20,
            ),
        ),
    ]

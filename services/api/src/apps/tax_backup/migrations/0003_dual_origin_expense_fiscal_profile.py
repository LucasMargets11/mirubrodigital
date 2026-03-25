"""
Migration: ExpenseFiscalProfile dual origin support.

Schema changes:
- Make expense nullable (was required OneToOne)
- Add fixed_expense_period OneToOneField (nullable)
- Add source_type CharField
- Add CheckConstraint: exactly one source FK must be non-null
- Add conditional UniqueConstraints for each FK
- Add index on (business, source_type)
- Remove old unique constraint on expense (replaced by conditional one)

Data migration:
- Backfill source_type='expense' for all existing profiles
"""
import django.db.models.deletion
from django.db import migrations, models


def backfill_source_type(apps, schema_editor):
    """Set source_type='expense' for all existing profiles."""
    ExpenseFiscalProfile = apps.get_model('tax_backup', 'ExpenseFiscalProfile')
    ExpenseFiscalProfile.objects.filter(source_type='').update(source_type='expense')


class Migration(migrations.Migration):

    dependencies = [
        ('tax_backup', '0002_duplicate_flag_canonical_pair'),
        ('treasury', '0005_expense_auto_source_fields'),
    ]

    operations = [
        # 1. Make expense nullable
        migrations.AlterField(
            model_name='expensefiscalprofile',
            name='expense',
            field=models.OneToOneField(
                blank=True,
                help_text='Gasto puntual de treasury (mutuamente excluyente con fixed_expense_period)',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='fiscal_profile',
                to='treasury.expense',
            ),
        ),
        # 2. Add fixed_expense_period FK
        migrations.AddField(
            model_name='expensefiscalprofile',
            name='fixed_expense_period',
            field=models.OneToOneField(
                blank=True,
                help_text='Período de gasto fijo de treasury (mutuamente excluyente con expense)',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='fiscal_profile',
                to='treasury.fixedexpenseperiod',
            ),
        ),
        # 3. Add source_type (allow blank temporarily for backfill)
        migrations.AddField(
            model_name='expensefiscalprofile',
            name='source_type',
            field=models.CharField(
                choices=[('expense', 'Gasto puntual'), ('fixed_expense_period', 'Período de gasto fijo')],
                default='expense',
                help_text='Tipo de origen del perfil fiscal',
                max_length=30,
            ),
            preserve_default=False,
        ),
        # 4. Backfill source_type for existing rows
        migrations.RunPython(backfill_source_type, migrations.RunPython.noop),
        # 5. Remove old unconditional unique constraint on expense
        migrations.RemoveConstraint(
            model_name='expensefiscalprofile',
            name='tb_one_fiscal_profile_per_expense',
        ),
        # 6. Add conditional unique constraint for expense
        migrations.AddConstraint(
            model_name='expensefiscalprofile',
            constraint=models.UniqueConstraint(
                fields=('expense',),
                condition=models.Q(expense__isnull=False),
                name='tb_one_fiscal_profile_per_expense',
            ),
        ),
        # 7. Add conditional unique constraint for fixed_expense_period
        migrations.AddConstraint(
            model_name='expensefiscalprofile',
            constraint=models.UniqueConstraint(
                fields=('fixed_expense_period',),
                condition=models.Q(fixed_expense_period__isnull=False),
                name='tb_one_fiscal_profile_per_fep',
            ),
        ),
        # 8. Add exactly-one-source check constraint
        migrations.AddConstraint(
            model_name='expensefiscalprofile',
            constraint=models.CheckConstraint(
                check=(
                    models.Q(expense__isnull=False, fixed_expense_period__isnull=True)
                    | models.Q(expense__isnull=True, fixed_expense_period__isnull=False)
                ),
                name='tb_fp_exactly_one_source',
            ),
        ),
        # 9. Add index on (business, source_type)
        migrations.AddIndex(
            model_name='expensefiscalprofile',
            index=models.Index(
                fields=['business', 'source_type'],
                name='tb_fp_biz_source_idx',
            ),
        ),
    ]

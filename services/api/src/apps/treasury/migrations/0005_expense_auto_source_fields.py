"""
Migration: add source_type, source_id, is_auto_generated to Expense
and a unique constraint that prevents duplicate auto-generated expenses
for the same (business, source_type, source_id) triplet.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('treasury', '0004_remove_expense_treasury_exp_status_due_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='source_type',
            field=models.CharField(
                blank=True,
                help_text="Tipo de origen del gasto automático (ej: 'stock_replenishment')",
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='expense',
            name='source_id',
            field=models.CharField(
                blank=True,
                help_text='ID del registro de origen (UUID o entero como string)',
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='expense',
            name='is_auto_generated',
            field=models.BooleanField(
                default=False,
                help_text='True cuando fue creado automáticamente por el sistema (ej. reposición de stock)',
            ),
        ),
        migrations.AddConstraint(
            model_name='expense',
            constraint=models.UniqueConstraint(
                condition=models.Q(source_type__isnull=False),
                fields=['business', 'source_type', 'source_id'],
                name='expense_unique_auto_source',
            ),
        ),
    ]

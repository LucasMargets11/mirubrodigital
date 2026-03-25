"""
Sprint 4 — Fiscal validation fields on ExpenseFiscalProfile.

Adds: fiscal_status, review_required, missing_fields, validation_issues,
      evaluated_at, evaluation_source.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tax_backup', '0003_dual_origin_expense_fiscal_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='expensefiscalprofile',
            name='fiscal_status',
            field=models.CharField(
                choices=[
                    ('sin_comprobante', 'Sin comprobante'),
                    ('incompleto', 'Incompleto'),
                    ('requiere_revision', 'Requiere revisión'),
                    ('valido_con_observaciones', 'Válido con observaciones'),
                    ('valido', 'Válido'),
                ],
                db_index=True,
                default='sin_comprobante',
                help_text='Estado de validación fiscal/documental (Sprint 4)',
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name='expensefiscalprofile',
            name='review_required',
            field=models.BooleanField(
                default=False,
                help_text='Flag rápido para UI: indica si necesita atención del usuario',
            ),
        ),
        migrations.AddField(
            model_name='expensefiscalprofile',
            name='missing_fields',
            field=models.JSONField(
                blank=True,
                help_text='Lista de campos faltantes del comprobante ["issuer_tax_id", ...]',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='expensefiscalprofile',
            name='validation_issues',
            field=models.JSONField(
                blank=True,
                help_text='Lista de observaciones/issues [{"code": "...", "message": "..."}]',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='expensefiscalprofile',
            name='evaluated_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Timestamp de última evaluación fiscal',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='expensefiscalprofile',
            name='evaluation_source',
            field=models.CharField(
                blank=True,
                choices=[
                    ('manual', 'Manual'),
                    ('extracted', 'Extracción automática'),
                    ('mixed', 'Manual + Extracción'),
                ],
                help_text='Fuente de datos usada en la última evaluación',
                max_length=15,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name='expensefiscalprofile',
            index=models.Index(
                fields=['business', 'fiscal_status'],
                name='tb_fp_biz_fstatus_idx',
            ),
        ),
    ]

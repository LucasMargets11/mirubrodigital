"""
Sprint 5 — Add processing_error field to FiscalDocument.

Tracks why extraction failed (distinguishes 'no data found' from 'technical error').
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tax_backup', '0004_fiscal_validation_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='fiscaldocument',
            name='processing_error',
            field=models.TextField(
                blank=True,
                help_text='Detalle del error si el procesamiento falló (distingue "sin datos" de "fallo técnico")',
                null=True,
            ),
        ),
    ]

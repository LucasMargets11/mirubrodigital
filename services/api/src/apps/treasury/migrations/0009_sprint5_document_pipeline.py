"""
Sprint 5: Document processing pipeline enhancements.

Adds:
- processed_with_warnings status
- upload_source field
- pipeline_version field
- processing_attempts counter
- error_trace structured JSON field
- Widens status max_length to 30 for processed_with_warnings
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('treasury', '0008_document_processing_fields'),
    ]

    operations = [
        # 1. Widen status max_length (new choice 'processed_with_warnings' = 24 chars)
        migrations.AlterField(
            model_name='expensedocument',
            name='status',
            field=models.CharField(
                choices=[
                    ('uploaded', 'Subido'),
                    ('archived', 'Archivado'),
                    ('queued', 'En cola'),
                    ('processing', 'Procesando'),
                    ('processed', 'Procesado'),
                    ('processed_with_warnings', 'Procesado con advertencias'),
                    ('failed', 'Fallido'),
                ],
                default='uploaded',
                max_length=30,
            ),
        ),

        # 2. Upload source
        migrations.AddField(
            model_name='expensedocument',
            name='upload_source',
            field=models.CharField(
                choices=[
                    ('web', 'Web'),
                    ('mobile', 'Móvil'),
                    ('api', 'API'),
                    ('bulk', 'Carga masiva'),
                ],
                default='web',
                help_text='Origen de la subida (web, mobile, api, bulk).',
                max_length=20,
            ),
        ),

        # 3. Pipeline version
        migrations.AddField(
            model_name='expensedocument',
            name='pipeline_version',
            field=models.CharField(
                default='1.0',
                help_text='Versión del pipeline que procesó el documento.',
                max_length=20,
            ),
        ),

        # 4. Processing attempts counter
        migrations.AddField(
            model_name='expensedocument',
            name='processing_attempts',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='Cantidad de intentos de procesamiento realizados.',
            ),
        ),

        # 5. Structured error trace
        migrations.AddField(
            model_name='expensedocument',
            name='error_trace',
            field=models.JSONField(
                blank=True,
                null=True,
                help_text='Traza estructurada de errores: [{step, error, timestamp}, ...]',
            ),
        ),
    ]

# Generated migration for DocumentSeries model

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0008_businessbillingprofile_businessbranding'),
        ('invoices', '0002_rename_invoices_invoice_busines_2b3f52_idx_invoices_in_busines_b10fdc_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentSeries',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('document_type', models.CharField(
                    choices=[
                        ('invoice', 'Factura'),
                        ('quote', 'Presupuesto'),
                        ('receipt', 'Recibo'),
                        ('credit_note', 'Nota de Crédito'),
                        ('debit_note', 'Nota de Débito'),
                        ('delivery_note', 'Remito'),
                    ],
                    help_text='Tipo de documento',
                    max_length=20,
                )),
                ('letter', models.CharField(
                    blank=True,
                    choices=[
                        ('A', 'A'),
                        ('B', 'B'),
                        ('C', 'C'),
                        ('E', 'E'),
                        ('M', 'M'),
                        ('X', 'X'),
                        ('P', 'P (Presupuestos)'),
                    ],
                    help_text='Letra del comprobante',
                    max_length=1,
                )),
                ('prefix', models.CharField(
                    blank=True,
                    help_text='Prefijo opcional (ej: FAC, PRE, REC)',
                    max_length=10,
                )),
                ('suffix', models.CharField(
                    blank=True,
                    help_text='Sufijo opcional',
                    max_length=10,
                )),
                ('point_of_sale', models.PositiveIntegerField(
                    default=1,
                    help_text='Punto de venta (1-9999)',
                )),
                ('next_number', models.PositiveIntegerField(
                    default=1,
                    help_text='Próximo número a asignar',
                )),
                ('is_active', models.BooleanField(
                    default=True,
                    help_text='Si está activa para emitir nuevos documentos',
                )),
                ('is_default', models.BooleanField(
                    default=False,
                    help_text='Si es la serie predeterminada para este tipo de documento',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='document_series',
                    to='business.business',
                )),
                ('branch', models.ForeignKey(
                    blank=True,
                    help_text='Sucursal específica (opcional)',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='branch_document_series',
                    to='business.business',
                )),
            ],
            options={
                'db_table': 'document_series',
                'ordering': ['document_type', 'letter', 'point_of_sale'],
            },
        ),
        migrations.AddConstraint(
            model_name='documentseries',
            constraint=models.UniqueConstraint(
                fields=('business', 'document_type', 'letter', 'point_of_sale'),
                name='unique_business_doc_type_letter_pv'
            ),
        ),
        migrations.AddIndex(
            model_name='documentseries',
            index=models.Index(
                fields=['business', 'document_type', 'is_default'],
                name='doc_series_business_type_default_idx'
            ),
        ),
    ]

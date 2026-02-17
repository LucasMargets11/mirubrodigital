# Data migration: Migrate InvoiceSeries and QuoteSequence to DocumentSeries

from django.db import migrations


def migrate_existing_series_to_document_series(apps, schema_editor):
    """
    Migrar series existentes de InvoiceSeries y QuoteSequence al nuevo modelo DocumentSeries.
    """
    DocumentSeries = apps.get_model('invoices', 'DocumentSeries')
    InvoiceSeries = apps.get_model('invoices', 'InvoiceSeries')
    QuoteSequence = apps.get_model('sales', 'QuoteSequence')
    
    # Migrar InvoiceSeries → DocumentSeries (como invoices)
    for invoice_series in InvoiceSeries.objects.all():
        # Inferir letter desde el código si está disponible
        # Formato típico: "001-A" o "FAC-A-001"
        letter = 'X'  # Default
        code_parts = invoice_series.code.split('-')
        for part in code_parts:
            if part in ['A', 'B', 'C', 'E', 'M', 'X']:
                letter = part
                break
        
        # Crear DocumentSeries equivalente
        DocumentSeries.objects.get_or_create(
            business=invoice_series.business,
            document_type='invoice',
            letter=letter,
            point_of_sale=1,  # Default point of sale
            defaults={
                'prefix': invoice_series.prefix or '',
                'next_number': invoice_series.next_number,
                'is_active': invoice_series.is_active,
                'is_default': True,  # Primera serie migrada será default
            }
        )
    
    # Migrar QuoteSequence → DocumentSeries (como quotes)
    for quote_seq in QuoteSequence.objects.all():
        DocumentSeries.objects.get_or_create(
            business=quote_seq.business,
            document_type='quote',
            letter='P',  # Presupuestos usan letra P
            point_of_sale=1,
            defaults={
                'prefix': 'PRE',
                'next_number': quote_seq.last_number + 1,  # last_number es el último usado, next es el siguiente
                'is_active': True,
                'is_default': True,
            }
        )


def reverse_migration(apps, schema_editor):
    """
    Reverse: No podemos revertir automáticamente porque eliminaría datos.
    Se deja como no-op para evitar pérdida de datos.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0003_documentseries'),
        ('sales', '0005_quotesequence_quote_quoteitem_and_more'),
    ]

    operations = [
        migrations.RunPython(
            migrate_existing_series_to_document_series,
            reverse_migration,
        ),
    ]

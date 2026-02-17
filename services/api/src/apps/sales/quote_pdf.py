"""Generador de PDF para presupuestos usando ReportLab."""
from io import BytesIO
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

from .models import Quote
from apps.business.services import get_business_document_config


def format_money_ar(value) -> str:
    """
    Formatea un monto en formato argentino:
    - Sin decimales si es entero (ej: 6975.00 → "6.975")
    - Con decimales si tiene centavos (ej: 6975.50 → "6.975,50")
    - Separador de miles: punto (.)
    - Separador de decimales: coma (,)
    """
    if value is None:
        value = Decimal('0')
    
    # Convertir a Decimal para precisión
    dec_value = Decimal(str(value))
    
    # Verificar si es entero (sin decimales reales)
    is_integer = dec_value == dec_value.quantize(Decimal('1'))
    
    if is_integer:
        # Formato sin decimales
        int_part = int(dec_value)
        # Formatear con separador de miles
        formatted = f"{int_part:,}".replace(',', '.')
    else:
        # Formato con 2 decimales
        int_part = int(dec_value)
        cents = int((dec_value - int_part) * 100)
        # Formatear parte entera con separadores de miles
        int_formatted = f"{int_part:,}".replace(',', '.')
        formatted = f"{int_formatted},{cents:02d}"
    
    return formatted


def format_quantity_ar(value) -> str:
    """
    Formatea cantidades de manera inteligente:
    - Si es entero: sin decimales (ej: 1.00 → "1")
    - Si tiene decimales: con hasta 2 decimales (ej: 1.50 → "1,5")
    """
    if value is None:
        return "0"
    
    dec_value = Decimal(str(value))
    is_integer = dec_value == dec_value.quantize(Decimal('1'))
    
    if is_integer:
        return str(int(dec_value))
    else:
        # Mostrar con decimales, eliminando ceros innecesarios
        formatted = f"{float(dec_value):.2f}".replace('.', ',')
        # Eliminar ceros finales después de la coma
        if ',' in formatted:
            formatted = formatted.rstrip('0').rstrip(',')
        return formatted


def build_quote_pdf(quote: Quote) -> bytes:
    """
    Genera un PDF tipo factura para el presupuesto.
    Retorna bytes que pueden servirse como FileResponse.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch
    )

    # Estilos
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=12,
        alignment=TA_CENTER
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#475569'),
        spaceAfter=6
    )
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#1e293b')
    )
    small_style = ParagraphStyle(
        'CustomSmall',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#64748b')
    )

    # Construir contenido
    story = []

    # Header: Título y número
    story.append(Paragraph("PRESUPUESTO", title_style))
    story.append(Paragraph(f"<b>Número:</b> {quote.number}", normal_style))
    story.append(Paragraph(
        f"<b>Fecha:</b> {quote.created_at.strftime('%d/%m/%Y')}",
        normal_style
    ))
    if quote.valid_until:
        story.append(Paragraph(
            f"<b>Válido hasta:</b> {quote.valid_until.strftime('%d/%m/%Y')}",
            normal_style
        ))
    story.append(Spacer(1, 0.3 * inch))

    # Obtener configuración centralizada del negocio
    config = get_business_document_config(quote.business)
    issuer = config.get_issuer_data()
    
    # Información del negocio (emisor)
    business_name = issuer.get('legal_name') or quote.business.name
    story.append(Paragraph(f"<b>{business_name}</b>", heading_style))
    
    # Mostrar datos fiscales si existen
    if issuer.get('tax_id_display'):
        story.append(Paragraph(issuer['tax_id_display'], small_style))
    if issuer.get('vat_condition_display'):
        story.append(Paragraph(f"IVA: {issuer['vat_condition_display']}", small_style))
    if issuer.get('commercial_address'):
        story.append(Paragraph(issuer['commercial_address'], small_style))
    if issuer.get('phone'):
        story.append(Paragraph(f"Tel: {issuer['phone']}", small_style))
    if issuer.get('email'):
        story.append(Paragraph(f"Email: {issuer['email']}", small_style))
    
    story.append(Spacer(1, 0.2 * inch))

    # Información del cliente
    story.append(Paragraph("<b>Cliente</b>", heading_style))
    if quote.customer:
        customer_name = quote.customer.name
    else:
        customer_name = quote.customer_name or "Cliente"
    story.append(Paragraph(customer_name, normal_style))
    
    if quote.customer_email:
        story.append(Paragraph(f"Email: {quote.customer_email}", small_style))
    if quote.customer_phone:
        story.append(Paragraph(f"Tel: {quote.customer_phone}", small_style))
    
    story.append(Spacer(1, 0.3 * inch))

    # Tabla de items
    story.append(Paragraph("<b>Detalle</b>", heading_style))
    story.append(Spacer(1, 0.1 * inch))

    # Headers de la tabla
    table_data = [
        ['Producto/Descripción', 'Cant.', 'Precio Unit.', 'Desc.', 'Total']
    ]

    items = quote.items.all()
    for item in items:
        table_data.append([
            item.name_snapshot,
            format_quantity_ar(item.quantity),
            f"$ {format_money_ar(item.unit_price)}",
            f"$ {format_money_ar(item.discount)}" if item.discount > 0 else "-",
            f"$ {format_money_ar(item.total_line)}"
        ])

    # Crear tabla
    item_table = Table(table_data, colWidths=[3.5 * inch, 0.8 * inch, 1 * inch, 0.8 * inch, 1 * inch])
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 0.3 * inch))

    # Totales
    totals_data = []
    if quote.subtotal:
        totals_data.append(['Subtotal:', f"$ {format_money_ar(quote.subtotal)}"])
    if quote.discount_total and quote.discount_total > 0:
        totals_data.append(['Descuentos:', f"-$ {format_money_ar(quote.discount_total)}"])
    if quote.tax_total and quote.tax_total > 0:
        totals_data.append(['Impuestos:', f"$ {format_money_ar(quote.tax_total)}"])
    
    # TOTAL en negrita usando Paragraph
    total_label = Paragraph('<b>TOTAL:</b>', normal_style)
    total_value = Paragraph(f'<b>$ {format_money_ar(quote.total)}</b>', normal_style)
    totals_data.append([total_label, total_value])

    totals_table = Table(totals_data, colWidths=[5 * inch, 1.5 * inch])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -2), 4),
        ('TOPPADDING', (0, 0), (-1, -2), 4),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
        ('TOPPADDING', (0, -1), (-1, -1), 8),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1e293b')),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 0.3 * inch))

    # Notas y términos
    if quote.notes:
        story.append(Paragraph("<b>Notas:</b>", heading_style))
        story.append(Paragraph(quote.notes, small_style))
        story.append(Spacer(1, 0.1 * inch))

    if quote.terms:
        story.append(Paragraph("<b>Términos y condiciones:</b>", heading_style))
        story.append(Paragraph(quote.terms, small_style))
        story.append(Spacer(1, 0.1 * inch))

    # Pie
    story.append(Spacer(1, 0.2 * inch))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#94a3b8'),
        alignment=TA_CENTER
    )
    story.append(Paragraph("Gracias por su consulta", footer_style))

    # Generar PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

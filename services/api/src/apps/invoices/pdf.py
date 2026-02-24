"""
Generación de PDF para facturas.

Renderiza un PDF con:
- Logo del negocio en el header (si está configurado)
- Bloque completo de datos del emisor (razón social, CUIT, IVA, domicilios, contacto)
- Datos del cliente
- Tabla de ítems
- Totales

Todos los accesos a campos del perfil son seguros (getattr/fallback)
para no romper el PDF si falta algún dato opcional.
"""
from __future__ import annotations

import logging
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from .models import Invoice
from apps.business.services import get_business_document_config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Tamaños del logo en header
# ──────────────────────────────────────────────
LOGO_HEADER_MAX_H = 28 * mm
LOGO_HEADER_MAX_W = 60 * mm


def _draw_logo(pdf: canvas.Canvas, image_field, x: float, y_top: float) -> float:
    """
    Intenta renderizar el logo header en el canvas y devuelve la altura ocupada.

    - SVG: no soportado por ReportLab → se omite, no rompe el PDF.
    - Error de E/S o campo vacío: se omite silenciosamente.
    - Aspect ratio siempre preservado.

    Returns:
        Altura real dibujada en puntos (0 si no se dibujó nada).
    """
    if not image_field:
        return 0.0
    try:
        name = getattr(image_field, 'name', '') or ''
        if not name:
            return 0.0
        if name.lower().endswith('.svg'):
            logger.warning('Logo SVG no soportado en PDF (%s); se omite el logo.', name)
            return 0.0

        file_path = image_field.path  # puede lanzar SuspiciousFileOperation si vacío

        from reportlab.lib.utils import ImageReader
        img_reader = ImageReader(file_path)
        img_w, img_h = img_reader.getSize()

        scale_w = LOGO_HEADER_MAX_W / img_w
        scale_h = LOGO_HEADER_MAX_H / img_h
        scale = min(scale_w, scale_h, 1.0)
        draw_w = img_w * scale
        draw_h = img_h * scale

        pdf.drawImage(file_path, x, y_top - draw_h,
                      width=draw_w, height=draw_h,
                      preserveAspectRatio=True, mask='auto')
        return draw_h
    except Exception:
        logger.warning('No se pudo renderizar el logo en el PDF; se continúa sin imagen.',
                       exc_info=True)
        return 0.0


def render_invoice_pdf(invoice: Invoice) -> bytes:
    """
    Genera los bytes PDF de una factura usando los datos fiscales / branding del negocio.

    Returns:
        bytes del PDF generado.
    """
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin = 18 * mm
    current_y = height - margin

    # ── Config centralizada ──────────────────────────────────────────────
    config = get_business_document_config(invoice.business)
    issuer = config.get_issuer_data()
    branding = config.get_invoice_branding()

    accent_hex = branding.get('accent_color') or '#0f172a'
    try:
        accent_color = colors.HexColor(accent_hex)
    except Exception:
        accent_color = colors.HexColor('#0f172a')

    # ── Logo header ──────────────────────────────────────────────────────
    logo_field = branding.get('logo_header')
    logo_height = _draw_logo(pdf, logo_field, margin, current_y)

    legal_name = issuer.get('legal_name') or invoice.business.name
    if logo_height > 0:
        # Título a la derecha del logo
        pdf.setFont('Helvetica-Bold', 15)
        pdf.setFillColor(accent_color)
        pdf.drawString(margin + LOGO_HEADER_MAX_W + 4 * mm, current_y - 18, legal_name)
        pdf.setFillColor(colors.black)
    else:
        # Sin logo: sólo texto
        pdf.setFont('Helvetica-Bold', 16)
        pdf.setFillColor(accent_color)
        pdf.drawString(margin, current_y - 16, legal_name)
        pdf.setFillColor(colors.black)
        logo_height = 16

    header_consumed = max(logo_height, 20)
    current_y -= header_consumed + 6 * mm

    # ── Número y fecha ───────────────────────────────────────────────────
    pdf.setFont('Helvetica-Bold', 12)
    pdf.setFillColor(accent_color)
    pdf.drawString(margin, current_y, f'Factura  {invoice.full_number}')
    pdf.setFillColor(colors.black)
    pdf.setFont('Helvetica', 10)
    pdf.drawString(margin, current_y - 14,
                   f"Fecha: {invoice.issued_at.strftime('%d/%m/%Y %H:%M')} hs")
    current_y -= 30

    # Separador
    pdf.setStrokeColor(colors.HexColor('#e2e8f0'))
    pdf.line(margin, current_y, width - margin, current_y)
    current_y -= 10

    # ── Bloque Emisor ────────────────────────────────────────────────────
    pdf.setFont('Helvetica-Bold', 11)
    pdf.setFillColor(accent_color)
    pdf.drawString(margin, current_y, 'Emisor')
    pdf.setFillColor(colors.black)
    current_y -= 15

    label_indent = margin + 2 * mm
    value_x = label_indent + 42 * mm

    def _issuer_line(label: str, value: str) -> None:
        nonlocal current_y
        if not (value or '').strip():
            return
        pdf.setFont('Helvetica-Bold', 9)
        pdf.drawString(label_indent, current_y, f'{label}:')
        pdf.setFont('Helvetica', 9)
        pdf.drawString(value_x, current_y, value)
        current_y -= 12

    _issuer_line('Razón Social', issuer.get('legal_name') or invoice.business.name)
    trade = issuer.get('trade_name') or ''
    if trade and trade != (issuer.get('legal_name') or ''):
        _issuer_line('Nombre Fantasía', trade)
    _issuer_line('CUIT / ID', issuer.get('tax_id_display') or issuer.get('tax_id') or '')
    _issuer_line('Cond. IVA', issuer.get('vat_condition_display') or '')
    _issuer_line('Ing. Brutos', issuer.get('iibb') or '')

    fiscal_addr = issuer.get('legal_address') or issuer.get('fiscal_address') or ''
    _issuer_line('Dom. Fiscal', fiscal_addr)

    commercial_addr = issuer.get('commercial_address') or ''
    if commercial_addr and commercial_addr != fiscal_addr:
        _issuer_line('Dom. Comercial', commercial_addr)

    location_parts = [p for p in [
        issuer.get('city', ''),
        issuer.get('state_province', ''),
        issuer.get('postal_code', ''),
    ] if p]
    country = issuer.get('country', '')
    if country and country not in ('AR', 'Argentina'):
        location_parts.append(country)
    location_str = ' · '.join(location_parts)
    _issuer_line('Localidad', location_str)

    _issuer_line('Teléfono', issuer.get('phone') or '')
    _issuer_line('Email', issuer.get('email') or '')
    _issuer_line('Sitio web', issuer.get('website') or '')

    current_y -= 4

    # Separador
    pdf.setStrokeColor(colors.HexColor('#e2e8f0'))
    pdf.line(margin, current_y, width - margin, current_y)
    current_y -= 10

    # ── Bloque Cliente ───────────────────────────────────────────────────
    pdf.setFont('Helvetica-Bold', 11)
    pdf.setFillColor(accent_color)
    pdf.drawString(margin, current_y, 'Cliente')
    pdf.setFillColor(colors.black)
    current_y -= 15

    def _client_line(label: str, value: str) -> None:
        nonlocal current_y
        if not (value or '').strip():
            return
        pdf.setFont('Helvetica-Bold', 9)
        pdf.drawString(label_indent, current_y, f'{label}:')
        pdf.setFont('Helvetica', 9)
        pdf.drawString(value_x, current_y, value)
        current_y -= 12

    _client_line('Nombre', invoice.customer_name or 'Consumidor final')
    _client_line('Documento', invoice.customer_tax_id or '')
    _client_line('Dirección', invoice.customer_address or '')

    current_y -= 4

    # Separador
    pdf.setStrokeColor(colors.HexColor('#e2e8f0'))
    pdf.line(margin, current_y, width - margin, current_y)
    current_y -= 12

    # ── Tabla de ítems ───────────────────────────────────────────────────
    table_data = [['Producto', 'Cant.', 'Precio unit.', 'Total']]
    for item in invoice.sale.items.all():
        table_data.append([
            item.product_name_snapshot,
            str(item.quantity),
            f"${item.unit_price}",
            f"${item.line_total}",
        ])

    col_widths = [85 * mm, 20 * mm, 32 * mm, 32 * mm]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), accent_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cbd5e1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])
    )
    table.wrapOn(pdf, width - 2 * margin, height)
    table_h = table._height  # type: ignore[attr-defined]
    table.drawOn(pdf, margin, current_y - table_h)
    current_y -= table_h + 14

    # ── Totales ──────────────────────────────────────────────────────────
    pdf.setFont('Helvetica', 10)
    pdf.setFillColor(colors.black)
    pdf.drawRightString(width - margin, current_y, f"Subtotal: ${invoice.subtotal}")
    pdf.drawRightString(width - margin, current_y - 14, f"Descuento: ${invoice.discount}")
    pdf.setFont('Helvetica-Bold', 12)
    pdf.setFillColor(accent_color)
    pdf.drawRightString(width - margin, current_y - 30, f"TOTAL: ${invoice.total}")
    pdf.setFillColor(colors.black)

    # ── Pie de página ────────────────────────────────────────────────────
    pdf.setFont('Helvetica-Oblique', 8)
    pdf.setFillColor(colors.HexColor('#94a3b8'))
    pdf.drawString(margin, margin, 'Comprobante no fiscal · Generado con MiRubro')
    pdf.setFillColor(colors.black)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()

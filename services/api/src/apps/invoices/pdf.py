from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from .models import Invoice
from apps.business.services import get_business_document_config

HEADER_STYLE = ParagraphStyle(
  name='Header',
  fontName='Helvetica-Bold',
  fontSize=12,
  leading=14,
  textColor=colors.black,
)

BODY_STYLE = ParagraphStyle(
  name='Body',
  fontName='Helvetica',
  fontSize=10,
  leading=12,
  textColor=colors.black,
)

FOOTER_STYLE = ParagraphStyle(
  name='Footer',
  fontName='Helvetica-Oblique',
  fontSize=9,
  textColor=colors.HexColor('#475569'),
)


def render_invoice_pdf(invoice: Invoice) -> bytes:
  buffer = BytesIO()
  pdf = canvas.Canvas(buffer, pagesize=A4)
  width, height = A4

  margin = 20 * mm
  current_y = height - margin

  # Obtener configuración centralizada del negocio
  config = get_business_document_config(invoice.business)
  issuer = config.get_issuer_data()
  branding = config.get_branding_data()

  # Header con datos del emisor
  pdf.setFont('Helvetica-Bold', 16)
  pdf.drawString(margin, current_y, issuer.get('legal_name') or invoice.business.name)
  pdf.setFont('Helvetica', 10)
  pdf.drawString(margin, current_y - 14, f"Factura {invoice.full_number}")
  pdf.drawString(margin, current_y - 28, f"Fecha: {invoice.issued_at.strftime('%d/%m/%Y %H:%M')} hs")
  current_y -= 50

  # Datos del emisor
  pdf.setFont('Helvetica-Bold', 11)
  pdf.drawString(margin, current_y, 'Emisor')
  pdf.setFont('Helvetica', 10)
  pdf.drawString(margin, current_y - 14, f"Razón Social: {issuer.get('legal_name') or invoice.business.name}")
  pdf.drawString(margin, current_y - 28, issuer.get('tax_id_display') or 'CUIT: —')
  pdf.drawString(margin, current_y - 42, f"IVA: {issuer.get('vat_condition_display') or '—'}")
  if issuer.get('commercial_address'):
    pdf.drawString(margin, current_y - 56, f"Dirección: {issuer['commercial_address']}")
    current_y -= 76
  else:
    current_y -= 58

  # Datos del cliente
  pdf.setFont('Helvetica-Bold', 11)
  pdf.drawString(margin, current_y, 'Cliente')
  pdf.setFont('Helvetica', 10)
  pdf.drawString(margin, current_y - 14, f"Nombre: {invoice.customer_name or 'Consumidor final'}")
  pdf.drawString(margin, current_y - 28, f"Documento: {invoice.customer_tax_id or '—'}")
  if invoice.customer_address:
    pdf.drawString(margin, current_y - 42, f"Dirección: {invoice.customer_address}")
    current_y -= 58
  else:
    current_y -= 44

  table_data = [['Producto', 'Cantidad', 'Precio', 'Total']]
  for item in invoice.sale.items.all():
    table_data.append([
      item.product_name_snapshot,
      f"{item.quantity}",
      f"${item.unit_price}",
      f"${item.line_total}",
    ])

  table = Table(table_data, colWidths=[90 * mm, 25 * mm, 30 * mm, 30 * mm])
  table.setStyle(
    TableStyle(
      [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cbd5f5')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
      ]
    )
  )
  table.wrapOn(pdf, width - 2 * margin, height)
  table_height = table._height  # type: ignore[attr-defined]
  table.drawOn(pdf, margin, current_y - table_height)
  current_y = current_y - table_height - 20

  pdf.setFont('Helvetica', 10)
  pdf.drawRightString(width - margin, current_y, f"Subtotal: ${invoice.subtotal}")
  pdf.drawRightString(width - margin, current_y - 14, f"Descuento: ${invoice.discount}")
  pdf.setFont('Helvetica-Bold', 12)
  pdf.drawRightString(width - margin, current_y - 32, f"Total: ${invoice.total}")
  current_y -= 50

  pdf.setFont('Helvetica-Oblique', 9)
  pdf.setFillColor(colors.HexColor('#0f172a'))
  pdf.drawString(margin, current_y, 'Comprobante no fiscal. Generado desde MiRubro.')

  pdf.showPage()
  pdf.save()
  return buffer.getvalue()

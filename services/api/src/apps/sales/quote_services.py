"""Servicios para la gestión de presupuestos."""
from decimal import Decimal

from django.db import transaction

from .models import Quote, QuoteSequence


def generate_quote_number(business) -> str:
    """
    Genera el siguiente número de presupuesto de forma segura.
    Formato: P-000001
    """
    with transaction.atomic():
        sequence, _ = QuoteSequence.objects.select_for_update().get_or_create(
            business=business,
            defaults={'last_number': 0}
        )
        sequence.last_number += 1
        next_number = sequence.last_number
        sequence.save(update_fields=['last_number'])
        return f"P-{next_number:06d}"


def recalc_quote_totals(quote: Quote) -> None:
    """
    Recalcula los totales de un presupuesto basándose en sus items.
    Actualiza subtotal, discount_total, tax_total y total.
    """
    items = quote.items.all()
    
    # Recalcular total_line de cada item
    for item in items:
        item.total_line = (item.quantity * item.unit_price) - item.discount
        item.save(update_fields=['total_line'])
    
    # Calcular subtotal (suma de qty * unit_price)
    subtotal = sum(
        (item.quantity * item.unit_price) for item in items
    )
    
    # Calcular descuentos totales
    discount_total = sum(item.discount for item in items)
    
    # Por ahora tax_total es 0 (se puede extender en el futuro)
    tax_total = Decimal('0')
    
    # Total final
    total = subtotal - discount_total + tax_total
    
    # Actualizar el presupuesto
    quote.subtotal = subtotal
    quote.discount_total = discount_total
    quote.tax_total = tax_total
    quote.total = total
    quote.save(update_fields=['subtotal', 'discount_total', 'tax_total', 'total'])

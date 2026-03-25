"""
Respaldo Impositivo — Signals

Re-evalúa el tax_status automáticamente cuando se guardan cambios
relevantes en los modelos hijos (FiscalDocument, ExpensePaymentDetail).
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import ExpenseFiscalProfile, FiscalDocument, ExpensePaymentDetail


@receiver(post_save, sender=FiscalDocument)
def fiscal_document_saved(sender, instance, **kwargs):
    """Re-evalúa reglas cuando se crea/modifica un documento."""
    _reevaluate_profile(instance.fiscal_profile_id)


@receiver(post_delete, sender=FiscalDocument)
def fiscal_document_deleted(sender, instance, **kwargs):
    """Re-evalúa reglas cuando se borra un documento."""
    _reevaluate_profile(instance.fiscal_profile_id)


@receiver(post_save, sender=ExpensePaymentDetail)
def payment_detail_saved(sender, instance, **kwargs):
    """Re-evalúa reglas cuando se agrega/modifica un detalle de pago."""
    _reevaluate_profile(instance.fiscal_profile_id)


def _reevaluate_profile(profile_id: int) -> None:
    """Helper compartido: recarga el perfil con docs y ejecuta reglas."""
    from .rules import create_duplicate_flags, evaluate_tax_status
    from .models import TaxStatusLog

    try:
        profile = (
            ExpenseFiscalProfile.objects
            .prefetch_related('documents')
            .get(pk=profile_id)
        )
    except ExpenseFiscalProfile.DoesNotExist:
        return

    result = evaluate_tax_status(profile)
    old_status = profile.tax_status
    if result.status != old_status:
        profile.tax_status = result.status
        profile.review_reason = result.note if result.status == 'a_revisar' else None
        profile.save(update_fields=['tax_status', 'review_reason', 'updated_at'])
        TaxStatusLog.objects.create(
            fiscal_profile=profile,
            previous_status=old_status,
            new_status=result.status,
            rule_code=result.rule_code,
            note=result.note,
        )

    create_duplicate_flags(profile)

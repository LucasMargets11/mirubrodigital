import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from apps.sales.models import Sale
from .models import Transaction, TreasurySettings, Account

logger = logging.getLogger(__name__)


def _resolve_account_for_sale(sale, settings):
    """
    Return an Account for the given sale's payment method.
    Priority:
      1. TreasurySettings mapping for the exact payment method
      2. Fallback: any active account matching the expected type
      3. Last resort: any active cash account
    Returns None if no account found (transaction won't be created).
    """
    pm = sale.payment_method  # 'cash' | 'transfer' | 'card' | 'other'
    business = sale.business

    # 1. Check TreasurySettings configured mapping
    if settings:
        account = settings.get_account_for_payment_method(pm)
        if account and account.is_active:
            return account

    # 2. Type-based fallback
    TYPE_FALLBACK = {
        Sale.PaymentMethod.CASH: Account.Type.CASH,
        Sale.PaymentMethod.TRANSFER: Account.Type.BANK,
        Sale.PaymentMethod.CARD: Account.Type.CARD_FLOAT,
        Sale.PaymentMethod.OTHER: None,
    }
    fallback_type = TYPE_FALLBACK.get(pm)
    if fallback_type:
        account = Account.objects.filter(
            business=business, type=fallback_type, is_active=True
        ).first()
        if account:
            logger.warning(
                "TreasurySettings: No mapped account for payment_method=%s in business %s. "
                "Used fallback account '%s' (type=%s). Configure TreasurySettings to fix this.",
                pm, business.pk, account.name, fallback_type
            )
            return account

    # 3. Last resort: any active cash account
    account = Account.objects.filter(business=business, type=Account.Type.CASH, is_active=True).first()
    if account:
        logger.error(
            "TreasurySettings: No suitable account for payment_method=%s in business %s. "
            "Falling back to first cash account '%s'. Configure TreasurySettings to fix this.",
            pm, business.pk, account.name
        )
    return account


@receiver(post_save, sender=Sale)
def create_transaction_from_sale(sender, instance, created, **kwargs):
    sale = instance
    if sale.status != Sale.Status.COMPLETED:
        return

    # Idempotency: skip if a Transaction already exists for this sale
    if Transaction.objects.filter(reference_type='sale', reference_id=str(sale.id)).exists():
        return

    business = sale.business
    amount = sale.total
    if amount <= 0:
        return

    settings = getattr(business, 'treasury_settings', None)
    account = _resolve_account_for_sale(sale, settings)

    if not account:
        logger.error(
            "Cannot create treasury Transaction for sale %s (business %s): no active account found.",
            sale.id, business.pk
        )
        return

    Transaction.objects.create(
        business=business,
        account=account,
        direction=Transaction.Direction.IN,
        amount=amount,
        occurred_at=sale.created_at or timezone.now(),
        description=f"Venta #{sale.number}",
        reference_type='sale',
        reference_id=str(sale.id),
        created_by=sale.created_by,
    )

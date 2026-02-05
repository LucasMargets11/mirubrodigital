from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from apps.sales.models import Sale
from .models import Transaction, TreasurySettings, Account

@receiver(post_save, sender=Sale)
def create_transaction_from_sale(sender, instance, created, **kwargs):
    sale = instance
    if sale.status != Sale.Status.COMPLETED:
        return

    # Idempotency check
    if Transaction.objects.filter(reference_type='sale', reference_id=str(sale.id)).exists():
        return

    business = sale.business
    amount = sale.total
    if amount <= 0:
        return

    # Resolve Account
    settings = getattr(business, 'treasury_settings', None)
    account = None

    if sale.payment_method == Sale.PaymentMethod.CASH:
        if settings and settings.default_cash_account:
            account = settings.default_cash_account
        else:
            account = Account.objects.filter(business=business, type=Account.Type.CASH, is_active=True).first()
    
    elif sale.payment_method == Sale.PaymentMethod.TRANSFER:
         if settings and settings.default_bank_account:
            account = settings.default_bank_account
         else:
            account = Account.objects.filter(business=business, type=Account.Type.BANK, is_active=True).first()
            
    # Fallback to any cash account if nothing else
    if not account:
        account = Account.objects.filter(business=business, type=Account.Type.CASH, is_active=True).first()

    if not account:
        # Cannot record transaction if no account exists.
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
        created_by=sale.created_by
    )

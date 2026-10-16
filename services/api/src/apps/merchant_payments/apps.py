from django.apps import AppConfig


class MerchantPaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.merchant_payments'
    verbose_name = 'Merchant Payments'

    def ready(self):
        from . import checks  # noqa: F401 — registers the deploy check

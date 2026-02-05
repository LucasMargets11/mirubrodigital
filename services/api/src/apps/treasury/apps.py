from django.apps import AppConfig


class TreasuryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.treasury'

    def ready(self):
        import apps.treasury.signals

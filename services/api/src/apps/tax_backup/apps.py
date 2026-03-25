from django.apps import AppConfig


class TaxBackupConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.tax_backup'
    verbose_name = 'Respaldo Impositivo'

    def ready(self):
        import apps.tax_backup.signals  # noqa: F401

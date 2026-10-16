from django.apps import AppConfig


class LeadsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.leads'
    verbose_name = 'Leads'

    def ready(self):
        from . import checks  # noqa: F401  (registra el deploy guard)

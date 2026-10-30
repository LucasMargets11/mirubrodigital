from django.apps import AppConfig


class AppointmentsConfig(AppConfig):
  default_auto_field = 'django.db.models.BigAutoField'
  name = 'apps.appointments'

  def ready(self):
    from . import checks  # noqa: F401

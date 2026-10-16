from django.core.management.base import BaseCommand

from apps.appointments.services.expiration import expire_due_appointment_holds


class Command(BaseCommand):
  help = 'Marca como `expired` los turnos `pending_payment` cuyo hold ya venció.'

  def handle(self, *args, **options):
    count = expire_due_appointment_holds()
    self.stdout.write(self.style.SUCCESS(f'{count} turno(s) marcado(s) como expired.'))

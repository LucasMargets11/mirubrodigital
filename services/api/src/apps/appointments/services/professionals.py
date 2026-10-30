"""Explicit professional mutations; model.save remains the quota backstop."""
from django.db import transaction

from apps.business.models import Business

from ..models import AppointmentProfessional


@transaction.atomic
def create_professional(*, business, **data):
  Business.objects.select_for_update().get(pk=business.pk)
  services = data.pop('services', None)
  professional = AppointmentProfessional.objects.create(business=business, **data)
  if services is not None:
    professional.services.set(services)
  return professional


@transaction.atomic
def update_professional(*, business, professional_id, **changes):
  Business.objects.select_for_update().get(pk=business.pk)
  professional = AppointmentProfessional.objects.select_for_update().get(
    business=business, pk=professional_id,
  )
  services = changes.pop('services', None)
  for field, value in changes.items():
    setattr(professional, field, value)
  professional.save()
  if services is not None:
    professional.services.set(services)
  return professional


def set_professional_active(*, business, professional_id, is_active):
  return update_professional(
    business=business, professional_id=professional_id, is_active=is_active,
  )

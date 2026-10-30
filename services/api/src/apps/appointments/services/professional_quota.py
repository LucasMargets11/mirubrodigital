"""Quota calculation and atomic enforcement for active Turnos professionals."""
from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.business.models import Business, BusinessPlan

from ..models import AppointmentProfessional


class ProfessionalQuotaExceeded(Exception):
  def __init__(self, *, active_count: int, limit: int):
    self.active_count = active_count
    self.limit = limit
    super().__init__(
      f'Límite de profesionales activos alcanzado ({active_count}/{limit}). '
      'Ampliá el plan o contratá profesionales adicionales.'
    )


class ProfessionalQuotaUnavailable(Exception):
  pass


@dataclass(frozen=True)
class ProfessionalQuotaState:
  active_count: int
  effective_limit: int
  over_limit: bool


def _effective_limit(config) -> int:
  return getattr(config, 'effective_professional_limit', config.included_professionals)


def _appointments_config(business):
  from apps.billing.appointments_plans import get_appointments_plan_config
  from apps.billing.runtime import resolve_subscription

  resolved = resolve_subscription(business, service_type='appointments')
  if resolved.source == 'v2':
    from apps.billing.models import SubscriptionV2

    subscription = resolved.subscription_v2
    if (
      subscription is None
      or subscription.status in (SubscriptionV2.Status.SUSPENDED, SubscriptionV2.Status.CANCELED)
      or not resolved.access_granted
    ):
      raise ProfessionalQuotaUnavailable('La suscripción de Turnos no permite administrar profesionales.')
    from apps.billing.services.appointments import resolve_appointments_subscription_config

    try:
      return resolve_appointments_subscription_config(subscription)
    except ValidationError as exc:
      raise ProfessionalQuotaUnavailable('La configuración comercial de Turnos no es válida.') from exc

  if resolved.source == 'legacy' and resolved.legacy_sub is not None:
    if resolved.legacy_sub.service != 'appointments':
      raise ProfessionalQuotaUnavailable('No hay una suscripción de Turnos activa.')
    legacy_plan = resolved.legacy_sub.plan
    if legacy_plan == BusinessPlan.APPOINTMENTS_BASE:
      return get_appointments_plan_config('appointments', None)
    if legacy_plan == BusinessPlan.APPOINTMENTS:
      return get_appointments_plan_config('appointments', None)
    if legacy_plan == BusinessPlan.APPOINTMENTS_PRO:
      return get_appointments_plan_config('appointments_pro', None)
    if legacy_plan == BusinessPlan.APPOINTMENTS_AI:
      return get_appointments_plan_config('appointments_pro', None)
  raise ProfessionalQuotaUnavailable('No hay una suscripción activa de Turnos.')


def count_active_professionals(business, *, exclude_professional_id=None) -> int:
  queryset = AppointmentProfessional.objects.filter(business=business, is_active=True)
  if exclude_professional_id is not None:
    queryset = queryset.exclude(pk=exclude_professional_id)
  return queryset.count()


def detect_over_limit(business, *, effective_limit: int | None = None) -> ProfessionalQuotaState:
  if effective_limit is None:
    effective_limit = _effective_limit(_appointments_config(business))
  active_count = count_active_professionals(business)
  return ProfessionalQuotaState(
    active_count=active_count,
    effective_limit=effective_limit,
    over_limit=active_count > effective_limit,
  )


def assert_professional_slot_available(business, *, exclude_professional_id=None) -> None:
  config = _appointments_config(business)
  effective_limit = _effective_limit(config)
  effective_limit = min(
    effective_limit,
    _pending_downgrade_limit(business, effective_limit),
  )
  active_count = count_active_professionals(
    business, exclude_professional_id=exclude_professional_id,
  )
  if active_count >= effective_limit:
    raise ProfessionalQuotaExceeded(
      active_count=active_count,
      limit=effective_limit,
    )


def _pending_downgrade_limit(business, current_limit: int) -> int:
  from apps.billing.appointments_plans import EXTRA_PROFESSIONAL, get_appointments_plan_config
  from apps.billing.models import PendingSubscriptionChange, SubscriptionV2

  subscription = (
    SubscriptionV2.objects.filter(
      business=business,
      service_type=SubscriptionV2.ServiceType.APPOINTMENTS,
    )
    .exclude(status=SubscriptionV2.Status.CANCELED)
    .order_by('-created_at')
    .first()
  )
  if subscription is None:
    return current_limit
  pending = (
    PendingSubscriptionChange.objects.filter(
      subscription_v2=subscription,
      is_downgrade=True,
      status__in=('scheduled', 'blocked'),
    )
    .order_by('created_at')
    .first()
  )
  if pending is None:
    return current_limit
  target = get_appointments_plan_config(
    pending.target_plan_code,
    pending.target_usage_tier,
  )
  return target.included_professionals + pending.config_snapshot.get(
    'quantities', {},
  ).get(EXTRA_PROFESSIONAL, 0)


def validate_professional_membership(professional) -> None:
  membership = professional.membership
  if membership is None:
    return
  if membership.business_id != professional.business_id:
    raise ValidationError({'membership': 'La Membership debe pertenecer al mismo negocio.'})
  if membership.status != membership.Status.ACTIVE:
    raise ValidationError({'membership': 'Solo se puede vincular una Membership activa.'})
  if membership.role != 'professional':
    raise ValidationError({'membership': 'La Membership vinculada debe tener el rol profesional.'})
  config = _appointments_config(professional.business)
  if config.plan_code not in ('appointments_pro', 'appointments_ai'):
    raise ValidationError({'membership': 'El acceso profesional requiere Turnos Pro o Turnos IA.'})


def request_professional(request):
  membership = getattr(request, 'membership', None)
  business = getattr(request, 'business', None)
  if (
    membership is None or business is None or membership.role != 'professional'
    or membership.status != membership.Status.ACTIVE
  ):
    return None
  return (
    AppointmentProfessional.objects
    .filter(business=business, membership=membership, is_active=True)
    .select_related('membership')
    .first()
  )


def professional_login_enabled(business) -> bool:
  from apps.billing.runtime import resolve_subscription

  resolved = resolve_subscription(business, service_type='appointments')
  if not resolved.access_granted:
    return False
  plan = resolved.plan
  if resolved.source == 'v2':
    return plan in ('appointments_pro', 'appointments_ai')
  return (
    resolved.source == 'legacy'
    and resolved.legacy_sub is not None
    and resolved.legacy_sub.service == 'appointments'
    and plan in (BusinessPlan.APPOINTMENTS_PRO, BusinessPlan.APPOINTMENTS_AI)
  )

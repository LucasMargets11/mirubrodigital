from __future__ import annotations

from typing import Dict, List

from apps.business.features import feature_flags_for_plan
from apps.business.models import BusinessPlan
from apps.business.service_catalog import enabled_services


def build_business_context(business) -> Dict[str, object]:
  subscription = getattr(business, 'subscription', None)
  plan = getattr(subscription, 'plan', None) or BusinessPlan.STARTER
  status = getattr(subscription, 'status', None) or 'active'
  feature_flags = feature_flags_for_plan(plan)
  service_list: List[str] = enabled_services(plan, feature_flags)
  subscription_service = getattr(subscription, 'service', None)
  default_service = subscription_service or business.default_service or 'gestion'
  if default_service not in service_list and service_list:
    active_service = service_list[0]
  elif not service_list:
    active_service = 'gestion'
  else:
    active_service = default_service
  return {
    'plan': plan,
    'status': status,
    'features': feature_flags,
    'enabled_services': service_list,
    'default_service': default_service,
    'service': active_service,
  }

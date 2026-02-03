from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List

from apps.business.models import BusinessPlan


@dataclass(frozen=True)
class ServiceDefinition:
  slug: str
  name: str
  description: str
  features: List[str]
  min_plan: str


SERVICE_CATALOG: Iterable[ServiceDefinition] = (
  ServiceDefinition(
    slug='gestion',
    name='Gestion Comercial',
    description='Stock, ventas, caja y clientes en un solo lugar.',
    features=['products', 'inventory', 'stock', 'sales', 'customers', 'cash', 'reports'],
    min_plan=BusinessPlan.STARTER,
  ),
  ServiceDefinition(
    slug='restaurante',
    name='Restaurantes',
    description='Pedidos, mesas y automatizaciones con WhatsApp.',
    features=['resto_orders', 'resto_kitchen', 'resto_sales', 'resto_menu'],
    min_plan=BusinessPlan.PLUS,
  ),
)


def serialize_catalog() -> List[Dict[str, object]]:
  return [asdict(service) for service in SERVICE_CATALOG]


PLAN_ORDER = {
  BusinessPlan.STARTER: 0,
  BusinessPlan.PRO: 1,
  BusinessPlan.PLUS: 2,
}


def enabled_services(plan: str, feature_flags: Dict[str, bool]) -> List[str]:
  enabled: List[str] = []
  current_rank = PLAN_ORDER.get(plan, PLAN_ORDER[BusinessPlan.STARTER])
  for service in SERVICE_CATALOG:
    required_rank = PLAN_ORDER.get(service.min_plan, PLAN_ORDER[BusinessPlan.STARTER])
    if current_rank < required_rank:
      continue
    if all(feature_flags.get(feature, False) for feature in service.features):
      enabled.append(service.slug)

  if 'restaurante' in enabled and 'gestion' in enabled:
    enabled.remove('gestion')

  return enabled

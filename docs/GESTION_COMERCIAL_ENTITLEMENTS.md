# Gestión Comercial - Entitlements (Feature Gating)

## Introducción

Este documento define el sistema de **entitlements** para el servicio **Gestión Comercial**. Un **entitlement** es un permiso a nivel de plan/subscripción que habilita o bloquea el acceso a un módulo o feature específico.

El sistema de entitlements trabaja **junto con RBAC**, no lo reemplaza:
- **RBAC**: Define qué puede hacer un usuario dentro de un módulo (ej: `sales.view_sale`, `sales.create_sale`)
- **Entitlements**: Define si el business tiene acceso al módulo en sí (ej: `gestion.cash`)

Para acceder a un recurso, el usuario necesita **ambos**:
1. El business debe tener el **entitlement** del módulo
2. El usuario debe tener el **permiso RBAC** correspondiente

---

## Lista de Entitlements

A continuación se listan todos los entitlements para el servicio `gestion`:

### Core / Incluido en Todos los Planes

| Entitlement | Descripción | Incluido desde |
|-------------|-------------|----------------|
| `gestion.products` | Gestión de productos y catálogo | START |
| `gestion.inventory_basic` | Inventario básico (entradas, salidas, stock) | START |
| `gestion.sales_basic` | Ventas simples sin caja | START |
| `gestion.dashboard_basic` | Dashboard con métricas básicas | START |
| `gestion.settings_basic` | Configuración comercial básica | START |

### Pro Features

| Entitlement | Descripción | Incluido desde |
|-------------|-------------|----------------|
| `gestion.customers` | Gestión de clientes (CRM) | PRO |
| `gestion.cash` | Caja registradora y sesiones de caja | PRO |
| `gestion.quotes` | Cotizaciones + generación de PDF | PRO |
| `gestion.reports` | Reportes avanzados | PRO |
| `gestion.export` | Exportación de datos (Excel, CSV) | PRO |
| `gestion.treasury` | Tesorería / Finanzas (cuentas, movimientos) | PRO |
| `gestion.inventory_advanced` | Inventario avanzado (traspasos, lotes) | PRO |
| `gestion.sales_advanced` | Ventas avanzadas (descuentos, notas) | PRO |
| `gestion.rbac_full` | RBAC completo con auditoría | PRO |
| `gestion.audit` | Auditoría de cambios | PRO |

### Business Features

| Entitlement | Descripción | Incluido desde |
|-------------|-------------|----------------|
| `gestion.invoices` | Facturación electrónica (*) | BUSINESS |
| `gestion.multi_branch` | Multi-sucursal consolidado | BUSINESS |
| `gestion.transfers` | Transferencias entre sucursales | BUSINESS |
| `gestion.consolidated_reports` | Reportes consolidados multi-sucursal | BUSINESS |

(*) En **PRO** puede habilitarse mediante add-on `invoices_module`.

---

## Mapeo de Planes a Entitlements

### Plan START

```python
ENTITLEMENTS_START = {
    'gestion.products',
    'gestion.inventory_basic',
    'gestion.sales_basic',
    'gestion.dashboard_basic',
    'gestion.settings_basic',
}
```

### Plan PRO

```python
ENTITLEMENTS_PRO = ENTITLEMENTS_START | {
    'gestion.customers',
    'gestion.cash',
    'gestion.quotes',
    'gestion.reports',
    'gestion.export',
    'gestion.treasury',
    'gestion.inventory_advanced',
    'gestion.sales_advanced',
    'gestion.rbac_full',
    'gestion.audit',
}
```

### Plan BUSINESS

```python
ENTITLEMENTS_BUSINESS = ENTITLEMENTS_PRO | {
    'gestion.invoices',
    'gestion.multi_branch',
    'gestion.transfers',
    'gestion.consolidated_reports',
}
```

### Plan ENTERPRISE

```python
ENTITLEMENTS_ENTERPRISE = ENTITLEMENTS_BUSINESS  # + custom si es necesario
```

---

## Entitlements de Add-ons

### Invoices Module Add-on

**Code**: `invoices_module`  
**Habilita**: `gestion.invoices`  
**Disponible en**: PRO (en BUSINESS ya está incluido)

---

## Implementación Backend

### Helper Functions

```python
# src/apps/business/entitlements.py

from typing import Set

PLAN_ENTITLEMENTS = {
    'start': {
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
    },
    'pro': {
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
        'gestion.customers',
        'gestion.cash',
        'gestion.quotes',
        'gestion.reports',
        'gestion.export',
        'gestion.treasury',
        'gestion.inventory_advanced',
        'gestion.sales_advanced',
        'gestion.rbac_full',
        'gestion.audit',
    },
    'business': {
        # Todos los de PRO +
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
        'gestion.customers',
        'gestion.cash',
        'gestion.quotes',
        'gestion.reports',
        'gestion.export',
        'gestion.treasury',
        'gestion.inventory_advanced',
        'gestion.sales_advanced',
        'gestion.rbac_full',
        'gestion.audit',
        'gestion.invoices',
        'gestion.multi_branch',
        'gestion.transfers',
        'gestion.consolidated_reports',
    },
    'enterprise': {
        # Todos los de BUSINESS (se puede extender según custom)
        'gestion.products',
        'gestion.inventory_basic',
        'gestion.sales_basic',
        'gestion.dashboard_basic',
        'gestion.settings_basic',
        'gestion.customers',
        'gestion.cash',
        'gestion.quotes',
        'gestion.reports',
        'gestion.export',
        'gestion.treasury',
        'gestion.inventory_advanced',
        'gestion.sales_advanced',
        'gestion.rbac_full',
        'gestion.audit',
        'gestion.invoices',
        'gestion.multi_branch',
        'gestion.transfers',
        'gestion.consolidated_reports',
    },
}

ADDON_ENTITLEMENTS = {
    'invoices_module': {'gestion.invoices'},
}

def get_plan_entitlements(plan: str) -> Set[str]:
    """Retorna los entitlements base del plan."""
    return PLAN_ENTITLEMENTS.get(plan.lower(), set())

def get_effective_entitlements(subscription) -> Set[str]:
    """
    Calcula los entitlements efectivos de una subscription,
    incluyendo los del plan base + add-ons activos.
    """
    entitlements = get_plan_entitlements(subscription.plan)
    
    # Si tiene add-ons, agregarlos
    if hasattr(subscription, 'addons'):
        for addon in subscription.addons.filter(is_active=True):
            entitlements |= ADDON_ENTITLEMENTS.get(addon.code, set())
    
    return entitlements

def has_entitlement(business, entitlement_code: str) -> bool:
    """Verifica si un business tiene un entitlement específico."""
    try:
        subscription = business.subscription
        entitlements = get_effective_entitlements(subscription)
        return entitlement_code in entitlements
    except:
        return False
```

---

## Enforcement en Endpoints

### Decorator

```python
# src/common/permissions.py

from rest_framework.exceptions import PermissionDenied
from functools import wraps

def require_entitlement(entitlement_code: str, upgrade_hint: str = "PRO"):
    """
    Decorator que bloquea el acceso si el business no tiene el entitlement.
    
    :param entitlement_code: Código del entitlement (ej: 'gestion.customers')
    :param upgrade_hint: Plan sugerido ('PRO', 'BUSINESS', 'ADDON')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            business = getattr(request, 'business', None)
            if not business:
                raise PermissionDenied("No se pudo determinar el business.")
            
            if not has_entitlement(business, entitlement_code):
                raise PermissionDenied({
                    'code': 'plan_entitlement_required',
                    'entitlement': entitlement_code,
                    'upgrade_hint': upgrade_hint,
                    'message': f'Tu plan actual no incluye esta funcionalidad. Actualiza a {upgrade_hint}.'
                })
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
```

### Permission Class (DRF)

```python
from rest_framework.permissions import BasePermission

class HasEntitlement(BasePermission):
    """
    Permission class que verifica el entitlement del business.
    
    Uso:
        class CustomerViewSet(viewsets.ModelViewSet):
            permission_classes = [HasEntitlement]
            required_entitlement = 'gestion.customers'
            upgrade_hint = 'PRO'
    """
    def has_permission(self, request, view):
        entitlement_code = getattr(view, 'required_entitlement', None)
        if not entitlement_code:
            return True  # No entitlement required
        
        business = getattr(request, 'business', None)
        if not business:
            return False
        
        if not has_entitlement(business, entitlement_code):
            self.message = {
                'code': 'plan_entitlement_required',
                'entitlement': entitlement_code,
                'upgrade_hint': getattr(view, 'upgrade_hint', 'PRO'),
            }
            return False
        
        return True
```

---

## Endpoints a Proteger

### Customers
- **Endpoints**: `/api/v1/customers/`
- **Entitlement**: `gestion.customers`
- **Upgrade hint**: PRO

### Cash / Sessions
- **Endpoints**: `/api/v1/cash/`, `/api/v1/cash-sessions/`
- **Entitlement**: `gestion.cash`
- **Upgrade hint**: PRO

### Quotes
- **Endpoints**: `/api/v1/quotes/`
- **Entitlement**: `gestion.quotes`
- **Upgrade hint**: PRO

### Reports Export
- **Endpoints**: `/api/v1/reports/export/`
- **Entitlement**: `gestion.export`
- **Upgrade hint**: PRO

### Treasury
- **Endpoints**: `/api/v1/treasury/`
- **Entitlement**: `gestion.treasury`
- **Upgrade hint**: PRO

### Invoices
- **Endpoints**: `/api/v1/invoices/`
- **Entitlement**: `gestion.invoices`
- **Upgrade hint**: BUSINESS o ADDON (según plan)

---

## Frontend Integration

### Hook

```typescript
// apps/web/src/hooks/useEntitlements.ts

export function useEntitlements() {
  const { data, isLoading } = useSWR('/api/v1/business/entitlements', fetcher)
  
  return {
    entitlements: data?.entitlements ?? [],
    hasEntitlement: (code: string) => data?.entitlements?.includes(code) ?? false,
    isLoading,
  }
}
```

### Uso en Componentes

```typescript
const { hasEntitlement } = useEntitlements()

if (!hasEntitlement('gestion.customers')) {
  return <UpgradePrompt feature="Clientes" plan="PRO" />
}

// Renderizar módulo normalmente
```

---

## Testing

### Casos de Prueba

1. **START plan**: No puede acceder a `/api/v1/customers/` → 403
2. **PRO plan**: Puede acceder a `/api/v1/treasury/` → 200
3. **PRO plan sin add-on**: No puede acceder a `/api/v1/invoices/` → 403
4. **PRO plan con invoices_module add-on**: Puede acceder a `/api/v1/invoices/` → 200
5. **BUSINESS plan**: Puede acceder a `/api/v1/invoices/` → 200

---

**Última actualización**: Febrero 2026  
**Versión**: 1.0

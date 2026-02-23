# Fix: Servicios Habilitados para Cuentas Demo

## Problema Detectado

Las cuentas demo creadas por `seed_gestion_comercial_demo_accounts` no mostraban "Gestión Comercial" como habilitado en `/app/servicios`, y al intentar acceder a `/app/gestion/*` redirigía a `/app/servicios`.

### Causa Raíz

Los nuevos planes de Gestión Comercial ('start', 'pro', 'business') **no estaban definidos** en:
- `PLAN_FEATURES` (features.py)
- `PLAN_ORDER` (service_catalog.py)

Esto causaba que:
1. La función `enabled_services(plan, feature_flags)` no reconociera los planes nuevos
2. Los feature_flags se normalizaban a 'starter' (legacy)
3. El servicio 'gestion' requería features que 'starter' no tenía (ej: 'cash', 'reports')
4. El resolver devolvía `enabled_services: []` (lista vacía)
5. El layout de `/app/gestion` verificaba `session.services.enabled.includes('gestion')` → False
6. Redirigía a `/app/servicios`

## Archivos Modificados

### 1. `services/api/src/apps/business/features.py`

**Cambio**: Agregado los nuevos planes con sus features correspondientes:

```python
PLAN_FEATURES: Dict[str, Iterable[str]] = {
  # Legacy plans
  'starter': ('products', 'inventory', 'stock', 'sales', 'customers'),
  'plus': (...),  # Restaurante
  
  # New plans (Gestión Comercial) ✨ NUEVO
  'start': ('products', 'inventory', 'stock', 'sales'),
  'pro': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'reports'),
  'business': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'reports'),
  'enterprise': ('products', 'inventory', 'stock', 'sales', 'customers', 'invoices', 'cash', 'reports'),
  
  # Menu QR
  'menu_qr': (...),
}
```

### 2. `services/api/src/apps/business/service_catalog.py`

**Cambios**:

a) Agregado los nuevos planes al ranking:

```python
PLAN_ORDER = {
  # Legacy
  BusinessPlan.STARTER: 0,
  BusinessPlan.PLUS: 2,
  
  # New plans ✨ NUEVO
  BusinessPlan.START: 0,
  BusinessPlan.PRO: 1,
  BusinessPlan.BUSINESS: 2,
  BusinessPlan.ENTERPRISE: 3,
  
  # Menu QR
  BusinessPlan.MENU_QR: 0,
}
```

b) Simplificado los features requeridos para 'gestion':

```python
ServiceDefinition(
  slug='gestion',
  name='Gestion Comercial',
  description='Stock, ventas, caja y clientes en un solo lugar.',
  features=['products', 'inventory', 'stock', 'sales'],  # ✨ Reducido de 7 a 4
  min_plan=BusinessPlan.START,  # ✨ Cambiado de STARTER a START
),
```

**Razón**: El plan START solo tiene 4 features básicos, entonces 'gestion' solo debe requerir esos 4 para estar habilitado. Los features adicionales como 'customers', 'cash', 'reports' se controlan a nivel de rutas/componentes individuales.

### 3. `seed_gestion_comercial_demo_accounts.py`

**Cambio**: Agregada verificación automática end-to-end:

```python
def _verify_enabled_services(self, accounts):
    """
    Verifica que los servicios estén realmente habilitados usando el mismo resolver que la API.
    Si alguna cuenta no tiene 'gestion' habilitado, el comando falla.
    """
    from apps.business.context import build_business_context
    
    for account in accounts:
        business = account['business']
        context = build_business_context(business)
        enabled = context['enabled_services']
        
        if 'gestion' not in enabled:
            raise CommandError(
                "❌ Verificación fallida: cuenta sin Gestión Comercial habilitado"
            )
```

Ahora el comando **no termina exitosamente** si los servicios no están habilitados correctamente.

## Flujo de Verificación

El comando ahora verifica end-to-end:

```
1. Crea suscripciones (legacy + billing)
2. Ejecuta build_business_context(business) 
   └─> Lee business.subscription.plan
   └─> Calcula feature_flags_for_plan(plan)
   └─> Ejecuta enabled_services(plan, feature_flags)
3. Verifica que 'gestion' está en enabled_services
4. Si falla ⇒ CommandError con mensaje claro
```

Esto asegura que si el resolver cambia en el futuro, el seed lo detectará inmediatamente.

## Testing

### Antes del Fix
```bash
$ docker compose exec api python manage.py shell -c "..."
Enabled services: []  # ❌ Lista vacía
```

### Después del Fix
```bash
$ docker compose exec api python manage.py seed_gestion_comercial_demo_accounts

🔍 Verificando servicios habilitados con el resolver...
   ✅ gc.basic@demo.local: servicios habilitados = ['gestion']
   ✅ gc.pro@demo.local: servicios habilitados = ['gestion']
   ✅ gc.max@demo.local: servicios habilitados = ['gestion']

✅ Seed completado exitosamente.
```

## Frontend

No se necesitaron cambios en el frontend. El guard en `/app/gestion/layout.tsx` ya verificaba correctamente:

```tsx
const hasGestionService = resolvedSession.services.enabled.includes('gestion');

if (!hasGestionService) {
    redirect('/app/servicios');
}
```

Una vez que el backend devuelve correctamente `services.enabled: ['gestion']`, el frontend funciona automáticamente.

## Lecciones Aprendidas

1. **Source of truth único**: El resolver `enabled_services()` es la única fuente de verdad. Todo cambio de planes debe reflejarse ahí primero.

2. **Verificación automática**: Los seeds deben verificar que crearon lo que esperaban, ejecutando los mismos resolvers que usa la API.

3. **Compatibilidad dual**: Mantener ambos sistemas de suscripción (legacy + nuevo) sincronizados es crítico durante la migración.

4. **Features granulares**: Los features requeridos para que un servicio esté "habilitado" deben ser mínimos. Las restricciones adicionales se manejan a nivel de ruta/componente.

## Próximos Pasos

- [ ] Migrar completamente de `business.Subscription` a `billing.Subscription`
- [ ] Deprecar planes legacy ('starter', 'plus')
- [ ] Unificar lógica de entitlements en un solo módulo
- [ ] Agregar tests automatizados para `enabled_services()`

---

**Fecha**: 2026-02-21  
**Issue**: Cuentas demo no mostraban Gestión Comercial como habilitado  
**Status**: ✅ Resuelto

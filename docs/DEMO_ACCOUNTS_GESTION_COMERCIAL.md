# Cuentas Demo - Gestión Comercial

Este documento describe el comando de Django para crear cuentas demo para probar los 3 planes de Gestión Comercial.

## Comando de Management

### Ubicación
```
services/api/src/apps/billing/management/commands/seed_gestion_comercial_demo_accounts.py
```

### Uso

```bash
# Desde el directorio del proyecto
docker compose exec api python manage.py seed_gestion_comercial_demo_accounts

# O desde dentro del contenedor
python manage.py seed_gestion_comercial_demo_accounts
```

## Características

### ✅ Idempotente
- Ejecutar el comando múltiples veces **no duplica datos**
- Usa `get_or_create()` y `update_or_create()` según corresponda
- Actualiza passwords y suscripciones si ya existen

### 🔒 Seguro para Producción
- Solo funciona con `DEBUG=True`
- Si se ejecuta en producción, falla inmediatamente con error claro
- No hay forma de bypass accidental

### 🎯 Auto-detección de Planes
- Detecta automáticamente los 3 bundles de Gestión Comercial
- Filtra por `vertical='commercial'` y `is_active=True`
- Los ordena por precio (`fixed_price_monthly`)
- Valida que haya exactamente 3 planes disponibles

### 📦 Qué Crea

El comando crea (o actualiza):

1. **3 Usuarios** con credenciales fijas
2. **3 Negocios** (uno por usuario)
3. **3 Memberships** (relación user-business con role='owner')
4. **6 Suscripciones** (2 por negocio):
   - `business.Subscription` (sistema legacy con campo `plan`)
   - `billing.Subscription` (sistema nuevo con FK a `Bundle`)
5. **Verificación automática**: Al final, el comando ejecuta el mismo resolver que usa `/api/v1/auth/me/` para confirmar que el servicio 'gestion' está habilitado. Si la verificación falla, el comando termina con error.

Esto asegura compatibilidad completa con cualquier parte del código que use uno u otro sistema, y garantiza que las cuentas demo funcionen correctamente en el frontend.

## Credenciales Demo

### Plan START (Básico)
```
📧 Email:     gc.basic@demo.local
🔑 Password:  Demo12345!
🏢 Negocio:   GC Basic Demo
💰 Precio:    $99.00/mes
📦 Módulos:   5 incluidos
```

### Plan PRO
```
📧 Email:     gc.pro@demo.local
🔑 Password:  Demo12345!
🏢 Negocio:   GC Pro Demo
💰 Precio:    $299.00/mes
📦 Módulos:   15 incluidos
```

### Plan BUSINESS (Máximo)
```
📧 Email:     gc.max@demo.local
🔑 Password:  Demo12345!
🏢 Negocio:   GC Max Demo
💰 Precio:    $499.00/mes
📦 Módulos:   19 incluidos
```

## Flujo de Prueba Manual

### 1. Asegurar que los Bundles existen

```bash
docker compose exec api python manage.py seed_billing
```

### 2. Crear las cuentas demo

```bash
docker compose exec api python manage.py seed_gestion_comercial_demo_accounts
```

### 3. Iniciar sesión en el Frontend

Ir a: `http://localhost:3000/entrar`

Probar con cada una de las 3 cuentas:
- `gc.basic@demo.local` / `Demo12345!`
- `gc.pro@demo.local` / `Demo12345!`
- `gc.max@demo.local` / `Demo12345!`

### 4. Verificar Restricciones de Planes

Navegar a **Gestión Comercial** y validar:

#### Plan START (Basic)
- ✅ Productos, Inventario Básico, Ventas Básicas
- ❌ **NO** tiene: Clientes, Caja, Reportes, Tesorería, Facturación

#### Plan PRO
- ✅ Todo de START +
- ✅ Clientes, Caja, Reportes, Tesorería, Exportación, RBAC completo
- ❌ **NO** tiene: Multi-sucursal, Facturación, Transferencias

#### Plan BUSINESS (Max)
- ✅ Todo de PRO +
- ✅ Facturación Electrónica, Multi-sucursal, Transferencias, Reportes Consolidados

### 5. Verificar Endpoints de API

Probar que los endpoints respeten el plan:
- Features bloqueados deben retornar `403 Forbidden` o `402 Payment Required`
- Features permitidos deben funcionar correctamente

## Arquitectura Técnica

### Modelos Usados

```python
# Usuario (Django contrib.auth)
from django.contrib.auth import get_user_model
User = get_user_model()

# Negocio
from apps.business.models import Business, BusinessPlan

# Relación User-Business con Roles
from apps.accounts.models import Membership

# Bundles y Módulos (Sistema Nuevo)
from apps.billing.models import Bundle, Module

# Suscripción Legacy
from apps.business.models import Subscription as BusinessSubscription

# Suscripción Nuevo Sistema
from apps.billing.models import Subscription as BillingSubscription
```

### Relaciones Creadas

```
User (gc.basic@demo.local)
  └─> Membership (role='owner')
        └─> Business (GC Basic Demo)
              ├─> BusinessSubscription (plan='start', service='gestion')
              └─> BillingSubscription (bundle=gestion_start)
                    └─> Bundle (gestion_start)
                          └─> Modules (5 módulos core)
```

### Compatibilidad Dual

El comando crea **ambos tipos de suscripción** para máxima compatibilidad:

1. **Legacy** (`business.Subscription`): 
   - Campo `plan` (CharField con choices: start/pro/business)
   - Campo `service` = 'gestion'
   - Límites: `max_branches`, `max_seats`

2. **Nuevo** (`billing.Subscription`):
   - FK a `Bundle` (gestion_start/gestion_pro/gestion_business)
   - M2M a `Module` (módulos incluidos en el bundle)
   - Snapshot de precios en JSON

Esto permite que el código funcione tanto si usa el sistema legacy como el nuevo.

### Transaccionalidad

Todo se ejecuta dentro de `transaction.atomic()`:
- Si cualquier paso falla, se hace rollback completo
- No quedan datos parciales

## Troubleshooting

### Error: "Verificación fallida: algunas cuentas NO tienen Gestión Comercial habilitado"

**Causa**: Los planes creados por el seed no están devolviendo servicios habilitados.

**Solución**: Esto indica un problema en la configuración de planes. Verificar:
1. Los planes 'start', 'pro', 'business' están en `PLAN_FEATURES` (services/api/src/apps/business/features.py)
2. Los planes están en `PLAN_ORDER` (services/api/src/apps/business/service_catalog.py)
3. El `SERVICE_CATALOG` para 'gestion' tiene los features correctos que coinciden con los planes

### Error: "Se esperaban 3 bundles pero solo se encontraron X"

**Solución**: Ejecutar primero el seed de billing:
```bash
docker compose exec api python manage.py seed_billing
```

### Error: "Este comando solo se puede ejecutar en DEBUG=True"

**Causa**: Estás en producción o `DEBUG=False` en settings.

**Solución**: Este comando está diseñado solo para desarrollo. No se puede usar en producción por seguridad.

### Las credenciales no funcionan en el login

**Solución**: Verificar que:
1. El backend esté corriendo: `docker compose ps`
2. Las migraciones estén aplicadas: `docker compose exec api python manage.py migrate`
3. ECompatibilidad Dual de Suscripciones

El comando crea **dos suscripciones por negocio** para asegurar compatibilidad total:

1. **`business.Subscription`** (Legacy)
   - Usado por código existente que verifica `business.subscription.plan`
   - Tiene límites directos: `max_branches`, `max_seats`
   - Mapeo directo a `BusinessPlan` choices

2. **`billing.Subscription`** (Nuevo)
   - Sistema modular con `Bundle` y `Module`
   - Más flexible y extensible
   - Preparado para el futuro del sistema

Ambas suscripciones se mantienen sincronizadas por el comando.

### Mapeo Bundle → Legacy Plan

```python
bundle_to_legacy_plan = {
    'gestion_start': 'start',      # 1 branch, 2 seats
    'gestion_pro': 'pro',           # 1 branch, 10 seats
    'gestion_business': 'business', # 5 branches, 20 seats
}
```

### ¿Por qué billing.Subscription y no business.Subscription?

El proyecto tiene dos sistemas de suscripción:
- **Legacy**: `business.Subscription` (usa CharField `plan` con choices)
- **Nuevo**: `billing.Subscription` (usa FK a `Bundle` y M2M a `Module`)

Este comando usa el sistema **nuevo** porque:
1. Es más flexible y escalable
2. Los bundles están bien definidos con sus módulos
3. Es el futuro del sistema de planes

### Relación con business.Subscription

Si el sistema frontend/backend todavía depende del legacy `business.Subscription`, será necesario:

1. Crear también una instancia de `business.Subscription` por compatibilidad
2. O migrar completamente al sistema de `billing.Subscription`

Actualmente, el comando solo crea `billing.Subscription`. Si encuentras problemas, puede que necesites sincronizar ambos.

---

**Última actualización**: Febrero 2026  
**Autor**: GitHub Copilot  
**Versión**: 1.0

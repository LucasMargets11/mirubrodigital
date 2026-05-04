# QA Setup — Onboarding Gestión Comercial

**Fecha:** 2026-04-27  
**Contexto:** Entorno local Docker para QA manual del wizard de onboarding de Gestión Comercial.

---

## 1. Resumen del entorno

| Componente | Estado |
|---|---|
| Backend (api) | `mirubro-api` — running |
| Frontend (web) | `mirubro-web` — running |
| Postgres | `mirubro-postgres` — healthy |
| Redis | `mirubro-redis` — healthy |
| `ROLLOUT_NEW_ONBOARDING=true` | ✅ confirmado en container api |
| `NEXT_PUBLIC_NEW_ONBOARDING_ENABLED=true` | ✅ confirmado en container web (bake-time) |
| 24/24 backend tests | ✅ `Ran 24 tests in 5.142s — OK` |
| Seed de datos demo | ✅ 4 escenarios creados |

---

## 2. Variables de entorno configuradas

### Backend — `services/api/.env`
```
ROLLOUT_NEW_ONBOARDING=true
```
Activa `ROLLOUT_FLAGS['new_onboarding_enabled'] = True` en Django settings en runtime.

### Frontend — build-time (baked into Docker image)
Configurado en `infra/docker-compose.yml` como build arg:
```yaml
NEXT_PUBLIC_NEW_ONBOARDING_ENABLED: "true"
```
Y en `apps/web/Dockerfile` en el stage `builder`:
```dockerfile
ARG NEXT_PUBLIC_NEW_ONBOARDING_ENABLED
ENV NEXT_PUBLIC_NEW_ONBOARDING_ENABLED=${NEXT_PUBLIC_NEW_ONBOARDING_ENABLED}
```

Para desarrollo local (`npm run dev`), también está en `apps/web/.env`:
```
NEXT_PUBLIC_NEW_ONBOARDING_ENABLED=true
```

---

## 3. Bug fix aplicado

**Archivo:** `apps/web/src/app/app/gestion/onboarding/page.tsx`  
**Bug:** Línea 15 accedía a `session.role` que no existe en el tipo `Session`.  
**Fix:** `session.role` → `session.current.role`

Este error bloqueaba el build de producción (TypeScript check fail). El fix está baked en la imagen `infra-web`.

---

## 4. Credenciales de demo QA

Creados con `python manage.py seed_onboarding_gestion_demo`. El comando es idempotente.

| Esc | Email | Password | Plan | Descripción |
|---|---|---|---|---|
| A | `onboarding.start.clean@demo.local` | `Demo12345!` | starter | Sin productos — pantalla inicial del wizard |
| B | `onboarding.start.product@demo.local` | `Demo12345!` | starter | 1 producto — `first_product` completado |
| C | `onboarding.start.sold@demo.local` | `Demo12345!` | starter | 1 producto + 1 venta — wizard en `sales_setup` |
| D | `onboarding.pro.warning@demo.local` | `Demo12345!` | pro | 1 producto + `block_sales=True` — warning en `sales_setup` |

---

## 5. Rutas para QA manual

- Login: `http://localhost:3000/entrar`
- Onboarding wizard: `http://localhost:3000/app/gestion/onboarding`
- Dashboard (redirect si no tiene acceso): `http://localhost:3000/app/gestion/dashboard`

---

## 6. Checklist de escenarios QA

### Escenario A — Starter / Sin productos (wizard desde cero)
1. Login con `onboarding.start.clean@demo.local`
2. Navegar a `/app/gestion/onboarding`
3. Verificar que el wizard carga en el paso `business_basics`
4. Completar el formulario de datos del negocio → debe avanzar al paso `first_product`
5. Agregar un producto → debe avanzar al paso `sales_setup`
6. Activar ventas → wizard completado o cierre

### Escenario B — Starter / 1 producto ya cargado
1. Login con `onboarding.start.product@demo.local`
2. Navegar a `/app/gestion/onboarding`
3. El wizard debe detectar el producto existente y mostrar `first_product` como completado
4. El paso activo debe ser `sales_setup`

### Escenario C — Starter / Producto + venta registrada
1. Login con `onboarding.start.sold@demo.local`
2. El wizard debe mostrar tanto `first_product` como evidencia de la venta
3. El paso `sales_setup` debe estar activo o completado
4. Al completar `sales_setup`, el wizard cierra correctamente

### Escenario D — Pro / `block_sales=True`
1. Login con `onboarding.pro.warning@demo.local`
2. El wizard debe cargarse (plan Pro tiene acceso)
3. Al llegar a `sales_setup`, debe mostrarse el **warning** de que las ventas en efectivo están bloqueadas
4. El warning no debe impedir completar el wizard
5. NO debe modificar `CommercialSettings` (plan Pro)

### Acceso denegado (regression)
1. Login con cualquier usuario con rol `manager` o `operator`
2. Navegar a `/app/gestion/onboarding`
3. Debe redirigir a `/app/gestion/dashboard` (no 403, sino redirect silencioso)

---

## 7. Comandos de verificación rápida

```powershell
# Verificar flags en containers
docker compose -f infra/docker-compose.yml exec api env | findstr ROLLOUT
# → ROLLOUT_NEW_ONBOARDING=true

docker compose -f infra/docker-compose.yml exec web env | findstr ONBOARDING
# → NEXT_PUBLIC_NEW_ONBOARDING_ENABLED=true

# Re-ejecutar tests backend
docker compose -f infra/docker-compose.yml run --rm --no-deps api python manage.py test apps.business.tests.test_onboarding_views -v 2
# → Ran 24 tests in X.XXXs — OK

# Re-sembrar datos (idempotente)
docker compose -f infra/docker-compose.yml exec api python /app/manage.py seed_onboarding_gestion_demo

# Ver logs del api
docker compose -f infra/docker-compose.yml logs -f api

# Ver logs del web
docker compose -f infra/docker-compose.yml logs -f web
```

---

## 8. Notas

- **Treasury warning en escenario C:** Al crear la venta de demo, el sistema emitió `Cannot create treasury Transaction for sale ... no active account found.` — esto es esperado para datos de demo y no bloquea el flujo del wizard.
- **Rollout flag en producción:** El flag `ROLLOUT_NEW_ONBOARDING` está en `services/api/.env`. Para producción, ver `docs/RUNBOOK_ONBOARDING_GESTION_ROLLOUT.md`.
- **No modificar:** Carta Online, QR Reseñas, Restaurante. No crear datos productivos reales.

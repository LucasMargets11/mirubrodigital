# Runbook — Activación en Producción: Onboarding Gestión Comercial MVP

## Variables de entorno requeridas

| Variable | Contexto | Valor para activar |
|---|---|---|
| `ROLLOUT_NEW_ONBOARDING` | Backend (Django) — runtime | `true` |
| `NEXT_PUBLIC_NEW_ONBOARDING_ENABLED` | Frontend (Next.js) — **build-time** | `true` |

> ⚠️ **Ambas variables deben activarse coordinadamente.** Si solo se activa una, el resultado es experiencia degradada (ver tabla de riesgos abajo).

---

## Orden de despliegue

1. **Backend primero:** activar `ROLLOUT_NEW_ONBOARDING=true` y hacer deploy/restart del servicio `api`.
2. **Luego frontend:** setear `NEXT_PUBLIC_NEW_ONBOARDING_ENABLED=true` en el proceso de build de Next.js y hacer deploy de `web`.

El orden importa porque si el frontend se activa antes que el backend, el wizard intentará llamar endpoints que devuelven 503.

---

## Riesgos de activación parcial

| Estado | Efecto |
|---|---|
| Solo backend ON | Endpoints disponibles, UI inaccesible. Aceptable temporalmente. |
| Solo frontend ON | Banner y wizard cargan; todos los endpoints devuelven 503. El usuario ve "No se pudo cargar el asistente. Recargá la página." en lugar del wizard. |
| Ambas OFF | Comportamiento anterior sin onboarding. Ningún efecto. |

---

## Verificación post-deploy

### 1. Backend activo
```bash
curl -X GET https://<host>/api/v1/onboarding/gestion/context \
  -H "Cookie: bid=<business_id>" \
  -H "Authorization: Bearer <token>"
# Esperar: 200 OK con { progress, steps }
# Si 503: ROLLOUT_NEW_ONBOARDING no está activo en el contenedor
```

### 2. Frontend activo
- Navegar a `/app/gestion/dashboard` como owner/admin de un negocio sin `completed_at`.
- El banner azul "Terminar de configurar tu negocio" debe aparecer.
- El wizard en `/app/gestion/onboarding` debe cargar.

### 3. Verificar `Business.status` para negocios nuevos
El banner solo se muestra si `Business.status` está en `['onboarding', 'trialing', 'active']`.
Confirmar que los negocios recién registrados reciben uno de estos estados (no `'inactive'` u otro valor no listado).

```python
# En Django shell
from apps.business.models import Business
Business.objects.order_by('-created_at').values('id', 'name', 'status')[:5]
```

---

## Rollback

Para desactivar el onboarding sin redeploy:
- Backend: setear `ROLLOUT_NEW_ONBOARDING=false` y reiniciar el contenedor `api`.
- Frontend: el flag es build-time — requiere rebuild con `NEXT_PUBLIC_NEW_ONBOARDING_ENABLED=false`.

Para un rollback de emergencia sin rebuild de frontend: el backend OFF (503) es suficiente para que el banner no cargue y el wizard muestre error screen (no crash). 

---

## Notas de implementación

- El flag de backend se lee en `services/api/src/config/settings.py` línea ~349.
- El flag de frontend se evalúa en `isOnboardingEnabled()` en `apps/web/src/features/onboarding/gestion/utils.ts`.
- Los endpoints están bajo el namespace `business:onboarding-gestion-*`.
- El banner solo se muestra a `owner` y `admin`; otros roles no ven el wizard ni el banner.

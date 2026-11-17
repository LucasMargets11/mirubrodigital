# Turnos IA — alta interna del piloto

Permite que el personal de plataforma (`superadmin`) cree desde
`/admin/clientes/nuevo` un negocio con **Turnos IA Recepcionista** como acceso
bonificado, y que su recepción abra la bandeja de Leads.

## Qué cambió

- `seed_appointments_catalog` ahora crea la fila `Plan` `appointments_ai`
  (inactiva, `price=0`, `features_json.pricing_mode='usage_tier'`). Antes la
  salteaba y el formulario solo ofrecía Turnos y Turnos Pro. Una fila existente
  conserva su precio. El comando se puede ejecutar varias veces sin duplicar.
- `GET /api/v1/platform-admin/clients/provisioning-options/` agrega
  `usage_tiers` **solo** al plan `appointments_ai`: `ai_300`, `ai_1500`,
  `ai_3000`, tomados de `generated/pricing.json`. `custom` queda afuera porque
  no tiene conversaciones incluidas y la medición de IA lo rechaza.
- `POST /api/v1/platform-admin/clients/` acepta `usage_tier` (opcional).
  `grant_complimentary_access()` lo exige para Turnos IA y lo rechaza para
  cualquier otro plan. El error es `400 invalid_complimentary_usage_tier` en el
  campo `usage_tier`, y el alta completa se revierte.
- El formulario muestra "Nivel de uso" solo cuando el plan elegido trae tiers.
  Para Turnos, Turnos Pro y los demás servicios, el payload sigue teniendo los
  mismos 10 campos.
- Sin cambios en Turnos, Turnos Pro, las suscripciones existentes ni el checkout
  público: todos los checkouts exigen `plan_status='active'`, y el producto
  Turnos sigue con `is_active=false`.

## Qué representa cada valor

| Valor | Dónde | Significado |
|---|---|---|
| `appointments_ai` | `SubscriptionV2.plan_code` | Turnos IA: incluye Pro y Automatizaciones. Otorga `appointments.leads` |
| `ai_300` | `SubscriptionV2.usage_tier` | 300 conversaciones de IA por mes (tier canónico) |
| `appointments_base` | plan legacy | Lo usa `qa-turnos`, creado por shell. También otorga Leads, pero no se ofrece en el admin |

## Guía corta

1. En el servidor: `python manage.py seed_appointments_catalog`.
2. Panel admin → Clientes → Nuevo cliente:
   - Servicio: **Turnos**.
   - Plan: **Turnos IA Recepcionista**.
   - Nivel de uso: **IA 300** (o el que corresponda).
   - Fechas de inicio y fin, y motivo: los completa quien hace el alta.
3. El responsable ingresa con Google, con el mismo email cargado
   (`/entrar/cliente`).
4. Responsable → Configuración → Roles & Accesos → Accesos (Cuentas) →
   **+ Crear usuario** → rol **Manager / Encargado**. Ese es el rol de
   recepción.
5. Recepción ingresa en `/entrar` con su usuario. Si se marcó, cambia la
   contraseña en el primer ingreso y después abre **Leads**
   (`/app/turnos/leads`).

Acceso del rol Manager en Turnos: tiene `view_leads` y `manage_leads` (ver,
tomar, asignar, notas, vincular cliente/turno), además de turnos, clientes,
notas y recordatorios. **No** tiene `manage_users`,
`manage_agent_channels` ni `manage_reminder_automations`.

## Verificación 2026-11-17 (local aislado, datos ficticios)

Base `mirubro_turnos_ia` en el postgres del compose. API y web corrieron desde
este worktree en 127.0.0.1:8100 y 127.0.0.1:3100.

- Navegador, admin: Turnos → Turnos IA Recepcionista → IA 300, 6 meses →
  "Cliente creado correctamente". Suscripción guardada:
  `appointments / appointments_ai / ai_300 / manual / trialing / is_active`,
  con el período elegido y el motivo. No se corrigió nada por shell.
- La primera prueba en navegador encontró un bug: `lib/admin/client.ts`
  descartaba `usage_tier`. Se corrigió y se agregó un test.
- Navegador, responsable: creó a "Recepción Ficticia" como Manager/Encargado
  desde Accesos (Cuentas).
- Navegador, recepción: login por `/entrar`, cambio de contraseña forzado y
  bandeja de Leads vacía ("0 LEADS"). `GET /api/v1/leads/` respondió 200 y
  `/me` informó `features.leads=true`.
- Control (alta por el mismo formulario con el plan Turnos): sin `usage_tier`,
  `GET /leads/` → 403, `GET /customers/` → 200, `features.leads=false`. Esto se
  verificó con el test client del API, no en el navegador.
- **Bloqueo del entorno:** el responsable creado por el admin es
  `owner_managed` sin contraseña y solo entra con Google preautorizado.
  "Olvidé mi contraseña" no aplica a esas cuentas, a propósito. Localmente se
  emitió un JWT para esa cuenta (sin tocar la suscripción). En producción, el
  responsable entra con su Google real.

## Pendiente para la próxima entrega

- Medición de uso de IA con alta bonificada: `resolve_appointments_ai_usage_period`
  exige `billing_cycle` mensual o anual, y `_locked_subscription` exige
  `Business.status='active'`. El alta bonificada deja `billing_cycle=''` y el
  negocio en `trialing`. El bot podría quedar sin cupo autorizado hasta
  resolverlo.
- Alojamiento del bot, tokens permanentes, webhook de Meta, `provision_agent` y
  activación en producción.

# PROD-09A — Revisión integral del onboarding de Recepcionista IA

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `ab6024d` · Bot
`ef5e329` (leído con `git show`/`git grep`, sin checkout ni cambios). Solo
revisión: no se modificó código.

> **Aviso sobre el bot.** El checkout local de `D:\BOT RECEPCIONISTA\agenterecep`
> está en `develop` @ `e8b70fb` (2026-11-12), **anterior** a la base `ef5e329`
> (`origin/feat/recepcionista`, 3 commits adelante, PROD-07C). Lo revisado acá
> corresponde a `ef5e329`. Un despliegue desde el checkout actual no tendría
> multi-comercio ni la configuración dinámica.

## 1. Flujo de onboarding disponible hoy

| Paso | Estado | Dónde |
|---|---|---|
| Alta de cliente nuevo con Recepcionista (tier 300 / 1.500 / 3.000 o personalizado con cupo) | **Panel** | `/admin/clientes/nuevo` → `POST platform-admin/clients/` |
| Owner nuevo (cuenta activa sin contraseña, preautorizada) | **Panel** | `admin_client_provisioning_service._resolve_owner` |
| Reutilizar una cuenta existente como owner (confirmación con token de 15 min) | **Panel** | mismo form, 409 `existing_owner_requires_confirmation` |
| Instrucciones de acceso (copiar texto: «Ingresá con Google…») | **Panel** | `nuevo-cliente-form.tsx` (pantalla final) |
| Acceso del owner con Google | **Funciona** | `GoogleAuthView` + login preautorizado (`accounts/views.py`, ADMIN-CLIENTES 04C) |
| Período bonificado (inicio/fin) | **Panel** | `grant_complimentary_access` → `SubscriptionV2` `manual` + `trialing`, `trial_ends_at` = fin |
| Política IA personalizada | **Automática en el alta** | `create_reception_custom_policy` (`valid_from=max(now,inicio)`, `valid_until=fin`) |
| Agregar Recepcionista a un comercio existente | **Solo backend** | `POST platform-admin/clients/<id>/services/` (PROD-02F5); sin UI |
| Configuración del agente | **Panel** | detalle del cliente → «Recepcionista IA» (PROD-08C) |
| Consumo comercial y diagnóstico | **Panel (lectura)** | «Consumo comercial de IA» (PROD-08D) |
| Métricas operativas | **Panel (lectura)** | «Métricas operativas» (PROD-08D) |
| Canales y autorizaciones WhatsApp | **Panel (lectura)** / **shell (escritura)** | «Conexiones WhatsApp» (PROD-08E2) / `manage.py provision_agent` |
| Instancia + credencial HMAC del agente | **Solo shell** | `provision_agent --external-id --key-id` (secreto por env/stdin) |

### Ciclo de vida comercial

| Operación | Estado | Detalle |
|---|---|---|
| Alta del servicio | Panel (cliente nuevo) / backend (comercio existente) | ver arriba |
| Modificar cupo personalizado | **Solo servicio** | `change_reception_custom_allowance` y `cancel_scheduled_reception_custom_change` (`billing/services/reception_ai_policy.py`); sin endpoint, comando ni UI |
| Extender vigencia | **No existe** | No hay operación. Volver a otorgar falla con `ActiveSubscriptionConflictError` mientras la suscripción no esté cancelada, y también si hay sesiones de IA en el período (`AIUsagePeriodOverlapError`) |
| Suspender / reanudar | **No existe** | Nada escribe `suspended` a mano (PROD-02F6A). La suspensión solo ocurre sola: `trialing → suspended` cuando vence `trial_ends_at` (`billing/tasks.py`) |
| Cancelar | **Panel** | `/admin/suscripciones/[id]` → `POST subscriptions/<id>/cancel/` (`cancel_subscription_immediately`). Para `manual` no hace falta `provider_sub_id`. Es inmediato y no hay vuelta atrás |

Además, el detalle del cliente muestra **una sola** suscripción: la última no
cancelada. Si el comercio tiene Gestión y Recepcionista, la tarjeta «Plan y
suscripción» puede no ser la de Recepcionista. El bloque Recepcionista IA
(consumo) sí la identifica, con `source_subscription`.

## 2. Activación: qué hace atender al agente

No hay un interruptor operativo por comercio. Con `ef5e329`, el agente atiende
cualquier canal que se resuelva y verifica en **cada interacción**:

1. Mi Rubro le entrega la credencial del canal (`resolve_channel_whatsapp_credential`).
   Exige canal activo, autorización vigente del negocio o de plataforma, y WABA.
2. La instancia está habilitada (la autenticación HMAC rechaza una instancia
   deshabilitada).
3. La configuración está en `ready` (PROD-03C). Si está en `draft` o falta, no
   se llama al modelo: el lote queda como `agent_handoff_required` y se crea el
   lead para atención humana (PROD-07C).
4. La IA está autorizada comercialmente en esa interacción
   (`ai-usage/authorize`):
   - suscripción `trialing` con bonificación vigente, o `active`
     (`ai_source._business_may_consume`);
   - política válida y cupo disponible.
5. Flags globales de despliegue, no por comercio:
   - Mi Rubro: `AGENT_INTEGRATION_ENABLED`, `AI_USAGE_METERING_ENABLED`.
   - Agente: `MIRUBRO_SYNC_ENABLED`, `AI_USAGE_METERING_ENABLED`.
   - `BOT_ENABLED` solo aparece en `/health`: no bloquea nada.
6. Fuera de Mi Rubro, el webhook de Meta del número tiene que apuntar al
   agente. Queda para PROD-10/11.

**Consecuencia.** Cuando 1 a 6 se cumplen, el cliente queda atendido por IA
**automáticamente**. Los controles reversibles que existen hoy:

- **«Configuración lista» → «Borrador»** (panel). Corta la IA de ese comercio.
  Los mensajes se siguen recibiendo y se derivan a humano.
- **Revocar la autorización** (shell, local). El agente deja de enviar y
  recibir por ese canal. No revoca nada ante Meta.
- **Cancelar la suscripción** (panel). No tiene vuelta atrás.

Deshabilitar la `AgentInstance` corta **todos** los comercios que comparten la
instancia.

## 3. Preparación: qué se puede verificar con datos existentes

| Condición | Fuente ya disponible en el bloque | ¿Verificable? |
|---|---|---|
| Owner habilitado | Detalle del cliente: owner con membership `active` | **Parcial**: el admin no ve `user.is_active`, si vinculó Google (`google_sub`) ni si ya ingresó |
| Acceso comercial vigente | `ai-usage` → `diagnosis.code` y `source_subscription` (estado, bonificación, vigencia) | Sí |
| Política IA válida | `ai-usage` → `summary.status` (`available` / `exhausted` / `policy_not_configured` …) y `diagnosis` | Sí |
| Configuración ready | `receptionist-config` → `config.status`, `missing_for_ready` | Sí |
| Canal WhatsApp activo | `whatsapp-connections` → `is_active` / `local_status` | Sí |
| Autorización local vigente | `whatsapp-connections` → `local_status = credential_ready` | Sí (solo local) |
| Instancia habilitada | `whatsapp-connections` → `agent_instance.is_enabled` / `agent_instance_disabled` | Sí |

**No verificables todavía:**
- Conectividad real con Meta: webhook suscrito, permisos del token, número
  registrado. Queda para PROD-10/11.
- Que el proceso del agente esté online, con los flags correctos y la misma
  `AgentCredential`.
- Que los flags globales de Mi Rubro estén encendidos en el entorno.
- Que una conversación real de prueba haya funcionado. Las métricas
  operativas solo la muestran después.

`ready` y `credential_ready` no significan «agente conectado». Las pantallas
actuales ya lo aclaran.

## 4. Componentes y operaciones reutilizables

**Frontend**
- `app/admin/clientes/nuevo/nuevo-cliente-form.tsx`: alta, owner,
  confirmación, período, cupo personalizado.
- `app/admin/clientes/[clienteId]/cliente-detail-content.tsx`: monta el
  bloque.
- `components/admin/receptionist-admin-card.tsx`: un solo `Providers` y la
  regla de ocultamiento por 404 de dominio.
- `features/reception/receptionist-config-form.tsx`: incluye
  `useReceptionistConfig` y la confirmación de paso a borrador.
- `components/admin/admin-ai-usage-section.tsx`, junto con `features/reception/hooks.ts`
  (`useAdminAIUsage`, `useAdminWhatsAppConnections`).
- `components/admin/admin-whatsapp-connections-section.tsx`.
- `components/admin/{section-card,status-badge,empty-state,error-state,loading-state}.tsx`
  y `components/ui/modal.tsx`.
- `app/admin/suscripciones/[subscriptionId]/`: cancelación con motivo.

**Backend**
- `accounts/admin_client_provisioning_service.py` (`provision_admin_client`,
  `grant_with_domain_errors`).
- `accounts/admin_client_service_addition.py` (agregar servicio).
- `billing/complimentary_access_service.py` (`grant_complimentary_access`).
- `billing/services/reception_ai_policy.py` (crear, cambiar y revocar la
  política).
- `billing/services/ai_usage_admin.py` (diagnóstico).
- `billing/cancellation_service.py`.
- `leads/services/whatsapp_authorizations.py` y
  `leads/management/commands/provision_agent.py`.
- `platform_audit.record_platform_action`, para la auditoría.

## 5. Faltantes imprescindibles para el primer cliente

1. **Checklist de preparación.** Hoy los estados están repartidos en cuatro
   secciones y nada dice si el cliente está listo, ni que el paso a «lista»
   pone al agente a atender. Se resuelve solo en frontend con los datos ya
   cargados.
2. **Extensión de vigencia de la bonificación.** Al vencer `trial_ends_at`, la
   suscripción pasa sola a `suspended` y la IA se corta (queda derivación a
   humano). No hay manera de extenderla sin shell o base de datos, y volver a
   otorgar está bloqueado. En un plan personalizado, la política vence en la
   misma fecha (`valid_until=fin`), así que la extensión tiene que mover las
   dos cosas en una sola transacción auditada.
3. **Procedimiento documentado de alta técnica.** Instancia, credencial, canal
   y autorización existen solo por `provision_agent`. Hasta PROD-10/11 tiene
   que haber un runbook con:
   - el orden de los pasos;
   - los comandos exactos, con los secretos por stdin o env;
   - la verificación en el panel;
   - el corte de emergencia (paso a borrador o revocación);
   - que el agente se despliegue desde `ef5e329` o posterior.

**Condicional:** si el primer cliente **ya existe** en Mi Rubro, hace falta la
UI de «Agregar Recepcionista». El backend de PROD-02F5 está completo.

**Para después** (no bloquea el primer cliente):
- UI para cambiar el cupo personalizado (el servicio ya existe).
- Suspensión y reanudación manual: alcanza con el paso a borrador como corte
  operativo y la cancelación como corte definitivo.
- Mostrar en la tarjeta del plan todas las suscripciones, no solo la última.
- Indicar en el detalle si el owner ya vinculó Google.
- Alta de canales desde el panel: es parte de PROD-10/11.

## 6. Riesgos de activación y gestión comercial

- R1: **la activación es automática**. Un canal con credencial vigente más la
  configuración en `ready` atiende de inmediato. Pasar a «lista» equivale a
  poner en producción, aunque el texto del panel diga solo que no significa
  conectado.
- R2: **corte silencioso al fin de la bonificación**. El paso a `suspended`
  automático corta la IA sin aviso. Se ve en «Consumo», pero nadie avisa
  antes.
- R3: **el bot local está en una versión anterior** (`e8b70fb`) a la base.
- R4: **la instancia es compartida**. Deshabilitarla corta a todos los
  comercios; el corte de un solo comercio es el paso a borrador o la
  revocación.
- R5: **la cancelación es inmediata y definitiva**, y no hay reanudación. Si
  se usa como «pausa», hay que volver a otorgar. Eso puede chocar con
  `AIUsagePeriodOverlapError` si hubo sesiones en el período.
- R6: **«Plan y suscripción» muestra solo la última suscripción**. En
  multi-servicio se puede cancelar la que no era.
- R7: **la autorización revocada es solo local**. El token sigue vivo en Meta
  hasta que se revoque allá (PROD-10/11).

## 7. Propuesta mínima de integración

Sin wizard ni modelo de onboarding. El estado se **deriva** de los mismos
datos.

1. **«Preparación» al inicio del bloque Recepcionista IA del detalle.** Una
   `SectionCard` con siete filas (`StatusBadge`): owner, acceso comercial,
   política IA, configuración, canal, autorización e instancia.
   - Cada fila sale de las queries que el bloque ya hace: config, ai-usage,
     whatsapp-connections y el `client` del detalle. Usa las mismas query keys
     y el mismo `Providers`, así que no agrega requests.
   - No recalcula reglas: usa `diagnosis.code`, `summary.status`,
     `config.status` y `local_status`.
   - Una fila fija de «No verificable desde Mi Rubro» lista Meta, el agente
     online, los flags y la prueba real.
   - Un aviso explícito: con todo en verde, pasar a «Configuración lista» pone
     al agente a atender. Para cortar, volver a «Borrador».
2. **Extensión de vigencia.**
   - Backend: una operación en `billing` que mueva `trial_ends_at` y, si
     corresponde, `valid_until` de la política personalizada. Con lock
     Business → SubscriptionV2, solo hacia adelante, solo para suscripciones
     `manual` bonificadas de Recepcionista y con auditoría estricta.
   - Endpoint: `POST platform-admin/clients/<id>/services/reception/extend/`,
     o una acción sobre la suscripción.
   - UI: un botón con un `Modal` existente en la sección de consumo.
3. **Runbook** en `docs/`, con los pasos del punto 5.3 y la verificación en la
   checklist.
4. **Condicional:** «Agregar Recepcionista» en el detalle, reutilizando los
   campos del alta (plan, tier o cupo, período) contra el endpoint de 02F5.

## 8. Slices para terminar PROD-09

| Slice | Alcance | Tipo |
|---|---|---|
| **09B** | Checklist «Preparación» derivada en el bloque Recepcionista IA | Frontend |
| **09C** | Extensión de vigencia de la bonificación de Recepcionista (suscripción y política, atómica, auditada) y su botón | Backend + frontend |
| **09D** | Runbook de alta técnica y corte de emergencia del primer cliente | Docs |
| 09E (condicional) | UI «Agregar Recepcionista» a comercio existente sobre PROD-02F5 | Frontend |

**Decisiones pendientes:**
- D1: ¿el primer cliente es nuevo o ya existe en Mi Rubro? Define si 09E
  entra.
- D2: duración inicial de la bonificación del primer cliente. Si alcanza para
  el piloto, 09C puede ir después del go-live, pero antes del vencimiento.
- D3: actualizar el checkout local del bot a `ef5e329` antes de cualquier
  despliegue.

No se avanzó a PROD-09B.

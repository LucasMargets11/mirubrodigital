# PROD-10B2 — Servicio común de vinculación segura de WhatsApp

Fecha: 2026-11-28. Rama `feat/recepcionista`, base `7305b69`. Bot sin cambios (`de7e932`).
Solo backend de Mi Rubro. Sin endpoints, frontend, llamadas reales a Meta ni despliegue.

## 1. Contrato interno

`apps/leads/services/whatsapp_link.py`:

```python
link_whatsapp_channel(*, business, waba_id, phone_number_id, token, actor, reason, source, session=None)
    -> WhatsAppChannelLink(channel, authorization_id, outcome, created_channel,
                           created_authorization, verification, automatic_attention_enabled)
channel_meta_verification(channel, now=None) -> dict | None
```

- `source`: `assisted` | `embedded_signup`. Es la única diferencia entre ambos orígenes.
- `outcome`: `linked` (autorización nueva) | `already_linked` (repetición equivalente).
- `session` existe solo para inyectar el Graph simulado en tests.
- Errores:
  - `WhatsAppAuthorizationError(code)` para validaciones locales y conflictos.
  - `MetaGraphError(code, transient)` de PROD-10B1 para la verificación, sin envolver.

| Código | Cuándo |
|---|---|
| `actor_not_authorized` | No es superadmin (`operations` tampoco) |
| `invalid_source`, `invalid_reason` (1–255), `invalid_token` | Entrada |
| `client_not_eligible` | No es HQ o no tiene Recepcionista no cancelada |
| `agent_instance_not_configured`, `agent_instance_unavailable` | Falta `WHATSAPP_LINK_AGENT_INSTANCE_ID`, o la instancia no existe o está deshabilitada |
| `phone_number_unavailable` | Número activo en otro negocio, o carrera perdida. No revela cuál |
| `channel_agent_instance_mismatch`, `channel_waba_mismatch` | El canal existente usa otra instancia u otra WABA |
| `channel_credential_conflict` | El canal ya tiene otra credencial: otro token, de plataforma, revocada, inválida o vencida |
| `channel_changed_concurrently` | El canal cambió entre la lectura y el lock |
| `whatsapp_authorization_expired` | Venció entre la verificación y la escritura |
| `whatsapp_credential_unreadable` | No se pudo descifrar la credencial guardada al comparar |

## 2. Componentes reutilizados y nuevos

- **Reutilizados sin cambios:**
  - Modelos: `AgentInstance`, `AgentChannel`, `WhatsAppAuthorization`.
  - Servicios: `create_whatsapp_authorization`, `associate_channel`, `channel_credential_problem`, `verify_whatsapp_resources`.
  - Cifrado y auditoría: Fernet de `crypto.py`, `record_platform_action`.
  - Constraint de pnid activo único.
  - Fakes HTTP de los tests 10B1 y firma HMAC de 04C.
- **Movido, sin cambio de comportamiento:** `admin_reception_business` pasó de `receptionist_config_views.py` a `services/receptionist_config.py`. Las vistas lo importan de ahí, así un servicio no depende de una vista.
- **Nuevos:**
  - El módulo `whatsapp_link.py`.
  - El setting `WHATSAPP_LINK_AGENT_INSTANCE_ID` (env).
  - Un campo `AgentChannel.meta_verification` (JSON, nullable) con la migración `leads/0017`, aditiva y sin backfill.
  - No hay modelos, dependencias ni endpoints nuevos.

## 3. Flujo, persistencia y atomicidad

1. **Validaciones locales, sin locks:**
   - El actor es superadmin.
   - El cliente se resuelve con `admin_reception_business` por id. Nunca se usa el estado del objeto recibido.
   - Se resuelve la instancia compartida configurada. Nunca se elige ni se crea una.
   - Se buscan conflictos visibles del número. Si los hay, falla antes de llamar a Meta.
2. **`verify_whatsapp_resources`** se ejecuta fuera de cualquier transacción; un test lo comprueba con `in_atomic_block=False`. Exige:
   - Token válido y de nuestra app.
   - Permisos y alcance sobre la WABA.
   - Número dentro de la WABA.
   - Token y acceso a datos vigentes.
3. **Una transacción:**
   - Lock del `Business`. Serializa las vinculaciones del mismo comercio.
   - Revalidación: elegibilidad, instancia y vencimiento con `now` actual.
   - Lock de la autorización existente y después del canal. Es el orden de `associate_channel`.
   - Se vuelven a revisar los conflictos.
   - Se crea el canal si no existe, o se reutiliza el activo del mismo comercio e instancia que no tiene credencial.
   - `create_whatsapp_authorization(owner_business=business)`. Nunca `platform=True`.
   - `associate_channel`.
   - Se escribe la evidencia.
   - Auditoría `WHATSAPP_CHANNEL_LINKED`, que se suma a `WHATSAPP_AUTHORIZATION_CREATED/LINKED`.

   Cualquier falla revierte todo. Los tests lo cubren para fallas de auditoría, de asociación y de escritura de evidencia, y verifican que no queden autorizaciones huérfanas.
4. **Vencimiento efectivo:**
   - `expires_at` = el menor entre el vencimiento del token y el de acceso a datos. Es el único campo existente.
   - Así la regla local existente bloquea la entrega a tiempo.
   - `None` solo si Meta no informó ninguno (`0` o ausente).
   - Los dos valores originales quedan en la evidencia.

## 4. Idempotencia y conflictos

- **Repetición equivalente** (mismo comercio, número, WABA, instancia y token):
  - Responde `already_linked`, sin canal ni autorización nuevos.
  - Refresca la evidencia y la audita.
  - El token se compara descifrando y con `hmac.compare_digest`.
- **Token distinto, credencial de plataforma, revocada, inválida o vencida:** `channel_credential_conflict`. Nunca se rota ni se reemplaza en silencio.
- **Otra WABA u otra instancia:** se rechaza.
- **Número activo en otro comercio:** `phone_number_unavailable`, sin id ni nombre. No se reasigna.
- **Carreras:**
  - Mismo comercio: las serializa el lock del Business.
  - Distintos comercios: las resuelve la constraint de pnid activo único. El `IntegrityError` revierte toda la transacción y se traduce al mismo código.
  - Tests reales con hilos: dos comercios, el mismo comercio dos veces y el mismo comercio con tokens distintos. Siempre termina en un canal y una autorización.

## 5. Evidencia de verificación

`AgentChannel.meta_verification` (versión 1) guarda solo metadatos elegidos, nunca la respuesta cruda:

- `verified_at`, `source`.
- **Ligadura:** `authorization_id`, `authorization_updated_at`, `waba_id`, `phone_number_id`.
- `app_subscribed` y `override_callback_configured`, tal como se observaron.
- **Número:** `display_phone_number`, `verified_name`, `code_verification_status`, `quality_rating`, `platform_type`.
- **Token:** `type`, `scope_coverage` y los dos vencimientos. Nunca el token.
- `legal_ownership_verified: false`, explícito.

**Invalidación derivada:** `channel_meta_verification` devuelve `None` en estos casos:
- El canal no entregaría hoy su credencial (`channel_credential_problem`: inactivo, revocada, inválida, vencida…).
- Cambió la autorización asociada.
- Cambió su `updated_at`. Rotar, revocar o invalidar lo actualizan.
- Cambió la WABA o el número.
- La versión no coincide o el contenido está mal formado.

No hizo falta tocar los servicios existentes de rotación y asociación: aunque una escritura posterior no limpie el campo, la evidencia vieja nunca se presenta como vigente. Aun vigente es histórica: dice cuándo se observó, no que la conexión funcione ahora.

## 6. Activación operativa

- La vinculación no lee ni escribe la `ReceptionistConfig`; solo informa `automatic_attention_enabled`, en el resultado y en la auditoría. Un test verifica la fila idéntica antes y después.
- No toca suscripciones, contenido ni atención humana.
- **Riesgo con atención ya habilitada:**
  - En cuanto se vincula, el canal queda con credencial entregable por el GET HMAC (04C).
  - Si nuestra app ya estaba suscripta a la WABA (`app_subscribed=true` en la evidencia), los mensajes de ese número pueden empezar a llegar al bot y atenderse automáticamente sin otro paso.
  - Con `app_subscribed=false` no llegan hasta suscribir el webhook (10C).
  - **Recomendación para 10C:** mostrar ambos datos antes de confirmar y, si corresponde, pausar la atención primero con el switch existente (09C3).

## 7. Seguridad

- Ningún resultado, error, log, auditoría ni evidencia contiene el token, el app secret ni valores cifrados. Los tests lo comprueban en todos esos lugares y en las URLs de Graph.
- El token se guarda solo cifrado (Fernet existente). Los tests verifican el prefijo y la ausencia del texto plano.
- La auditoría es estricta y en la misma transacción: si falla, no hay vinculación.
- El Business sale solo del llamador. Nunca de Meta ni de otro contexto, y se re-resuelve por id.
- Ante una verificación inválida, incompleta o con error transitorio no hay ninguna escritura. Los tests cubren token inválido, vencido, de otra app, sin permisos, sin alcance, número fuera de la WABA y Meta caído.

## 8. Tests

`apps/leads/tests/test_whatsapp_link_10b2.py`: 49 tests con Graph simulado y PostgreSQL descartable (`postgres:16-alpine` en tmpfs). La concurrencia usa `TransactionTestCase` con hilos.

| Bloque | Cubre |
|---|---|
| Vinculación | Alta válida, dueño, cifrado, vencimiento efectivo, sin vencimiento, auditoría, reuso de canal sin credencial, logs y URLs sin secretos |
| Validaciones locales | Operations o no staff, origen y motivo, cliente cancelado, sucursal, instancia no configurada, inexistente o deshabilitada, token mal formado (sin llamar a Meta) |
| Meta | Inválido, vencido, acceso a datos vencido, otra app, permisos, alcance, número fuera de la WABA, Meta caído, vencimiento entre verificación y escritura |
| Idempotencia y conflictos | Repetición, token distinto, otro negocio sin revelarlo, otra WABA, otra instancia, revocada o de plataforma, conflicto detectado bajo lock tras la verificación |
| Atomicidad | Rollback por auditoría, asociación y evidencia; sin huérfanas |
| Evidencia | Contenido, app no suscripta, invalidación por rotación, revocación, reasociación, WABA, vencimiento, desactivación y manipulación |
| Atención | Deshabilitada sigue igual; habilitada, fila intacta |
| Entrega HMAC | El canal vinculado entrega token, WABA y `expires_at` por el GET 04C |
| Concurrencia | Meta fuera de transacción; dos negocios; mismo negocio repetido; tokens distintos |

**Regresiones:**
- `apps.leads` completo: **989/989 OK**. Son los 940 previos más los 49 nuevos, e incluyen las autorizaciones 04B, la entrega 04C, las conexiones 08E1, Meta Graph 10B1 y la configuración 03A/03B/03C/08C.
- `manage.py check`: sin problemas.
- `makemigrations --check`: sin cambios.

## 9. Riesgos y pendientes

- **Propiedad legal:** la verificación prueba autorización técnica sobre la WABA y el número, no la propiedad legal. La decisión queda en el superadmin y en el motivo auditado.
- **`platform_type`:** se registra pero no se exige `CLOUD_API`. Un número on-premise se vincularía y fallaría al operar. A decidir en 10C.
- **Sin verificar contra Meta real (10E):** heredado de 10B1, el app token en Bearer para `debug_token`, los códigos exactos de error y la semántica de `expires_at=0`.
- **Revocación del lado del cliente:** solo se detecta re-verificando (10C) o con la señal del bot (F8).
- **Despliegue:**
  - Requiere la migración `leads/0017` (aditiva y nullable, segura).
  - Requiere `WHATSAPP_LINK_AGENT_INSTANCE_ID` con el `external_id` de la instancia real. Sin él la vinculación falla cerrada y nada más cambia.
- **Fuera de alcance, para 10C y siguientes:** endpoints admin, re-verificación, suscripción del webhook, desactivación, reasignación, rotación con verificación previa y Embedded Signup.

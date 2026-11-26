# PROD-04A — Revisión y diseño mínimo de credenciales WhatsApp por conexión

Fecha: 2026-11-26 · Solo revisión y diseño: sin código funcional, modelos ni
migraciones. Base Mi Rubro `f48f0e4`, bot `8b69e4d`. No se leyó ni se muestra
ningún valor de secreto: solo nombres de variables y estructura de código.

## 1. Infraestructura existente reutilizable

| Pieza | Dónde | Qué aporta |
|---|---|---|
| `AgentInstance` | `apps/leads/models.py` | Deployment del bot. Puede atender varios negocios. |
| `AgentChannel` | idem | `(provider, phone_number_id)` → Business + instancia. Único activo global por número (constraint parcial). Es la fuente de la relación número ↔ negocio. |
| `AgentCredential` | idem | Secreto HMAC del bot, cifrado con `set_secret`/`get_secret`, CHECK de prefijo Fernet en DB, estados `active → retiring → revoked` con `revoked_at` coherente. |
| `apps/leads/crypto.py` | idem | Fernet con clave dedicada `AGENT_SECRET_ENCRYPTION_KEY`. Nunca cae a texto plano y los errores no incluyen material sensible. |
| `apps/merchant_payments` | `MercadoPagoConnection` + `EncryptedTextField` | Precedente de token OAuth por comercio con `status` y `token_expires_at`. Usa su propia clave `MP_TOKEN_ENCRYPTION_KEY`. |
| `provision_agent` | `apps/leads/management/commands` | Alta transaccional. El secreto se lee de env o stdin, nunca de argv, y nunca se imprime. Idempotente. Rota con un `key_id` nuevo. |
| `AgentHmacAuthentication` | `apps/leads/authentication.py` | Contract V1: firma sobre el path, ventana de timestamp, nonce (fail-closed opcional, como en `ai-executions`). |
| `resolve_channel` | `services/receiver.py` | Tenant derivado del canal activo de la instancia, con `channel_disabled`/`business_inactive`/`business_mismatch`. |
| `record_platform_action` | `apps/accounts/platform_audit.py` | Auditoría estricta y transaccional sobre `AccessAuditLog`. |
| `Conversation.phoneNumberId` (bot) | PROD-02E4B | El bot ya guarda en cada conversación por qué número entró. |

## 2. Inventario de credenciales

**Bot** (`src/config/configuration.ts`, `.env.example`; solo nombres):

| Variable | Alcance correcto | Estado actual |
|---|---|---|
| `WHATSAPP_APP_SECRET` | Global: firma `x-hub-signature-256` de la app de Meta | OK, global |
| `WHATSAPP_VERIFY_TOKEN` | Global: suscripción del webhook de la app | OK, global |
| `WHATSAPP_GRAPH_VERSION` | Global | OK, global |
| `WHATSAPP_ACCESS_TOKEN` | Por autorización de Meta | Global: un solo token para todo el deployment |
| `WHATSAPP_PHONE_NUMBER_ID` | Por conexión (ya está en `AgentChannel`) | Global: el webhook descarta otros números y `sendTextMessage` siempre envía desde este |
| `WHATSAPP_WABA_ID` | Por número (cada número pertenece a una WABA) | Global y sin uso en el código |
| `MIRUBRO_BUSINESS_ID` | Por conexión (sale del canal) | Global: un negocio por deployment |
| `RECEPTION_WHATSAPP_NUMBER` | Por negocio (aviso interno a recepción) | Global y odontológico; fuera de este slice |
| `MIRUBRO_AGENT_INSTANCE_ID`, `MIRUBRO_AGENT_KEY_ID`, `MIRUBRO_AGENT_SECRET` | Global por deployment (HMAC bot → Mi Rubro) | OK |
| `MIRUBRO_INBOUND_KEY_ID`, `MIRUBRO_INBOUND_SECRET`, `MIRUBRO_BASE_URL` | Global por deployment | OK |

**Mi Rubro** (`config/settings.py`; solo nombres):
- `AGENT_SECRET_ENCRYPTION_KEY`, `MP_TOKEN_ENCRYPTION_KEY`,
  `MFA_ENCRYPTION_KEY`: claves Fernet por dominio, globales. Ninguna tiene
  rotación de clave (no hay `MultiFernet` en el repo).
- `AGENT_TAKEOVER_BASE_URL`, `AGENT_TAKEOVER_KEY_ID`,
  `AGENT_TAKEOVER_SECRET`: un único destino de bot (Mi Rubro → bot). Es
  global por deployment; con varias instancias necesitará resolverse por
  `AgentInstance`, pero queda fuera de este slice.
- No hay ningún token de Meta en Mi Rubro hoy.

**Conclusión.** `phone_number_id` y la relación con el negocio ya viven en
Mi Rubro (`AgentChannel`). Lo que falta llevar a Mi Rubro es el token de
Meta y la WABA de cada número. El secreto de app y el verify token siguen
siendo globales.

## 3. Diseño mínimo propuesto

### 3.1 Responsabilidades separadas

- **`AgentCredential`:** autentica al bot frente a Mi Rubro (HMAC, secreto
  compartido). No cambia.
- **Autorización de Meta:** permite al bot actuar frente a Meta por cuenta de
  un negocio (Bearer token). Es otra contraparte, otro ciclo de vida
  (lo emite o revoca Meta, puede vencer) y otro alcance (uno o varios
  números). Por eso no se mezcla con `AgentCredential`.

### 3.2 Representación

**`AgentChannel` (existente) + 2 campos:**
- `waba_id`: CharField de dígitos, nullable para canales viejos. Es un dato
  del número (cada número pertenece a una sola WABA), así que va junto a
  `phone_number_id`, que no se duplica.
- `whatsapp_authorization`: FK nullable, `PROTECT`, al modelo nuevo.

**`WhatsAppAuthorization` (modelo nuevo, en `apps.leads`):**

| Campo | Notas |
|---|---|
| `id` | UUID |
| `owner_business` | FK Business, nullable. Si tiene valor, es una autorización del comercio (Embedded Signup); si es `null`, es una autorización de plataforma (system user de Mi Rubro, vinculación asistida) que puede cubrir números de varios negocios. |
| `encrypted_access_token` | TextField, `editable=False`, con `set_token()`/`get_token()` sobre `encrypt_agent_secret`/`decrypt_agent_secret`, más un CHECK de prefijo Fernet (mismo patrón que `AgentCredential`). |
| `status` | `active` \| `revoked` \| `invalid` (Meta rechazó el token). CHECK en DB. |
| `expires_at` | Nullable. Los tokens de system user no vencen. |
| `revoked_at` | Coherente con `revoked` (mismo CHECK que `AgentCredential`). |
| `created_at`, `updated_at` | |

**Varios números con una autorización:** varios `AgentChannel` apuntan a la
misma fila, así que un solo secreto cubre todos los números de esa WABA o de
ese system user.

**Regla de aislamiento:** si `owner_business` tiene valor, debe ser igual al
`business` de cada canal que la referencia. Se valida en `save()` y en el
servicio, igual que los invariantes cross-table de `LeadAgentState`, porque
la DB no puede expresarlo. Una autorización de plataforma solo la puede
asignar Platform Admin.

**Rotación:** se reemplaza el token en la misma fila (`set_token`) y se
audita. Los canales siguen asociados sin tocarlos. Las autorizaciones de
Meta no tienen solapamiento útil como el `retiring` del HMAC: el token viejo
lo invalida Meta.

**Revocación:** `status=revoked` y `revoked_at`. Todos los canales que la
usan dejan de resolver credencial (fail-closed). Reasignar un canal a otra
autorización es una operación explícita y auditada.

### 3.3 Qué NO se crea

- No se duplica `phone_number_id`.
- No hay tabla intermedia autorización ↔ número: la FK en `AgentChannel`
  alcanza.
- No hay historial de tokens: la auditoría registra el evento.
- No hay `token_type`, scopes ni metadatos de Meta mientras no se usen.
- No hay clave Fernet nueva ni dependencia nueva.

## 4. Elementos nuevos estrictamente necesarios

| Elemento | Por qué no alcanza lo existente |
|---|---|
| `WhatsAppAuthorization` | El token de Meta puede cubrir varios números (y, en modo plataforma, varios negocios). Guardarlo en `AgentChannel` copiaría el secreto en cada canal y obligaría a rotarlo en N filas. Guardarlo en `AgentCredential` mezclaría el HMAC de Mi Rubro con un Bearer de Meta, que tienen otra contraparte, otro vencimiento y otro alcance. `MercadoPagoConnection` es OneToOne con Business y de otro dominio. |
| `AgentChannel.waba_id` | Dato de Meta por número que hoy solo existe como env global sin uso. |
| `AgentChannel.whatsapp_authorization` | Vincula el número con su autorización sin duplicar la relación con el negocio. |
| 3 acciones de auditoría (`WHATSAPP_AUTHORIZATION_CREATED/ROTATED/REVOKED`) | `AccessAuditLog.action` tiene choices. Solo cambia el estado de la migración. |
| Más adelante, un GET HMAC de credencial por canal (§5.3) | La configuración de 03C no debe llevar secretos (ver §5.4). |

**Clave de cifrado:** se reutiliza `AGENT_SECRET_ENCRYPTION_KEY` y su módulo
`crypto.py`. Es el mismo dominio (integración del bot), el mismo servicio la
lee y no suma operación de claves. Si más adelante se quiere aislar el radio
de exposición, el cambio a una clave propia queda localizado en
`set_token`/`get_token`.

No uso `EncryptedTextField` de pagos: descifra en cada lectura del ORM y está
atado a `MP_TOKEN_ENCRYPTION_KEY`. Un `get_token()` explícito evita que el
token aparezca en claro en serializers, admin o `values()` por accidente.

## 5. Seguridad y riesgos

1. **Cifrado en reposo:** Fernet con la clave del agente, CHECK de prefijo en
   DB, sin texto plano posible y `__str__` sin token.
2. **Acceso restringido:**
   - Sin endpoint humano que devuelva el token, nunca: ni al comercio ni a
     Platform Admin. La administración solo escribe (crear, rotar, revocar)
     y lee metadatos (estado, vencimiento, canales).
   - Alta inicial por un comando de management, extendiendo
     `provision_agent`: el token se lee de env o stdin, nunca de argv.
3. **Resolución por canal autorizado:**
   - El bot obtiene el token con un GET HMAC nuevo, resuelto con
     `resolve_channel`: canal activo de su instancia, `business_id`
     contrastado.
   - Devuelve el token solo si la autorización está `active` y no vencida.
   - Nonce fail-closed, porque entrega un secreto (como `ai-executions`).
   - `no-store`, sin eco en logs.
4. **Configuración separada:** el token no viaja en el payload de 03C. La
   configuración es contenido no secreto que se puede cachear o mostrar.
5. **Revocación y rotación:**
   - El bot mantiene el token solo en memoria, con TTL corto (≤ 5 min), y
     nunca lo persiste ni lo loguea.
   - Una revocación o rotación tarda como máximo ese TTL en llegar.
   - Si Meta responde 401 o 190, el bot descarta el cache y Mi Rubro puede
     marcar la autorización `invalid`.
6. **Auditoría:** `record_platform_action` estricto con
   `{authorization_id, owner_business o null, channel_ids, status}`. Nunca el
   token, ni un hash, ni sus últimos caracteres.
7. **Filtraciones entre negocios:**
   - Regla `owner_business == channel.business`.
   - El token solo se entrega por canal de la instancia firmante.
   - Una autorización de plataforma solo la asigna Platform Admin.

**Riesgos:**
- **R1:** no hay rotación de la clave Fernet en el repo (tampoco para
  `AgentCredential` ni Mercado Pago). Rotarla exige recifrar fuera de línea.
  `MultiFernet` sería el paso siguiente si se requiere.
- **R2:** con una autorización de plataforma, un token de Mi Rubro cubre
  números de varios comercios. Comprometerlo afecta a todos. Por eso el
  Embedded Signup (token del comercio) es el destino.
- **R3:** el bot sigue con un único token y número por env hasta
  implementar §6. Mientras tanto, multi-comercio real no es posible.
- **R4:** `AGENT_TAKEOVER_*` es un único bot destino; varias instancias
  necesitarán resolver el destino por `AgentInstance`. Queda fuera de este
  slice.

## 6. Integración futura

- **Vinculación asistida inicial:** Platform Admin o un comando crean una
  autorización de plataforma (o del comercio) y el `AgentChannel` con
  `waba_id` y FK. Reutiliza `provision_agent`.
- **Meta Embedded Signup:** el callback canjea el código por un token del
  comercio y crea `WhatsAppAuthorization(owner_business=…)` más los canales
  de los números elegidos, en una transacción auditada. El modelo no cambia;
  solo se agrega el flujo.
- **Resolución dinámica en el bot:**
  - el webhook acepta cualquier `phone_number_id`, que se valida contra Mi
    Rubro (el GET de 03C ya responde `channel_disabled` si no corresponde);
  - `business_id` sale del canal y ya no de `MIRUBRO_BUSINESS_ID`.
- **Envío desde el número correcto:** `sendTextMessage` usa el
  `Conversation.phoneNumberId` de esa conversación (ya persistido) y el token
  resuelto para ese canal, en lugar de las variables globales.

## 7. Siguientes slices

- **PROD-04B (Mi Rubro):**
  - modelo `WhatsAppAuthorization`;
  - campos `waba_id` y `whatsapp_authorization` en `AgentChannel`;
  - migración y acciones de auditoría;
  - extensión de `provision_agent` (token por stdin o env, rotar, revocar);
  - tests de cifrado, aislamiento, revocación y auditoría sin secretos.
  - Sin endpoints todavía.
- **PROD-04C (Mi Rubro):** GET HMAC de credencial por canal (fail-closed,
  `no-store`) con tests de canal ajeno, revocado, vencido y replay.
- **PROD-04D (bot):** resolución dinámica de número, negocio, configuración
  y token por canal, envío desde el número de la conversación y retiro de
  `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_WABA_ID` y
  `MIRUBRO_BUSINESS_ID` como fuentes.

No se avanzó a PROD-04B.

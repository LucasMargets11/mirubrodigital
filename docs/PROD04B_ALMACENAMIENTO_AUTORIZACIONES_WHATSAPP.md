# PROD-04B — Almacenamiento seguro de autorizaciones WhatsApp

Fecha: 2026-11-26 · Rama `feat/recepcionista` · Base Mi Rubro `ca23b6c` · Bot
`8b69e4d` sin cambios. Diseño de referencia:
`docs/PROD04A_DISENO_CREDENCIALES_WHATSAPP.md`. Sin endpoints, frontend ni
llamadas a Meta; no se accedió a secretos reales.

## 1. Modelo y campos

**`WhatsAppAuthorization`** (`apps.leads`, migración `leads/0015`):

| Campo | Regla |
|---|---|
| `id` | UUID |
| `owner_business` | FK Business, nullable, `CASCADE`. **Inmutable** (`save()` rechaza cambiarlo, también entre dueño y plataforma). `NULL` = autorización de plataforma, excepcional: requiere `platform=True` explícito. |
| `encrypted_access_token` | `editable=False`. Solo `set_token()`/`get_token()` sobre `crypto.py`. CHECK de prefijo Fernet en DB. |
| `status` | `active` \| `revoked` (local) \| `invalid` (reservado para cuando Meta rechace el token; lo usa la resolución). CHECK en DB. |
| `expires_at` | Nullable (los tokens de system user no vencen). |
| `revoked_at` | CHECK: con valor si y solo si `status=revoked`. |
| `created_at`, `updated_at` | Automáticas. |

`__str__`/`repr` nunca incluyen el token, ni siquiera cifrado.

**`AgentChannel`**: solo dos campos nuevos.
- `waba_id`: dígitos, `''` por defecto, con CHECK.
- `whatsapp_authorization`: FK nullable, `RESTRICT`. No se borra una
  autorización en uso, salvo dentro del mismo cascade que borra sus canales.

Se reutiliza `phone_number_id`. `AgentChannel.save()` valida que una
autorización con dueño solo se asocie a canales de ese Business (el mismo
patrón cross-table que `LeadAgentState`).

Los canales existentes quedan con `waba_id=''` y sin autorización: no se
migró ni se inventó ningún dato.

## 2. Operaciones centralizadas

`apps/leads/services/whatsapp_authorizations.py` es el único camino de
escritura y resolución:

| Operación | Locks y reglas |
|---|---|
| `create_whatsapp_authorization` | Valida el token (20 a 4096 caracteres ASCII visibles, sin espacios) y el vencimiento (futuro, con zona horaria). Exige dueño o `platform=True`, nunca ambos. |
| `associate_channel` | Bloquea la autorización y luego el canal. Solo acepta un canal activo, una autorización activa y vigente, el dueño correcto y un `waba_id` válido. Reasignar es la misma operación (auditada con `previous_authorization_id`). Si no hay cambios, no hace nada ni audita. |
| `rotate_whatsapp_authorization` | Bloquea la fila y reemplaza el token en el lugar: los canales siguen asociados. Una autorización inválida o vencida vuelve a `active`. Una revocada no se rota (se crea otra). |
| `revoke_whatsapp_authorization` | Bloquea la fila. Revocación local e idempotente; corta todos los canales que la usan. |
| `resolve_channel_access_token` | Resolución interna, fail-closed. Falla con un código propio si el canal está inactivo, no tiene autorización o es de otro dueño, o si la autorización está revocada, inválida o vencida. Un fallo de descifrado propaga `AgentSecretEncryptionError`, sin caer a texto plano. |

- **Actor:** todas las operaciones exigen personal de plataforma con rol
  `superadmin` u `operations` (administración interna).
- **Orden de locks:** autorización antes que canal, en todas las operaciones.
- **Revocación local:** rotar o revocar no invalida el token ante Meta. La
  auditoría lo registra con `meta_revocation: not_performed` y el comando lo
  advierte.

**`provision_agent`** (comando existente, extendido):
- `--create-whatsapp-authorization`: crea la autorización y la asocia al
  canal dado. Con `--platform-whatsapp-authorization` la crea sin dueño.
- `--whatsapp-authorization-id`: asocia el canal a una autorización
  existente (por ejemplo, compartida).
- `--rotate-whatsapp-authorization <uuid>` y
  `--revoke-whatsapp-authorization <uuid>`.
- Todas exigen `--actor-email`, y crear o asociar exige además `--waba-id`.
- El token se lee con el mismo mecanismo que el secreto HMAC (ahora un
  helper común `_read_value`): env `WHATSAPP_PROVISION_TOKEN` o
  `--whatsapp-token-stdin` (oculto en terminal). Nunca se acepta por
  argumento ni se imprime.
- Todo ocurre en una transacción: si falla la asociación, se revierte la
  creación del token.

## 3. Seguridad

- **Cifrado:** `AGENT_SECRET_ENCRYPTION_KEY` y `crypto.py` reutilizados, sin
  clave nueva. Sin clave, no se crea nada; con una clave distinta, falla sin
  devolver texto plano.
- **Sin exposición:** no hay endpoints ni frontend. El token solo sale de
  `resolve_channel_access_token` (para PROD-04C) y nunca aparece en `str`,
  `repr`, auditoría ni la salida del comando (verificado contra el token, el
  texto cifrado y sus fragmentos).
- **Aislamiento:** el dueño es inmutable; una autorización con dueño solo
  sirve a canales de ese negocio (validado en el servicio, en
  `AgentChannel.save()` y de nuevo al resolver, por si alguien escribió con
  `update()`). Las autorizaciones de plataforma solo se crean con la bandera
  explícita y por personal interno.
- **Auditoría:** `AccessAuditLog` mediante `record_platform_action` estricto,
  en la misma transacción, con cuatro acciones nuevas
  (`WHATSAPP_AUTHORIZATION_CREATED`, `LINKED`, `ROTATED`, `REVOKED`;
  migración `accounts/0036`, cambio de choices sin efecto en la base).
  - Registra `scope`, `status`, `expires_at`, `channel_ids`,
    `business_ids`, y además `previous_status`, `previous_authorization_id`
    o `meta_revocation` según la operación. Nunca el token.
  - `record_platform_action` acepta `platform_scope=True`, la única forma de
    auditar sin Business (autorización de plataforma). Es explícito, así que
    una falta de Business nunca pasa en silencio.
  - Si la auditoría falla, la operación se revierte (cubierto por tests).

## 4. Infraestructura reutilizada y elementos nuevos

**Reutilizado:**
- `crypto.py` + `AGENT_SECRET_ENCRYPTION_KEY`;
- el patrón de `AgentCredential` (`set_*`/`get_*`, CHECK Fernet, coherencia
  de `revoked_at`, `__str__` sin secreto);
- `AgentChannel` (`phone_number_id`, relación con Business);
- el patrón de invariantes en `save()` de `LeadAgentState`;
- `provision_agent` y su lectura segura de secretos;
- `AccessAuditLog` + `record_platform_action`;
- `select_for_update` y la técnica de tests concurrentes de 03B;
- las factories de tests de Leads.

**Nuevo, imprescindible:**
- el modelo (justificado en PROD-04A §4) y los dos campos de canal;
- el servicio, como único lugar de las reglas;
- cuatro choices de auditoría;
- el parámetro `platform_scope` en `record_platform_action`: una
  autorización de plataforma no tiene Business y la función los exigía
  siempre.

**No creado:** endpoints, caché, historial de tokens, tabla intermedia,
clave nueva ni dependencias.

## 5. Migraciones

- `leads/0015_whatsapp_authorization`: agrega `AgentChannel.waba_id` y la
  FK, crea el modelo y 4 CHECK.
- `accounts/0036_whatsapp_authorization_audit_actions`: solo choices.
- Validadas sobre PostgreSQL 16 descartable: se migró hasta
  `leads/0014`/`accounts/0035`, se insertó por SQL un canal legacy, se aplicó
  0015 (el canal quedó con `waba_id=''`, FK nula, activo y sin
  autorizaciones creadas), se hizo rollback a `0014` y se re-aplicó con el
  mismo resultado. `makemigrations --check` no detecta cambios.

## 6. Tests

`apps/leads/tests/test_whatsapp_authorizations_04b.py`, con 34 tests:

- **Cifrado:** el token queda cifrado en reposo y se recupera; la DB rechaza
  texto plano; con otra clave falla sin fallback; sin clave no crea nada;
  validación del token.
- **Sin secretos:** `str`/`repr` de la autorización y del canal, y la
  auditoría, sin el token, el texto cifrado ni sus fragmentos; metadatos de
  auditoría exactos.
- **Compartida y aislada:** dos canales del mismo negocio con una sola fila;
  una autorización de plataforma para dos negocios (auditada sin Business);
  una autorización con dueño nunca sirve a otro negocio (servicio, `save()`
  y resolución tras `update()`); la plataforma exige la bandera; dueño
  inmutable; solo superadmin u operations; reglas de asociación; reasignar
  audita y una asociación sin cambios no.
- **Legacy y borrado:** los canales legacy siguen guardando y fallan
  cerrados al resolver; CHECK de `waba_id`; una autorización en uso no se
  borra; borrar el Business dueño borra sus canales y su autorización sin
  tocar otros.
- **Rotación y revocación:** la rotación conserva los canales y audita
  `meta_revocation`; reactiva una autorización inválida o vencida; la
  revocación es idempotente y terminal (no se rota ni se asocia después) y
  corta todos los canales compartidos; vencidas, inválidas y canales
  inactivos nunca resuelven; validación del vencimiento.
- **Rollback:** creación, asociación, rotación y revocación se revierten si
  falla la auditoría.
- **Comando:** crear, asociar, rotar y revocar sin mostrar tokens; asociar
  una existente y la bandera de plataforma; validaciones (actor, waba, token
  ausente, uuid inválido) sin efectos; un fallo al asociar revierte la
  creación; no existe argumento para pasar el token.
- **Concurrencia real** (threads y `TransactionTestCase`): rotar contra
  revocar termina en `revoked` y sin resolución; dos rotaciones se
  serializan; asociar contra revocar nunca deja un vínculo revocado que
  resuelva.

| Corrida (PostgreSQL 16 descartable, tmpfs) | Resultado |
|---|---|
| `test_whatsapp_authorizations_04b` | 34/34 OK |
| `test_provision_command` (existente) | 12/12 OK |
| `apps.leads` + 7 suites de alta de clientes y acceso complementario (usan `record_platform_action`) | 963/964; la única falla es un flake de borde ajeno (ver abajo) |
| `manage.py check` / `makemigrations --check` | sin issues / sin cambios |

La falla de la corrida grande, `test_receiver_api.HmacAuthenticationTests.test_future_timestamp`,
es una carrera de un segundo preexistente: el test firma con `now + 301` contra una
tolerancia de 300 segundos, y si pasa un segundo antes de la verificación queda dentro de
la ventana. No hay cambios desde `ca23b6c` en `authentication.py`, `contract.py` ni el
test. La suite `test_receiver_api` re-ejecutada 3 veces dio 81/81 OK.

## 7. Riesgos

- **R1:** la clave Fernet no se puede rotar (no hay `MultiFernet` en el
  repo; tampoco para HMAC ni Mercado Pago). Rotarla exige recifrar fuera de
  línea.
- **R2:** una autorización de plataforma comprometida afecta a todos los
  negocios que cubre. Es excepcional y queda auditada con `business_ids`.
- **R3:** la revocación local no revoca ante Meta. Hay que hacerlo en Meta
  Business Manager; la auditoría y el comando lo dicen explícitamente.
- **R4:** la autorización revocada conserva el texto cifrado (no hay
  historial ni borrado). Es inutilizable por la resolución, pero sigue
  cifrado en la base.
- **R5:** `bulk_create`/`update()` saltean `save()`. La resolución vuelve a
  validar el dueño y el estado.
- **R6:** el estado `invalid` no tiene operación propia todavía. Lo marcará
  el flujo que reciba el rechazo de Meta (PROD-04D), y por ahora solo se
  sale de él rotando.

## 8. Commits y HEAD final

Commits sobre `ca23b6c`: modelo y migraciones, servicio y comando, tests, y
este reporte. Empujados a `origin/feat/recepcionista` sin force push. No se
tocó el bot ni se avanzó a PROD-04C.

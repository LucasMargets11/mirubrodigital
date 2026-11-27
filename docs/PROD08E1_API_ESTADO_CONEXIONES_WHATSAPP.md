# PROD-08E1 — API administrativa de estado de conexiones WhatsApp

Fecha: 2026-11-27 · Rama `feat/recepcionista` · Base Mi Rubro `513d42f` · Bot
`ef5e329` sin cambios. Solo backend. Sin modelos, migraciones, dependencias ni
cambios de frontend.

## 1. Endpoint

`GET /api/v1/platform-admin/clients/{id}/whatsapp-connections/`

- **Acceso:** igual que la configuración de Recepcionista en Platform Admin.
  `IsAuthenticated + IsPlatformStaff + HasInternalRole` (`superadmin`,
  `operations`).
- **Cliente:** el Business sale solo del id de la ruta. Tiene que ser un
  cliente HQ con Recepcionista no cancelada, sea el servicio principal o uno
  adicional. Si no lo es, 404 `client_not_found`, el mismo contrato que
  `.../receptionist-config/`.
- **Independencia del negocio activo:** no lee la cookie `bid` ni
  `X-Business-Id`.
- **Solo lectura:** acepta solo `GET`/`HEAD`/`OPTIONS`; el resto devuelve 405.
  Responde con `Cache-Control: no-store`, no escribe auditoría y no hace
  ninguna escritura.

## 2. Contrato (ejemplo ficticio)

```json
{
  "contract_version": 1,
  "business_id": 42,
  "evaluated_at": "2026-11-27T15:00:00+00:00",
  "channels": [
    {
      "id": "5f0c…-uuid",
      "provider": "whatsapp_cloud",
      "phone_number_id": "100200300400",
      "waba_id": "900800700600",
      "is_active": true,
      "created_at": "2026-11-20T12:00:00+00:00",
      "deactivated_at": null,
      "agent_instance": {
        "external_id": "recepcion-prod",
        "name": "Recepcionista prod",
        "is_enabled": true,
        "disabled_at": null
      },
      "authorization": {
        "id": "a1b2…-uuid",
        "kind": "business",
        "owned_by_this_business": true,
        "status": "active",
        "expired": false,
        "expires_at": "2027-01-15T00:00:00+00:00",
        "revoked_at": null,
        "created_at": "2026-11-20T12:05:00+00:00",
        "updated_at": "2026-11-20T12:05:00+00:00"
      },
      "local_status": "credential_ready"
    },
    {
      "id": "7d9e…-uuid",
      "provider": "whatsapp_cloud",
      "phone_number_id": "100200300999",
      "waba_id": null,
      "is_active": false,
      "created_at": "2026-10-01T12:00:00+00:00",
      "deactivated_at": "2026-11-20T11:59:00+00:00",
      "agent_instance": { "external_id": "recepcion-prod", "name": "Recepcionista prod", "is_enabled": true, "disabled_at": null },
      "authorization": null,
      "local_status": "channel_not_active"
    }
  ],
  "external_verification": {
    "performed": false,
    "meta_connectivity": "unknown",
    "detail": "Estado local de Mi Rubro; no se consultó a Meta ni al agente."
  }
}
```

- **Sin canales:** `channels: []`.
- **Orden:** activos primero, después por fecha de creación descendente.
- **`waba_id`:** `null` cuando no está informado.
- **`authorization`:** `null` cuando el canal no tiene autorización.
- **`owned_by_this_business`:** `null` si la autorización es de plataforma;
  `false` si el dueño es otro negocio, sin decir cuál.

## 3. Semántica de `local_status`

Cada canal tiene un solo valor: la primera regla que no se cumple, en este
orden. Es **la misma regla** con la que Mi Rubro entrega la credencial al
agente (PROD-04C), más el estado de la instancia.

| Valor | Significado |
|---|---|
| `channel_not_active` | Canal desactivado |
| `whatsapp_authorization_missing` | Canal sin autorización |
| `whatsapp_authorization_owner_mismatch` | La autorización es de otro negocio (estado anómalo, fail-closed) |
| `whatsapp_authorization_revoked` | Revocada localmente |
| `whatsapp_authorization_invalid` | Marcada como rechazada por Meta |
| `whatsapp_authorization_expired` | `expires_at` vencido (el `status` puede seguir `active`) |
| `whatsapp_waba_missing` | Canal sin WABA |
| `agent_instance_disabled` | Credencial lista, pero la instancia del agente está deshabilitada |
| `credential_ready` | Mi Rubro entregaría la credencial guardada al agente |

**Lo que el endpoint no afirma.** `credential_ready` es un estado local. No
dice que el agente esté online ni que WhatsApp funcione. Tampoco que los
permisos en Meta estén confirmados ni que se pueda enviar. No hay número
visible: el modelo no lo guarda. `external_verification` lo dice en la
respuesta: no se llamó a Meta ni al agente. El caso "canal inexistente" es
`channels: []`. Un id de cliente que no existe o no tiene Recepcionista
devuelve 404.

## 4. Infraestructura reutilizada

- **Modelos:** `AgentChannel`, `AgentInstance` y `WhatsAppAuthorization`, tal
  como están: no hay modelo, estado ni migración nuevos.
- **Regla de credencial:** las reglas de `resolve_channel_whatsapp_credential`
  pasaron a una función pura, `channel_credential_problem(channel, now)`, en
  `services/whatsapp_authorizations.py`. La entrega al agente usa esa función
  con los mismos códigos y mensajes. Las suites 04B y 04C pasan sin cambios.
- **Resolución del cliente:** `admin_reception_business(business_id)` en
  `receptionist_config_views.py`. Salió de
  `AdminClientReceptionistConfigView.target_business` y ahora la usan las dos
  vistas.
- **Permisos y patrón de vista:** `IsPlatformStaff`, `HasInternalRole` y el
  patrón de vista de lectura `no-store` de las vistas de consumo IA de
  Platform Admin.

**Nuevo:**
- `apps/leads/whatsapp_connection_views.py`: la vista.
- `admin_whatsapp_connections()`: la serialización, en el mismo servicio.
- La ruta en `platform_admin_urls.py`.

## 5. Seguridad

- **Secretos:** la respuesta no incluye el token, el valor cifrado,
  `AgentCredential` ni secretos HMAC. Nunca se llama a `get_token()` ni a
  `decrypt_agent_secret`; el test lo comprueba haciendo que ambos fallen.
- **Autorización compartida de plataforma:** se devuelve solo el canal del
  cliente consultado. No aparecen los otros canales, sus WABA, sus ids ni
  cuántos negocios la comparten.
- **Dueño ajeno:** no se informa el id del negocio dueño.
- **Logs:** la vista no escribe logs. El test captura el logger raíz durante el
  `GET` y verifica que no aparezca el token ni el texto cifrado.
- **Sin escrituras:** el `GET` no genera ningún
  `INSERT`/`UPDATE`/`DELETE` (capturado con `CaptureQueriesContext`), no crea
  auditoría y no cambia `updated_at`.

## 6. Tests

`apps/leads/tests/test_admin_whatsapp_connections_08e1.py`: 21 tests.
- Contrato:
  - negocio sin canales;
  - canal listo, con solo metadatos y sin claves de conectividad;
  - varios canales activos e inactivos;
  - instancia deshabilitada.
- Autorizaciones:
  - inexistente, vencida, revocada, inválida y sin WABA;
  - el estado coincide con lo que entrega el agente.
- Compartidas y aislamiento:
  - autorización de plataforma compartida sin datos del otro negocio;
  - dueño ajeno no revelado;
  - aislamiento entre negocios.
- Acceso:
  - `operations` puede, `support_agent` y `content_admin` reciben 403, el
    comercio 403 y un anónimo 401/403;
  - Recepcionista como servicio adicional;
  - 404 para cliente sin Recepcionista, cancelada, sucursal o inexistente;
  - independencia de la cookie `bid` y de `X-Business-Id`, incluso con un
    header inválido;
  - métodos de escritura devuelven 405.
- Secretos y efectos:
  - sin secretos en la respuesta ni en los logs;
  - nunca descifra;
  - `GET` sin escrituras.

Corridas sobre PostgreSQL 16 descartable (tmpfs) y Redis descartable, en una
red Docker propia, eliminadas al terminar:

| Corrida | Resultado |
|---|---|
| 08E1 + 04B + 04C + 03B + 08C.1 | 133/133 OK |
| `apps.leads` completo | 1.ª corrida 890/891; 2.ª y 3.ª 891/891 OK |
| `manage.py check` | sin issues |
| `makemigrations --check` | No changes detected |

La falla de la primera corrida completa fue
`test_notifications.HandoffCycleNotificationTests.test_ack_then_new_request_notifies_again`.
Pasa sola tres veces y en las dos corridas completas siguientes. Ese test no
pasa por el código modificado (receptor y notificaciones de handoff).
Queda registrada como falla intermitente preexistente, no investigada en este
slice.

## 7. Riesgos

- R1: `credential_ready` puede leerse como "conectado". El contrato lo evita con
  `external_verification`; el frontend (08E2) tiene que mostrarlo así.
- R2: solo se listan canales del Business HQ. Si existieran canales en
  sucursales, no aparecen.
- R3: un cliente sin Recepcionista vigente, por ejemplo uno que solo tiene
  Turnos IA con canales, devuelve 404. Es la misma regla que la configuración.
- R4: las fechas son las que ya existen en los modelos. No hay "última
  verificación" ni "último mensaje": esos datos no se persisten como estado de
  conexión.
- R5: el `id` de una autorización de plataforma es el mismo en todos los
  negocios que la comparten. No revela nada por sí solo, pero permite
  correlacionar entre clientes a quien ya tiene acceso administrativo a ambos.

## 8. HEAD

`cbbffc3` (endpoint y tests) y este reporte, empujados a
`origin/feat/recepcionista` sin force push. No se avanzó a PROD-08E2.

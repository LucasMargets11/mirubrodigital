# Confirmación de propuesta de turno desde WhatsApp

## Contexto estructurado MiRubro → agente

Fuente principal antes de procesar un mensaje:

`GET /api/v1/integrations/agent/leads/{external_lead_id}/appointment-context/`

Usa la autenticación HMAC del receiver: `X-Agent-Key-Id`, `X-Agent-Timestamp`,
`X-Request-Id` nuevo y `X-Agent-Signature`. Firmar el método `GET`, el path
exacto (con slash final) y el SHA-256 del body vacío. No necesita body ni
parámetros de tenant. MiRubro resuelve el Lead por instancia autenticada e
identificador externo y revalida su canal activo y negocio, igual que el
receiver. Los headers humanos/JWT/cookies no seleccionan el tenant.

```json
{
  "ok": true,
  "external_lead_id": "0c6a1f0e-8a7b-4f0e-9a51-3e2d9b1c7a44",
  "agenda_enabled": true,
  "proposal": {
    "id": "7a359564-7ddb-479b-9301-05441f7bdb55",
    "status": "queued",
    "service_name": "Consulta",
    "professional_name": null,
    "proposed_start_at": "2026-10-23T12:00:00Z",
    "expires_at": "2026-10-23T08:00:00Z"
  },
  "appointment": null
}
```

- `agenda_enabled` (PROD-02D, aditivo): `true` solo si el negocio opera Turnos
  hoy (suscripción Turnos con acceso efectivo, enforcement y lifecycle;
  fail-closed ante error). Con `false`, `proposal` y `appointment` son siempre
  `null` (Recepcionista IA sin agenda, o Turnos suspendido/cancelado/no
  iniciado): el bot no debe ofrecer ni acreditar turnos. Un bot que ignore el
  campo sigue viendo ambos bloques en `null`. MiRubro además ignora la señal
  `proposal_confirmation` (`agenda_unavailable`) sin acceso a Turnos.
- `proposal` solo expone `queued` vigente, con snapshots de nombres; aplica
  expiración lazy mediante `current_proposal`. `pending_delivery` se omite
  (`null`): todavía no fue aceptada por el agente. También son `null`
  `expired`, `superseded`, `converted` y `delivery_failed`.
- `appointment` sale exclusivamente de `Lead.appointment`, con forma
  `{"id": "uuid", "status": "confirmed", "start_at": "2026-10-23T12:00:00Z"}`.
  Se conserva el estado real, incluso si está cancelado: existencia no equivale
  a confirmación vigente; el bot debe interpretar `status`.
- Si hay Appointment vinculado, `proposal` es `null`; la reserva real tiene
  precedencia. Si no existe ninguno, ambos campos son `null`.
- Una Proposal es una **oferta**, nunca una reserva. Solo el Appointment real
  y su estado permiten hablar de un turno confirmado. No inferirlo de mensajes
  ni de la señal del paciente.
- El GET devuelve `Cache-Control: no-store`. Consultarlo antes de cada turno
  del bot; no usar una respuesta anterior como fuente permanente.
- Lead inexistente o de otra instancia: `404 lead_not_found`. Canal
  deshabilitado/reasignado: `403 channel_disabled`; negocio inactivo:
  `403 business_inactive`; inconsistencia entre negocio y canal:
  `409 business_mismatch`. UUID malformado: `404` del router.
  Otros errores conservan el envelope del receiver, HMAC, flag y throttle.

La respuesta del `PUT lead.sync` también agrega los mismos bloques `agenda_enabled`,
`proposal` y `appointment` para `created`, `applied`, `duplicate` y `stale`; reflejan el
estado actual de MiRubro, no el snapshot viejo del bot. El GET sigue siendo
la fuente principal. El hash/idempotencia del sync cubre el **input**, no
estos bloques de respuesta.

## Correlación explícita agente → MiRubro

Cuando el agente interpreta que el paciente responde afirmativamente a una
propuesta identificada por el contexto, incluye en el siguiente `lead.sync`:

```json
{
  "proposal_confirmation": {
    "proposal_id": "7a359564-7ddb-479b-9301-05441f7bdb55",
    "intent": "confirm",
    "message_id": "whatsapp-message-id"
  },
  "messages": [
    {
      "external_message_id": "whatsapp-message-id",
      "role": "user",
      "sender": "patient",
      "text": "Sí, dale",
      "sent_at": "2026-10-22T12:00:00Z",
      "status": null
    }
  ]
}
```

`proposal_confirmation` es opcional. Dentro del bloque, `proposal_id` (UUID),
`intent` (solo `confirm`) y `message_id` son obligatorios. No hay fallback de
"propuesta activa actual" ni alias. Bloque malformado: `400 validation_error`.

MiRubro busca la propuesta **exacta**, del mismo Business y Lead; la identidad
inmutable del Lead valida la conversación. Debe estar `queued`, sin Appointment
propio, con `expires_at > now`, y el Lead no debe estar cerrado ni tener
Appointment real.

`message_id` identifica `LeadAgentMessage.external_message_id` del mismo Lead,
con `sender=patient` y `role=user`. Puede llegar en `messages` de este sync
o estar ya persistido. No se copia el texto a la propuesta.

Temporalidad: el `sent_at` del paciente debe ser estrictamente posterior al
`sent_at` del mensaje de recepción (`sender=staff`, `role=assistant`)
identificado por `proposal.staff_message.message_id`. Si ese mensaje aún no
está sincronizado, se usa `staff_message.delivered_at`: es el acuse de encolado
del agente, **no prueba de entrega en WhatsApp**. Sin ninguna referencia
temporal verificable, se ignora la señal. Además,
`patient.sent_at <= proposal.expires_at`.

Si falla alguna condición de correlación/estado/temporalidad, se ignora solo
la señal, el sync sigue aceptándose y se registra un motivo técnico sin PII.
Reintentos/versiones repetidas no duplican la intención del mismo
`proposal_id`/`message_id`. `proposal_id` participa del hash de payload; cambiarlo
en la misma versión genera `409 version_conflict`.

La señal no crea ni confirma una reserva, no convierte la propuesta y no ocupa
el horario. La reserva solo se crea cuando una persona autorizada ejecuta
**Confirmar turno** en MiRubro. La salida CRM sigue llamándose
`patient_confirmation`; no es un segundo nombre de entrada al receiver.

## Compatibilidad

Contract V1 se mantiene: GET nuevo y bloques de respuesta aditivos/nullable.
Agentes que no envían la señal siguen funcionando. La señal aún no desplegada
debe actualizarse para enviar `proposal_id` antes de usarla; no se conserva un
modo legacy sin ese campo, aliases ni una versión paralela. Este cambio solo
implementa MiRubro; el bot debe integrar la consulta y la señal posteriormente.

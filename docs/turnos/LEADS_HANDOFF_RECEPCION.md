# Derivación del recepcionista IA a recepción (primer cliente)

Alcance: el bot junta los datos mínimos, genera el lead y lo entrega a
recepción; recepción toma el chat y gestiona el turno a mano. Agenda
automática, propuestas, recordatorios y cobro de excedentes quedan como están.

## Contrato mínimo del lead

| Dato | Tipo | Origen |
|---|---|---|
| Teléfono (`phone_e164`) | obligatorio | canal de WhatsApp, nunca se pregunta |
| Motivo (`reason`) | obligatorio | palabras del cliente |
| Preferencia de día/horario (`preferred_time`) | obligatorio | preferencia del cliente, no un turno |
| Urgencia (`urgency`) | derivado | síntomas o modelo; solo sube |
| Nombre (`patient_name`) | opcional | solo si el cliente lo dijo (si no, perfil de WhatsApp) |
| Resumen (`summary`) | opcional | para recepción |

Deriva con: motivo + preferencia completos, urgencia, o pedido explícito de
hablar con una persona.

## Estados en el panel

| Bot (agente) | `conversation_control` | Panel |
|---|---|---|
| atendiendo | `active`, `handoff_pending=false` | "Bot habilitado" · Tomar conversación |
| derivado, sin tomar | `active`, `handoff_pending=true` | "Pendiente de recepción · bot pausado" · **Tomar chat** (no hay Reactivar) |
| tomado | `taken` | "Tomada por X" · composer para responder · Reactivar bot (con confirmación) |
| reactivado | `active` con `released_at` posterior a la derivación | "Bot habilitado" |

"Reactivar bot" (antes "Reanudar bot") es el release: el bot vuelve a
responder automáticamente los mensajes nuevos. Solo existe desde `taken` y
pide confirmación; desde "pendiente de recepción" no se ofrece, así ninguna
acción de atención humana reactiva el bot sin querer.

## Despliegue

Orden sugerido: MiRubro (migración `leads.0010`, ignora el campo hasta que
llegue) → agente (migración `20261112120000_lead_handoff_paused_at`,
`prisma generate`). El campo es aditivo y solo se envía cuando existe: las
revisiones viejas conservan bytes y `payload_hash`.

## Prueba manual (número de prueba, cuando se habilite la validación)

Requisitos: agente con `WHATSAPP_REPLY_MODE=openai`, `MIRUBRO_SYNC_ENABLED`,
`AI_USAGE_METERING_ENABLED`, `MIRUBRO_TAKEOVER_ENABLED` y
`MIRUBRO_HUMAN_MESSAGES_ENABLED` en `true`; MiRubro con
`AGENT_INTEGRATION_ENABLED`, `AI_USAGE_METERING_ENABLED` y
`AGENT_TAKEOVER_ENABLED`; Celery worker + beat; un número de prueba que
nunca escribió.

1. Desde el número de prueba: "hola, quiero un turno". Esperado: respuesta
   del modelo (no "tuve un inconveniente"). Logs del agente: `First contact:
   lead … acknowledged`; en MiRubro aparece el lead en `/app/turnos/leads`.
2. Responder motivo ("limpieza") y preferencia ("el viernes a la tarde").
   Esperado: despedida fija "Listo… Dejé registrada tu consulta por
   limpieza, con tu preferencia "el viernes a la tarde". A partir de ahora la
   sigue recepción por este chat…". Nunca "turno confirmado".
3. Panel: el lead figura "Pendiente de recepción · bot pausado" y con
   atención pendiente; llega el aviso interno (campana). Detalle: datos y
   conversación completos.
4. Desde el número: "¿me confirmás?". Esperado: el bot no responde; el
   mensaje aparece en el detalle del mismo lead.
5. Reiniciar el agente y repetir el paso 4: sigue sin responder.
6. Panel: "Tomar chat" → "Tomada por vos"; escribir una respuesta en el
   composer. Esperado: llega al teléfono; el estado del mensaje pasa a
   enviado/entregado en el historial.
7. (Opcional) "Reactivar bot" → confirmar → el próximo mensaje lo responde
   el bot.
8. Repetir el paso 1 con MiRubro detenido: el agente no llama al modelo,
   deja el mensaje pendiente y reintenta (logs `left pending, retry n/4`);
   al levantar MiRubro, se responde.

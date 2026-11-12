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

## Casos borde cerrados

**Reintentos agotados (MiRubro no confirma el lead nuevo).** El batch espera el
ACK hasta 8 s y se difiere hasta 4 veces cada 30 s. Agotados los intentos:
no se llama al modelo ni se marca el batch como respondido. El lead registra
`agent_error` (revisión en el outbox, que sigue reintentando con backoff
persistido hasta 7 días) y el cliente recibe una sola vez "Quedó registrado;
si podés, escribime de nuevo…", que no anuncia ninguna derivación. El
procesamiento se recupera:
- con el próximo mensaje del cliente: el batch nuevo incluye los mensajes
  pendientes y repite el ciclo;
- al reiniciar el bot: `recoverPendingBatches` reprograma los pendientes de
  menos de `RECOVERY_MAX_AGE_MS`; los más viejos quedan como
  `recovery_dropped` (marcados, nunca borrados) para que recepción los vea;
- y cuando MiRubro vuelve, el outbox entrega el lead con sus mensajes y el
  `agent_error` (requiere atención).
Los contadores de reintento viven en memoria; tras un reinicio los
reconstruye la recuperación desde los mensajes pendientes en la base.

**Mensaje después de `LEAD_IDLE_HOURS` con el chat pausado.** La pausa es de
la conversación, no del lead: abrir un lead nuevo por inactividad no
reactiva al bot. El lead anterior se cierra (`idle`) y el nuevo se crea con
el mensaje. Como se abrió con el chat ya pausado, se sincroniza como
derivado: `handoff_paused_at` + motivo `agent_handoff_required`. Así
MiRubro marca atención pendiente, genera el aviso interno y muestra
"Pendiente de recepción · bot pausado" o "Tomada por X" si el chat seguía
tomado. Solo "Reactivar bot" vuelve a habilitar respuestas automáticas.

## Levantar el entorno local (base de desarrollo)

MiRubro (worktree `D:UsuarioDesktopmirubrodigital-lead-handoff`):
1. `docker compose -f infra/docker-compose.yml up -d postgres redis`
2. `docker compose -f infra/docker-compose.yml up -d api celery-worker celery-beat web`.
   El `api` corre `python manage.py migrate` al arrancar, lo que aplica
   `leads.0010` en la base de desarrollo. Se puede forzar con
   `docker compose -f infra/docker-compose.yml exec api python manage.py migrate leads`.
3. Dar de alta el agente y el canal del negocio de prueba (una vez):
   `docker compose -f infra/docker-compose.yml exec api python manage.py provision_agent --external-id <instancia> --key-id <key> --business-id <id> --phone-number-id <phone_number_id> --secret-stdin`.

Bot (worktree `D:BOT RECEPCIONISTAagenterecep-lead-handoff`):
1. `docker compose up -d postgres` (Postgres de desarrollo en :5433).
2. `npm ci`, `npx prisma generate` y `npx prisma migrate deploy` (con
   `DATABASE_URL` apuntando a esa base), que aplican
   `20261112120000_lead_handoff_paused_at`.
3. `npm run start:dev` con `PORT=3001` (el panel usa :3000) y un túnel HTTPS
   hacia :3001 para el webhook de Meta.

Notas: los nombres de contenedor son fijos (`mirubro-*`, `dental-bot-postgres`):
bajá primero los del checkout principal. Ambos worktrees usan los mismos
volúmenes de desarrollo que sus checkouts principales, así que las
migraciones agregan una columna nullable que el código anterior ignora.

Orden en otros entornos: primero MiRubro (acepta e ignora el campo hasta
que llegue) y después el agente. El campo es aditivo y solo se envía cuando
existe, así que las revisiones viejas conservan bytes y `payload_hash`.

### Variables (solo nombres; los valores van en los `.env` locales)

- **MiRubro `services/api/.env`:**
  - `DEBUG=True` (permite `http` hacia el agente);
  - `AGENT_INTEGRATION_ENABLED`, `AGENT_SECRET_ENCRYPTION_KEY`,
    `AI_USAGE_METERING_ENABLED`;
  - `AGENT_TAKEOVER_ENABLED`, `AGENT_TAKEOVER_BASE_URL` (URL del bot),
    `AGENT_TAKEOVER_KEY_ID`, `AGENT_TAKEOVER_SECRET`.
- **Bot `.env`:**
  - `NODE_ENV=development` (permite `http` hacia MiRubro), `PORT`,
    `DATABASE_URL`;
  - `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ACCESS_TOKEN`,
    `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_WABA_ID`, `WHATSAPP_APP_SECRET`,
    `WHATSAPP_REPLY_MODE=openai`;
  - `OPENAI_API_KEY`, `OPENAI_MODEL`, `AI_USAGE_METERING_ENABLED=true`;
  - `MIRUBRO_SYNC_ENABLED=true`, `MIRUBRO_BASE_URL`,
    `MIRUBRO_AGENT_INSTANCE_ID`, `MIRUBRO_BUSINESS_ID`,
    `MIRUBRO_AGENT_KEY_ID`, `MIRUBRO_AGENT_SECRET`,
    `MIRUBRO_CONVERSATION_ID_KEY`;
  - `MIRUBRO_TAKEOVER_ENABLED=true`, `MIRUBRO_HUMAN_MESSAGES_ENABLED=true`,
    `MIRUBRO_INBOUND_KEY_ID`, `MIRUBRO_INBOUND_SECRET` (pareja de
    `AGENT_TAKEOVER_*`);
  - para la prueba, `LEAD_IDLE_HOURS` (bajarlo, p. ej. a 1) y
    `RECOVERY_MAX_AGE_MS`.

## Validación manual (un recorrido, número de prueba que nunca escribió)

| # | Acción | Resultado esperado |
|---|---|---|
| 1 | Desde el número: "hola, quiero un turno". | Responde el modelo (no "tuve un inconveniente"). Log del bot: `First contact: lead … acknowledged`. El lead aparece en `/app/turnos/leads` con el mensaje. |
| 2 | Enviar motivo ("limpieza") y preferencia ("el viernes a la tarde"). | Despedida fija: "Listo… Dejé registrada tu consulta por limpieza, con tu preferencia "el viernes a la tarde". A partir de ahora la sigue recepción por este chat…". Nunca "turno confirmado". |
| 3 | Mirar el panel. | Llega el aviso interno (campana). El lead tiene atención pendiente y figura "Pendiente de recepción · bot pausado", con datos y conversación completos. Solo se ofrece "Tomar chat". |
| 4 | "Tomar chat" → confirmar, y responder desde el composer. | "Tomada por vos". El mensaje llega al teléfono y su estado pasa a enviado/entregado en el historial. |
| 5 | Desde el número: "¿me confirmás?". | El bot no responde. El mensaje aparece en el mismo lead. |
| 6 | Reiniciar el bot y repetir el paso 5. | Sigue sin responder (log `RECOVERY … left to the human` si había pendientes). |
| 7 | Esperar más de `LEAD_IDLE_HOURS` y escribir de nuevo. | El bot no responde. Aparece un lead nuevo con atención pendiente y aviso, "Tomada por vos" (o "Pendiente de recepción" si se liberó el control), y el anterior queda cerrado. |
| 8 | Detener `api` de MiRubro y escribir desde **otro** número de prueba. | No se llama al modelo. Log `left pending, retry n/4`. Tras ~2 min llega una sola vez "Quedó registrado; si podés, escribime de nuevo…". |
| 9 | Levantar `api` y escribir otra vez desde ese número. | El lead llega a MiRubro con sus mensajes y `agent_error` (atención). El bot responde considerando el mensaje anterior y el nuevo. |
| 10 | (Opcional) En un chat tomado: "Reactivar bot" → confirmar. | El próximo mensaje lo responde el bot. |

# Métricas operativas de WhatsApp (PROD-02E4C)

Servicio interno de solo lectura `apps.leads.services.whatsapp_metrics.whatsapp_metrics(business, start=, end=)`, con contrato v1. Todavía no tiene endpoint: lo va a consumir Platform Admin en PROD-02E4D.

Se construye solo con lo que el agente ya sincroniza por `lead.sync`. No hay copia propia de mensajes, ni callbacks de Meta en Mi Rubro (los webhooks de estado los recibe el agente), ni tablas o migraciones nuevas.

## Fuentes y cobertura
| Fuente | Aporta | Cobertura |
|---|---|---|
| `LeadAgentMessage` | Mensajes entrantes (`patient`) y salientes (`bot`, `staff`), `sent_at` y último estado de entrega | **Parcial**. Solo mensajes del episodio de cada Lead (entre `openedAt` y `closedAt`), hasta 500 por lead. Faltan las conversaciones que nunca generaron Lead, los mensajes fuera de un episodio y todo lo ocurrido con el sync apagado. |
| `LeadAgentState` | Conversación, canal original del episodio y handoff (`handoff_requested_at`, `handoff_paused_at`) | Un registro por episodio, con la primera solicitud de handoff del episodio. |
| `LeadActivity` | Tomas y reanudaciones humanas aplicadas | Completa para las acciones hechas desde Mi Rubro. |
| `LeadStaffMessage` | Mensajes que recepción pidió enviar | Estado del outbox hacia el agente (encolado o fallido). **No** es la entrega por WhatsApp; esa llega por `LeadAgentMessage` con `sender=staff`. |

## Definiciones
- **`totals.messages`**: mensajes registrados únicos en `[start, end)` según `sent_at`.
  - Para los entrantes, `sent_at` es el timestamp de WhatsApp. Para los salientes, es la aceptación de Meta o, si no se conoce, la hora en que se guardaron en el agente.
- **`inbound` / `outbound`**: `inbound` son los mensajes de `patient`. `outbound` son los de `bot` más los de `staff`.
- **`ai_generated` / `automated_non_ai`**: siempre `null`. El agente marca como `bot` tanto las respuestas de IA como los mensajes automáticos, así que no se infieren.
- **`outbound_status`**: cada saliente cuenta una sola vez, con su **último estado sincronizado**, no con el estado histórico al cierre del rango.
  - `unknown` significa que el agente no informó estado.
  - Los mensajes de un episodio cerrado conservan el estado de su último sync.
- **`conversations.with_activity`**: `external_conversation_id` distintos con al menos un mensaje en el rango.
- **`leads_with_activity`**: episodios con al menos un mensaje en el rango.
- **`handoffs`**: `requested` y `bot_paused_for_reception` salen de los timestamps del episodio. `takeovers_applied` y `releases_applied` salen de `LeadActivity`.
- **`daily`**: un bucket por día en la zona horaria del Business, cubriendo todo el rango.
- **Desconocido frente a cero**: si el Business no tiene `AgentChannel` o nunca se sincronizó un Lead (`available: false`), las métricas derivadas del agente valen `null`. Con sync observado, un 0 es un cero real dentro de la cobertura.

## Deduplicación y aislamiento
- **Identidad del mensaje**: `(agent_instance, external_message_id)`, donde el id es el del mensaje en el agente.
  - Un mismo mensaje en dos episodios (por ejemplo, en el borde de la ventana) cuenta una vez, con su estado más avanzado: `read`, `delivered`, `sent`, `failed` o `null`, en ese orden.
  - Los reintentos y reenvíos del sync son upserts y nunca duplican.
- **Aislamiento**: todo se filtra por `lead.business` **y** `channel.business`. Un número reasignado a otro Business no mueve el histórico: cada episodio conserva su canal original.
- **Rango**: `start` y `end` tienen que tener zona horaria, `end > start` y el rango no puede superar 92 días.
- **Lectura**: no hay locks ni escrituras.

## Fuera de alcance
- Costos de Meta y conversaciones facturables.
- Consumo comercial de IA: sesiones y cargos van por `ai_usage`.
- Telemetría de OpenAI: va por `AgentAIExecution`.

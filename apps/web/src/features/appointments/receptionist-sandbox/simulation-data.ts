// TURNOS RECEPCIONISTA 01: fixture local de la conversación de ejemplo.
// Sin llamadas a API/OpenAI — texto fijo para la simulación automática.

import type { ScenarioFixture } from './types';

export const DEMO_CONTACT_PHONE = '+54 9 11 2345-6789';

export const RESERVAR_TURNO_SCENARIO: ScenarioFixture = {
  id: 'reservar-turno',
  label: 'Reservar turno',
  messages: [
    {
      id: 'msg-1',
      role: 'customer',
      text: 'Hola, quería sacar un turno para una limpieza.',
      intelligenceEvents: [
        { type: 'intent_detected', value: 'book_appointment', confidence: 0.98 },
        { type: 'field_detected', field: 'service', value: 'Limpieza' },
        { type: 'phase_changed', value: 'collecting_identity' },
        {
          type: 'step_updated',
          id: 'message_received',
          label: 'Mensaje recibido',
          status: 'completed',
        },
        {
          type: 'step_updated',
          id: 'intent_detected',
          label: 'Intención detectada',
          status: 'completed',
        },
        {
          type: 'step_updated',
          id: 'customer_identified',
          label: 'Identificando cliente',
          status: 'active',
        },
        {
          type: 'step_updated',
          id: 'preferred_day',
          label: 'Consultando preferencia de fecha',
          status: 'pending',
        },
      ],
      mirubroEvents: [{ type: 'inquiry_received' }],
    },
    {
      id: 'msg-2',
      role: 'receptionist',
      text: '¡Hola! Claro. Soy el asistente virtual de la agenda. ¿Me decís tu nombre?',
      typingPhase: 'collecting_identity',
    },
    {
      id: 'msg-3',
      role: 'customer',
      text: 'Lucía.',
      intelligenceEvents: [
        { type: 'field_detected', field: 'name', value: 'Lucía' },
        { type: 'phase_changed', value: 'collecting_availability' },
        {
          type: 'step_updated',
          id: 'customer_identified',
          label: 'Cliente identificado',
          status: 'completed',
        },
        {
          type: 'step_updated',
          id: 'preferred_day',
          label: 'Consultando preferencia de fecha',
          status: 'active',
        },
      ],
      mirubroEvents: [{ type: 'contact_identified', phone: DEMO_CONTACT_PHONE }],
    },
    {
      id: 'msg-4',
      role: 'receptionist',
      text: 'Perfecto, Lucía. ¿Qué día te gustaría venir?',
      typingPhase: 'collecting_availability',
    },
    {
      id: 'msg-5',
      role: 'customer',
      text: 'Mañana por la tarde.',
      intelligenceEvents: [
        { type: 'field_detected', field: 'preferredDay', value: 'Mañana' },
        { type: 'field_detected', field: 'preferredTimeRange', value: 'Tarde' },
        { type: 'phase_changed', value: 'collecting_availability' },
        {
          type: 'step_updated',
          id: 'preferred_day',
          label: 'Preferencia detectada',
          status: 'completed',
        },
        {
          type: 'step_updated',
          id: 'availability',
          label: 'Buscando disponibilidad',
          status: 'active',
        },
      ],
      mirubroEvents: [{ type: 'lead_qualified' }],
    },
    {
      id: 'msg-6',
      role: 'receptionist',
      text: 'Tengo disponibilidad a las 16:00 y a las 17:30. ¿Cuál te sirve más?',
      typingPhase: 'collecting_availability',
      intelligenceEvents: [
        { type: 'phase_changed', value: 'offering_slots' },
        {
          type: 'step_updated',
          id: 'availability',
          label: 'Disponibilidad consultada',
          status: 'completed',
        },
        {
          type: 'step_updated',
          id: 'selection',
          label: 'Esperando selección',
          status: 'active',
        },
      ],
      mirubroEvents: [{ type: 'availability_consulted' }],
    },
    {
      id: 'msg-7',
      role: 'customer',
      text: '17:30.',
      intelligenceEvents: [
        { type: 'field_detected', field: 'selectedSlot', value: '17:30' },
        { type: 'phase_changed', value: 'confirming' },
        {
          type: 'step_updated',
          id: 'selection',
          label: 'Horario seleccionado',
          status: 'completed',
        },
        {
          type: 'step_updated',
          id: 'confirming',
          label: 'Confirmando turno',
          status: 'active',
        },
      ],
      mirubroEvents: [{ type: 'slot_selected' }],
    },
    {
      id: 'msg-8',
      role: 'receptionist',
      text: 'Perfecto. Te reservé la limpieza para mañana a las 17:30.',
      typingPhase: 'confirming',
      intelligenceEvents: [
        { type: 'phase_changed', value: 'completed' },
        {
          type: 'step_updated',
          id: 'confirming',
          label: 'Conversación procesada',
          status: 'completed',
        },
        {
          type: 'step_updated',
          id: 'required_data',
          label: 'Datos necesarios obtenidos',
          status: 'completed',
        },
      ],
      mirubroEvents: [{ type: 'appointment_confirmed' }],
    },
  ],
};

export const RECEPTIONIST_SCENARIOS: ScenarioFixture[] = [RESERVAR_TURNO_SCENARIO];

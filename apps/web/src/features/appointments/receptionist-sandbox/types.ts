// TURNOS RECEPCIONISTA 01: tipos del sandbox de simulación del Recepcionista IA.
// Slice local, sin backend ni persistencia — todo vive en memoria del cliente.

export type ChatRole = 'customer' | 'receptionist';

export type ReceptionistIntent =
  | 'unknown'
  | 'book_appointment'
  | 'reschedule'
  | 'cancel'
  | 'general_question';

export type ReceptionistPhase =
  | 'idle'
  | 'understanding'
  | 'collecting_identity'
  | 'collecting_service'
  | 'collecting_availability'
  | 'offering_slots'
  | 'confirming'
  | 'completed';

export type IntelligenceField =
  | 'name'
  | 'service'
  | 'preferredDay'
  | 'preferredTimeRange'
  | 'selectedSlot';

export type IntelligenceStep = {
  id: string;
  label: string;
  status: 'pending' | 'active' | 'completed';
};

export type IntelligenceSnapshot = {
  intent: ReceptionistIntent;
  phase: ReceptionistPhase;
  confidence?: number;
  extracted: Partial<Record<IntelligenceField, string>>;
  steps: IntelligenceStep[];
};

export type IntelligenceEvent =
  | { type: 'intent_detected'; value: ReceptionistIntent; confidence?: number }
  | { type: 'field_detected'; field: IntelligenceField; value: string }
  | { type: 'phase_changed'; value: ReceptionistPhase }
  | {
      type: 'step_updated';
      id: string;
      label: string;
      status: IntelligenceStep['status'];
    };

export type MirubroEvent =
  | { type: 'inquiry_received' }
  | { type: 'contact_identified'; phone: string }
  | { type: 'lead_qualified' }
  | { type: 'availability_consulted' }
  | { type: 'slot_selected' }
  | { type: 'appointment_confirmed' };

export type MirubroActivity = {
  id: MirubroEvent['type'];
  label: string;
  status: 'pending' | 'active' | 'completed';
};

export type MirubroSnapshot = {
  contact: {
    status: 'empty' | 'identified';
    name?: string;
    phone?: string;
    source?: 'whatsapp';
  };
  lead: {
    status: 'empty' | 'new' | 'qualified' | 'converted';
    intent?: 'book_appointment';
    service?: string;
    preferredDay?: string;
    preferredTimeRange?: string;
    source?: 'whatsapp';
  };
  booking: {
    status: 'empty' | 'pending' | 'confirmed';
    service?: string;
    day?: string;
    slot?: string;
  };
  events: MirubroActivity[];
};

export type ScenarioMessageFixture = {
  id: string;
  role: ChatRole;
  text: string;
  intelligenceEvents?: IntelligenceEvent[];
  mirubroEvents?: MirubroEvent[];
  typingPhase?: ReceptionistPhase;
  /**
   * Demora (ms) antes de que aparezca un mensaje del cliente, simulando que
   * está escribiendo/enviando. Solo se usa cuando `role === 'customer'`.
   */
  delayMs?: number;
  /**
   * Duración (ms) del indicador de "escribiendo…" antes de que aparezca la
   * respuesta del recepcionista. Solo se usa cuando `role === 'receptionist'`.
   */
  typingMs?: number;
};

export type ChatMessage = ScenarioMessageFixture & {
  /** Timestamp (epoch ms) en que el mensaje se volvió visible en el chat. */
  revealedAt: number;
};

export type ScenarioId = 'reservar-turno';

export type ScenarioFixture = {
  id: ScenarioId;
  label: string;
  messages: ScenarioMessageFixture[];
};

export type SimulationStatus = 'idle' | 'running' | 'paused' | 'completed';

export type SimulationSnapshot = {
  status: SimulationStatus;
  messages: ChatMessage[];
  isTyping: boolean;
  intelligence: IntelligenceSnapshot;
  mirubro: MirubroSnapshot;
};

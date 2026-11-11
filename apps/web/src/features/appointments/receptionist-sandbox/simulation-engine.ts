// TURNOS RECEPCIONISTA 01: motor local de simulación de la conversación.
//
// Reglas duras de este slice:
// - Ningún `fetch`/request: todo el estado vive en memoria, avanzado por un
//   único scheduler (`setTimeout` recursivo) con cleanup explícito.
// - Nada de polling ni websockets.
// - `SimulationEngine` es agnóstico de React (fácil de testear con fake
//   timers); `useReceptionistSimulation` lo conecta al ciclo de vida de un
//   componente.

import { useEffect, useState } from 'react';

import type {
  ChatMessage,
  IntelligenceEvent,
  IntelligenceSnapshot,
  MirubroEvent,
  MirubroSnapshot,
  ScenarioFixture,
  ScenarioMessageFixture,
  SimulationSnapshot,
  SimulationStatus,
} from './types';

export const MESSAGE_SETTLE_MS = 700;
export const SNAPSHOT_DELAY_MS = 500;

export function getMessageDelayMs(message: ScenarioMessageFixture): number {
  if (message.role === 'customer') {
    return message.delayMs ?? 900 + Math.min(message.text.length * 18, 900);
  }
  return message.typingMs ?? 1400 + Math.min(message.text.length * 24, 1800);
}

type Listener = (snapshot: SimulationSnapshot) => void;

function initialSnapshot(): SimulationSnapshot {
  return {
    status: 'idle',
    messages: [],
    isTyping: false,
    intelligence: {
      intent: 'unknown',
      phase: 'idle',
      extracted: {},
      steps: [{ id: 'message_received', label: 'Esperando mensaje', status: 'active' }],
    },
    mirubro: {
      contact: { status: 'empty' },
      lead: { status: 'empty' },
      booking: { status: 'empty' },
      events: [],
    },
  };
}

function applyIntelligenceEvents(
  snapshot: IntelligenceSnapshot,
  events: IntelligenceEvent[],
): IntelligenceSnapshot {
  let next = snapshot;

  for (const event of events) {
    if (event.type === 'intent_detected') {
      next = {
        ...next,
        intent: event.value,
        ...(event.confidence === undefined ? {} : { confidence: event.confidence }),
      };
    } else if (event.type === 'field_detected') {
      next = {
        ...next,
        extracted: { ...next.extracted, [event.field]: event.value },
      };
    } else if (event.type === 'phase_changed') {
      next = { ...next, phase: event.value };
    } else {
      const stepIndex = next.steps.findIndex((step) => step.id === event.id);
      const steps = [...next.steps];
      const step = { id: event.id, label: event.label, status: event.status };
      if (stepIndex === -1) steps.push(step);
      else steps[stepIndex] = step;
      next = { ...next, steps };
    }
  }

  return next;
}

const MIRUBRO_EVENT_LABELS: Record<MirubroEvent['type'], string> = {
  inquiry_received: 'Consulta recibida',
  contact_identified: 'Contacto identificado',
  lead_qualified: 'Lead calificado',
  availability_consulted: 'Disponibilidad consultada',
  slot_selected: 'Horario seleccionado',
  appointment_confirmed: 'Turno confirmado',
};

function requiredField(
  intelligence: IntelligenceSnapshot,
  field: keyof IntelligenceSnapshot['extracted'],
): string {
  const value = intelligence.extracted[field];
  if (!value) throw new Error(`Missing intelligence field "${field}" for MiRubro event.`);
  return value;
}

function applyMirubroEvents(
  snapshot: MirubroSnapshot,
  events: MirubroEvent[],
  intelligence: IntelligenceSnapshot,
): MirubroSnapshot {
  let next = snapshot;

  for (const event of events) {
    const activity = {
      id: event.type,
      label: MIRUBRO_EVENT_LABELS[event.type],
      status: event.type === 'appointment_confirmed' ? 'completed' : 'active',
    } as const;
    const updatedEvents = next.events.map((item) =>
      item.status === 'active' ? { ...item, status: 'completed' as const } : item,
    );

    if (event.type === 'inquiry_received') {
      if (intelligence.intent !== 'book_appointment')
        throw new Error('MiRubro inquiry requires a booking intent.');
      next = {
        ...next,
        lead: {
          ...next.lead,
          status: 'new',
          intent: intelligence.intent,
          service: requiredField(intelligence, 'service'),
          source: 'whatsapp',
        },
      };
    } else if (event.type === 'contact_identified') {
      next = {
        ...next,
        contact: {
          status: 'identified',
          name: requiredField(intelligence, 'name'),
          phone: event.phone,
          source: 'whatsapp',
        },
      };
    } else if (event.type === 'lead_qualified') {
      next = {
        ...next,
        lead: {
          ...next.lead,
          status: 'qualified',
          service: requiredField(intelligence, 'service'),
          preferredDay: requiredField(intelligence, 'preferredDay'),
          preferredTimeRange: requiredField(intelligence, 'preferredTimeRange'),
        },
      };
    } else if (event.type === 'availability_consulted') {
      next = {
        ...next,
        booking: {
          status: 'pending',
          service: requiredField(intelligence, 'service'),
          day: requiredField(intelligence, 'preferredDay'),
        },
      };
    } else if (event.type === 'slot_selected') {
      next = {
        ...next,
        booking: {
          ...next.booking,
          status: 'pending',
          slot: requiredField(intelligence, 'selectedSlot'),
        },
      };
    } else {
      next = {
        ...next,
        lead: { ...next.lead, status: 'converted' },
        booking: { ...next.booking, status: 'confirmed' },
      };
    }

    next = { ...next, events: [...updatedEvents, activity] };
  }

  return next;
}

export class SimulationEngine {
  private readonly scenario: ScenarioFixture;
  private readonly listeners = new Set<Listener>();
  private snapshot: SimulationSnapshot = initialSnapshot();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private nextAction: (() => void) | null = null;
  private remainingMs = 0;
  private dueAt = 0;

  constructor(scenario: ScenarioFixture) {
    this.scenario = scenario;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.snapshot);
    return () => {
      this.listeners.delete(listener);
    };
  }

  getSnapshot(): SimulationSnapshot {
    return this.snapshot;
  }

  start(): void {
    this.clearTimer();
    this.nextAction = null;
    this.emit({
      status: 'running',
      messages: [],
      isTyping: false,
      intelligence: initialSnapshot().intelligence,
      mirubro: initialSnapshot().mirubro,
    });
    this.scheduleStep(0);
  }

  pause(): void {
    if (this.snapshot.status !== 'running') return;
    this.remainingMs = Math.max(0, this.dueAt - Date.now());
    this.clearTimer();
    this.emit({ status: 'paused' });
  }

  resume(): void {
    if (this.snapshot.status !== 'paused') return;
    this.emit({ status: 'running' });
    if (this.nextAction) this.scheduleAction(this.nextAction, this.remainingMs);
  }

  restart(): void {
    this.clearTimer();
    this.nextAction = null;
    this.emit(initialSnapshot());
  }

  /** Limpia timers y listeners. Debe llamarse al desmontar. */
  dispose(): void {
    this.clearTimer();
    this.nextAction = null;
    this.listeners.clear();
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private emit(patch: Partial<SimulationSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const listener of this.listeners) listener(this.snapshot);
  }

  private scheduleAction(action: () => void, delayMs: number): void {
    this.nextAction = action;
    this.remainingMs = delayMs;
    this.dueAt = Date.now() + delayMs;
    this.timer = setTimeout(() => {
      this.timer = null;
      this.nextAction = null;
      action();
    }, delayMs);
  }

  private scheduleStep(index: number): void {
    const message = this.scenario.messages[index];

    if (!message) {
      this.emit({ status: 'completed', isTyping: false });
      return;
    }

    if (message.role === 'customer') {
      this.scheduleAction(() => this.revealMessage(message, index), getMessageDelayMs(message));
      return;
    }

    const intelligence = message.typingPhase
      ? applyIntelligenceEvents(this.snapshot.intelligence, [
          { type: 'phase_changed', value: message.typingPhase },
        ])
      : this.snapshot.intelligence;
    this.emit({ isTyping: true, intelligence });
    this.scheduleAction(() => this.revealMessage(message, index), getMessageDelayMs(message));
  }

  private revealMessage(message: ScenarioMessageFixture, index: number): void {
    const chatMessage: ChatMessage = { ...message, revealedAt: Date.now() };
    this.emit({
      messages: [...this.snapshot.messages, chatMessage],
      isTyping: false,
    });

    this.scheduleAction(() => {
      const intelligence = message.intelligenceEvents
        ? applyIntelligenceEvents(this.snapshot.intelligence, message.intelligenceEvents)
        : this.snapshot.intelligence;
      const mirubro = message.mirubroEvents
        ? applyMirubroEvents(this.snapshot.mirubro, message.mirubroEvents, intelligence)
        : this.snapshot.mirubro;
      this.emit({ intelligence, mirubro });
      this.scheduleAction(() => this.scheduleStep(index + 1), MESSAGE_SETTLE_MS);
    }, SNAPSHOT_DELAY_MS);
  }
}

export type ReceptionistSimulation = SimulationSnapshot & {
  start: () => void;
  pause: () => void;
  resume: () => void;
  restart: () => void;
};

/** Conecta un `SimulationEngine` al ciclo de vida de un componente React. */
export function useReceptionistSimulation(scenario: ScenarioFixture): ReceptionistSimulation {
  // `useState` con inicializador perezoso crea la instancia una sola vez por
  // componente, sin incurrir en el acceso a `ref.current` durante el render.
  const [engine] = useState(() => new SimulationEngine(scenario));
  const [snapshot, setSnapshot] = useState<SimulationSnapshot>(() => engine.getSnapshot());

  useEffect(() => {
    const unsubscribe = engine.subscribe(setSnapshot);
    return () => {
      unsubscribe();
      engine.dispose();
    };
  }, [engine]);

  return {
    ...snapshot,
    start: () => engine.start(),
    pause: () => engine.pause(),
    resume: () => engine.resume(),
    restart: () => engine.restart(),
  };
}

export type { SimulationSnapshot, SimulationStatus };

// TURNOS RECEPCIONISTA 01: tests del motor de simulación (sin React).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getMessageDelayMs,
  MESSAGE_SETTLE_MS,
  SNAPSHOT_DELAY_MS,
  SimulationEngine,
} from '../simulation-engine';
import { RESERVAR_TURNO_SCENARIO } from '../simulation-data';
import type { ScenarioFixture } from '../types';

const SCENARIO: ScenarioFixture = {
  id: 'reservar-turno',
  label: 'Reservar turno',
  messages: [
    { id: 'm1', role: 'customer', text: 'Hola', delayMs: 400 },
    { id: 'm2', role: 'receptionist', text: 'Hola, te ayudo', typingMs: 800 },
    { id: 'm3', role: 'customer', text: 'Gracias', delayMs: 400 },
  ],
};

const INITIAL_INTELLIGENCE = {
  intent: 'unknown',
  phase: 'idle',
  extracted: {},
  steps: [{ id: 'message_received', label: 'Esperando mensaje', status: 'active' }],
};

const INITIAL_MIRUBRO = {
  contact: { status: 'empty' },
  lead: { status: 'empty' },
  booking: { status: 'empty' },
  events: [],
};

const SCENARIO_DURATION_MS = RESERVAR_TURNO_SCENARIO.messages.reduce(
  (total, message) => total + getMessageDelayMs(message) + SNAPSHOT_DELAY_MS + MESSAGE_SETTLE_MS,
  0,
);

const GAP = SNAPSHOT_DELAY_MS + MESSAGE_SETTLE_MS;
const [, M2, M3, M4, M5, M6, M7, M8] = RESERVAR_TURNO_SCENARIO.messages.map(getMessageDelayMs);

function advanceToMessage(count: number) {
  const elapsed = RESERVAR_TURNO_SCENARIO.messages
    .slice(0, count)
    .reduce((total, message) => total + getMessageDelayMs(message) + GAP, 0);
  vi.advanceTimersByTime(elapsed - MESSAGE_SETTLE_MS);
}

describe('SimulationEngine', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('uses a bounded human pace, with longer typing for longer replies', () => {
    expect(getMessageDelayMs({ id: 'short', role: 'receptionist', text: 'Hola' })).toBe(1496);
    expect(getMessageDelayMs({ id: 'long', role: 'receptionist', text: 'x'.repeat(200) })).toBe(
      3200,
    );
    expect(getMessageDelayMs({ id: 'short', role: 'customer', text: 'Hola' })).toBe(972);
    expect(SCENARIO_DURATION_MS).toBeGreaterThan(20_000);
    expect(SCENARIO_DURATION_MS).toBeLessThan(30_000);
  });

  it('reveals the message before its synchronized panel updates and preserves the remaining pause', () => {
    const engine = new SimulationEngine(RESERVAR_TURNO_SCENARIO);
    engine.start();
    vi.advanceTimersByTime(getMessageDelayMs(RESERVAR_TURNO_SCENARIO.messages[0]));
    expect(engine.getSnapshot().messages).toHaveLength(1);
    expect(engine.getSnapshot().intelligence.intent).toBe('unknown');
    expect(engine.getSnapshot().mirubro.lead.status).toBe('empty');

    vi.advanceTimersByTime(200);
    engine.pause();
    vi.advanceTimersByTime(5000);
    expect(engine.getSnapshot().mirubro.lead.status).toBe('empty');
    engine.resume();
    vi.advanceTimersByTime(SNAPSHOT_DELAY_MS - 201);
    expect(engine.getSnapshot().mirubro.lead.status).toBe('empty');
    vi.advanceTimersByTime(1);
    expect(engine.getSnapshot().intelligence.intent).toBe('book_appointment');
    expect(engine.getSnapshot().mirubro.lead.status).toBe('new');
    expect(engine.getSnapshot().messages).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(1);
    engine.dispose();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('pauses and resumes typing without duplicating a message or restarting its full delay', () => {
    const engine = new SimulationEngine(SCENARIO);
    engine.start();
    vi.advanceTimersByTime(400 + GAP + 300);
    expect(engine.getSnapshot().isTyping).toBe(true);
    engine.pause();
    vi.advanceTimersByTime(5000);
    expect(engine.getSnapshot().messages).toHaveLength(1);
    engine.resume();
    vi.advanceTimersByTime(499);
    expect(engine.getSnapshot().messages).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(engine.getSnapshot().messages.map((message) => message.id)).toEqual(['m1', 'm2']);
    vi.runAllTimers();
    expect(engine.getSnapshot().status).toBe('completed');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('starts idle with no messages', () => {
    const engine = new SimulationEngine(SCENARIO);
    expect(engine.getSnapshot()).toEqual({
      status: 'idle',
      messages: [],
      isTyping: false,
      intelligence: INITIAL_INTELLIGENCE,
      mirubro: INITIAL_MIRUBRO,
    });
  });

  it('reveals messages in order, typing before each receptionist message', () => {
    const engine = new SimulationEngine(SCENARIO);
    engine.start();
    expect(engine.getSnapshot().status).toBe('running');
    expect(engine.getSnapshot().messages).toHaveLength(0);

    // First (customer) message appears after its delay.
    vi.advanceTimersByTime(400);
    expect(engine.getSnapshot().messages.map((m) => m.id)).toEqual(['m1']);
    expect(engine.getSnapshot().isTyping).toBe(false);

    // Settle pause, then typing starts for the receptionist message.
    vi.advanceTimersByTime(GAP);
    expect(engine.getSnapshot().isTyping).toBe(true);
    expect(engine.getSnapshot().messages.map((m) => m.id)).toEqual(['m1']);

    // Typing resolves into the message; indicator disappears.
    vi.advanceTimersByTime(800);
    expect(engine.getSnapshot().isTyping).toBe(false);
    expect(engine.getSnapshot().messages.map((m) => m.id)).toEqual(['m1', 'm2']);

    // Final customer message. A trailing settle pause runs once more
    // before the engine confirms there are no further steps.
    vi.advanceTimersByTime(GAP + 400 + GAP);
    expect(engine.getSnapshot().messages.map((m) => m.id)).toEqual(['m1', 'm2', 'm3']);
    expect(engine.getSnapshot().status).toBe('completed');
  });

  it('pause stops progression and resume continues it', () => {
    const engine = new SimulationEngine(SCENARIO);
    engine.start();
    vi.advanceTimersByTime(400); // m1 revealed
    expect(engine.getSnapshot().messages).toHaveLength(1);

    engine.pause();
    expect(engine.getSnapshot().status).toBe('paused');

    // Time passes while paused: nothing new should appear.
    vi.advanceTimersByTime(5000);
    expect(engine.getSnapshot().messages).toHaveLength(1);
    expect(engine.getSnapshot().status).toBe('paused');

    engine.resume();
    expect(engine.getSnapshot().status).toBe('running');

    vi.advanceTimersByTime(GAP + 800 + GAP + 400 + GAP);
    expect(engine.getSnapshot().messages.map((m) => m.id)).toEqual(['m1', 'm2', 'm3']);
    expect(engine.getSnapshot().status).toBe('completed');
  });

  it('restart clears messages and returns to idle', () => {
    const engine = new SimulationEngine(SCENARIO);
    engine.start();
    vi.advanceTimersByTime(400 + GAP + 800);
    expect(engine.getSnapshot().messages.length).toBeGreaterThan(0);

    engine.restart();
    expect(engine.getSnapshot()).toEqual({
      status: 'idle',
      messages: [],
      isTyping: false,
      intelligence: INITIAL_INTELLIGENCE,
      mirubro: INITIAL_MIRUBRO,
    });

    // No further timers should fire after restart.
    vi.advanceTimersByTime(5000);
    expect(engine.getSnapshot()).toEqual({
      status: 'idle',
      messages: [],
      isTyping: false,
      intelligence: INITIAL_INTELLIGENCE,
      mirubro: INITIAL_MIRUBRO,
    });
  });

  it('dispose clears timers and listeners (cleanup)', () => {
    const engine = new SimulationEngine(SCENARIO);
    const listener = vi.fn();
    engine.subscribe(listener);
    engine.start();
    listener.mockClear();

    engine.dispose();
    vi.advanceTimersByTime(10_000);

    expect(listener).not.toHaveBeenCalled();
  });

  it('start can be called again after completion (repetir simulación)', () => {
    const engine = new SimulationEngine(SCENARIO);
    engine.start();
    vi.advanceTimersByTime(400 + GAP + 800 + GAP + 400 + GAP);
    expect(engine.getSnapshot().status).toBe('completed');

    engine.start();
    expect(engine.getSnapshot()).toEqual({
      status: 'running',
      messages: [],
      isTyping: false,
      intelligence: INITIAL_INTELLIGENCE,
      mirubro: INITIAL_MIRUBRO,
    });
    vi.advanceTimersByTime(400);
    expect(engine.getSnapshot().messages.map((m) => m.id)).toEqual(['m1']);
  });

  it('updates intent and service from the first customer message', () => {
    const engine = new SimulationEngine(RESERVAR_TURNO_SCENARIO);
    engine.start();

    advanceToMessage(1);

    expect(engine.getSnapshot().intelligence).toMatchObject({
      intent: 'book_appointment',
      phase: 'collecting_identity',
      confidence: 0.98,
      extracted: { service: 'Limpieza' },
    });
    expect(engine.getSnapshot().intelligence.steps).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: 'Mensaje recibido', status: 'completed' }),
        expect.objectContaining({ label: 'Intención detectada', status: 'completed' }),
        expect.objectContaining({ label: 'Identificando cliente', status: 'active' }),
      ]),
    );
  });

  it('detects the customer name after the Lucía message', () => {
    const engine = new SimulationEngine(RESERVAR_TURNO_SCENARIO);
    engine.start();

    advanceToMessage(3);

    expect(engine.getSnapshot().intelligence.extracted.name).toBe('Lucía');
    expect(engine.getSnapshot().intelligence.steps).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: 'Cliente identificado', status: 'completed' }),
        expect.objectContaining({
          label: 'Consultando preferencia de fecha',
          status: 'active',
        }),
      ]),
    );
  });

  it('detects preferred day and time range from the customer message', () => {
    const engine = new SimulationEngine(RESERVAR_TURNO_SCENARIO);
    engine.start();

    advanceToMessage(5);

    expect(engine.getSnapshot().intelligence.extracted).toMatchObject({
      preferredDay: 'Mañana',
      preferredTimeRange: 'Tarde',
    });
    expect(engine.getSnapshot().intelligence.steps).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: 'Preferencia detectada', status: 'completed' }),
        expect.objectContaining({ label: 'Buscando disponibilidad', status: 'active' }),
      ]),
    );
  });

  it('moves to offering slots when the receptionist presents availability', () => {
    const engine = new SimulationEngine(RESERVAR_TURNO_SCENARIO);
    engine.start();

    advanceToMessage(6);

    expect(engine.getSnapshot().intelligence.phase).toBe('offering_slots');
    expect(engine.getSnapshot().intelligence.steps).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: 'Disponibilidad consultada', status: 'completed' }),
        expect.objectContaining({ label: 'Esperando selección', status: 'active' }),
      ]),
    );
  });

  it('detects the selected slot and completes with all five fields', () => {
    const engine = new SimulationEngine(RESERVAR_TURNO_SCENARIO);
    engine.start();

    advanceToMessage(7);
    expect(engine.getSnapshot().intelligence.extracted.selectedSlot).toBe('17:30');
    expect(engine.getSnapshot().intelligence.phase).toBe('confirming');

    vi.advanceTimersByTime(GAP + M8);
    const { intelligence } = engine.getSnapshot();
    expect(intelligence.phase).toBe('completed');
    expect(Object.keys(intelligence.extracted)).toHaveLength(5);
    expect(intelligence.steps).toHaveLength(8);
    expect(intelligence.steps.slice(-2)).toEqual([
      { id: 'confirming', label: 'Conversación procesada', status: 'completed' },
      { id: 'required_data', label: 'Datos necesarios obtenidos', status: 'completed' },
    ]);
  });

  it('does not execute intelligence events while paused and continues on resume', () => {
    const engine = new SimulationEngine(RESERVAR_TURNO_SCENARIO);
    engine.start();
    advanceToMessage(1);
    const intelligenceAtPause = engine.getSnapshot().intelligence;

    engine.pause();
    vi.advanceTimersByTime(5000);
    expect(engine.getSnapshot().intelligence).toEqual(intelligenceAtPause);

    engine.resume();
    vi.advanceTimersByTime(GAP + M2 + GAP + M3);
    expect(engine.getSnapshot().intelligence.extracted.name).toBe('Lucía');
  });

  it('restart and repeat reset intelligence to a clean snapshot', () => {
    const engine = new SimulationEngine(RESERVAR_TURNO_SCENARIO);
    engine.start();
    advanceToMessage(1);
    expect(engine.getSnapshot().intelligence.intent).toBe('book_appointment');

    engine.restart();
    expect(engine.getSnapshot().intelligence).toEqual(INITIAL_INTELLIGENCE);

    engine.start();
    expect(engine.getSnapshot().intelligence).toEqual(INITIAL_INTELLIGENCE);
    advanceToMessage(1);
    expect(engine.getSnapshot().intelligence.extracted).toEqual({ service: 'Limpieza' });
  });

  it('derives Contacto, Lead, Reserva and activity from the declared fixture events', () => {
    const engine = new SimulationEngine(RESERVAR_TURNO_SCENARIO);
    engine.start();

    advanceToMessage(1);
    expect(engine.getSnapshot().mirubro).toMatchObject({
      contact: { status: 'empty' },
      lead: {
        status: 'new',
        intent: 'book_appointment',
        service: 'Limpieza',
        source: 'whatsapp',
      },
      booking: { status: 'empty' },
      events: [{ label: 'Consulta recibida', status: 'active' }],
    });

    vi.advanceTimersByTime(GAP + M2 + GAP + M3);
    expect(engine.getSnapshot().mirubro).toMatchObject({
      contact: {
        status: 'identified',
        name: 'Lucía',
        phone: '+54 9 11 2345-6789',
        source: 'whatsapp',
      },
      events: [
        { label: 'Consulta recibida', status: 'completed' },
        { label: 'Contacto identificado', status: 'active' },
      ],
    });

    vi.advanceTimersByTime(GAP + M4 + GAP + M5);
    expect(engine.getSnapshot().mirubro.lead).toMatchObject({
      status: 'qualified',
      service: 'Limpieza',
      preferredDay: 'Mañana',
      preferredTimeRange: 'Tarde',
    });

    vi.advanceTimersByTime(GAP + M6);
    expect(engine.getSnapshot().mirubro.booking).toMatchObject({
      status: 'pending',
      service: 'Limpieza',
      day: 'Mañana',
    });

    vi.advanceTimersByTime(GAP + M7);
    expect(engine.getSnapshot().mirubro.booking).toMatchObject({
      status: 'pending',
      slot: '17:30',
    });

    vi.advanceTimersByTime(GAP + M8 + MESSAGE_SETTLE_MS);
    expect(engine.getSnapshot()).toMatchObject({
      status: 'completed',
      mirubro: {
        lead: { status: 'converted' },
        booking: {
          status: 'confirmed',
          service: 'Limpieza',
          day: 'Mañana',
          slot: '17:30',
        },
        events: [
          { label: 'Consulta recibida', status: 'completed' },
          { label: 'Contacto identificado', status: 'completed' },
          { label: 'Lead calificado', status: 'completed' },
          { label: 'Disponibilidad consultada', status: 'completed' },
          { label: 'Horario seleccionado', status: 'completed' },
          { label: 'Turno confirmado', status: 'completed' },
        ],
      },
    });
    expect(vi.getTimerCount()).toBe(0);
  });

  it('freezes MiRubro while paused, resumes, and clears it on restart and repeat', () => {
    const engine = new SimulationEngine(RESERVAR_TURNO_SCENARIO);
    engine.start();
    advanceToMessage(1);
    const mirubroAtPause = engine.getSnapshot().mirubro;

    engine.pause();
    vi.advanceTimersByTime(5000);
    expect(engine.getSnapshot().mirubro).toEqual(mirubroAtPause);

    engine.resume();
    vi.advanceTimersByTime(SCENARIO_DURATION_MS);
    expect(engine.getSnapshot().mirubro.booking.status).toBe('confirmed');

    engine.restart();
    expect(engine.getSnapshot().mirubro).toEqual(INITIAL_MIRUBRO);
    expect(vi.getTimerCount()).toBe(0);

    engine.start();
    expect(engine.getSnapshot().mirubro).toEqual(INITIAL_MIRUBRO);
    advanceToMessage(1);
    expect(engine.getSnapshot().mirubro.lead.status).toBe('new');
  });
});

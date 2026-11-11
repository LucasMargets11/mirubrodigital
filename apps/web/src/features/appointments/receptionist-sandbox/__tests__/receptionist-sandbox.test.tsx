// TURNOS RECEPCIONISTA 01: tests de UI del sandbox (shell + simulación).

import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ReceptionistSandbox } from '../receptionist-sandbox';
import { RESERVAR_TURNO_SCENARIO } from '../simulation-data';
import { getMessageDelayMs, MESSAGE_SETTLE_MS, SNAPSHOT_DELAY_MS } from '../simulation-engine';

const TOTAL_DURATION_MS = RESERVAR_TURNO_SCENARIO.messages.reduce(
  (total, message) => total + getMessageDelayMs(message) + SNAPSHOT_DELAY_MS + MESSAGE_SETTLE_MS,
  0,
);

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

function advanceToMessage(count: number) {
  for (let step = 0; step < 32; step++) {
    if (screen.queryAllByTestId('receptionist-message-bubble').length >= count) {
      advance(SNAPSHOT_DELAY_MS);
      return;
    }
    act(() => vi.advanceTimersToNextTimer());
  }
  throw new Error(`Message ${count} was not revealed.`);
}

describe('ReceptionistSandbox', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Element.prototype.scrollTo = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('renders idle with an empty intelligence panel and the MiRubro placeholders', () => {
    render(<ReceptionistSandbox />);

    expect(screen.getByRole('button', { name: /Iniciar demo/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Modo interactivo próximamente')).toBeDisabled();
    expect(screen.getByText('Iniciá la demo para ver la conversación.')).toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(0);

    const intelligence = within(
      screen.getByRole('region', { name: 'Inteligencia del Recepcionista IA' }),
    );
    expect(intelligence.getByText('Sin detectar')).toBeInTheDocument();
    expect(intelligence.getByText('Esperando mensaje')).toBeInTheDocument();
    expect(intelligence.getByText('0 de 5 datos detectados')).toBeInTheDocument();
    expect(intelligence.getByRole('progressbar', { name: 'Datos detectados' })).toHaveAttribute(
      'aria-valuenow',
      '0',
    );
    const mirubro = within(screen.getByRole('region', { name: 'Procesamiento en MiRubro' }));
    expect(mirubro.getByText('Todavía no identificado')).toBeInTheDocument();
    expect(mirubro.getByText('Todavía no creado')).toBeInTheDocument();
    expect(mirubro.getByText('Sin turno')).toBeInTheDocument();
    expect(mirubro.getByText('Sin actividad todavía')).toBeInTheDocument();
  });

  it('starts the simulation and reveals messages in order with typing before each bot reply', () => {
    render(<ReceptionistSandbox />);

    fireEvent.click(screen.getByRole('button', { name: /Iniciar demo/i }));
    expect(screen.getByRole('button', { name: /Pausar/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('La simulación automática está en curso')).toBeDisabled();

    // First customer message.
    advance(getMessageDelayMs(RESERVAR_TURNO_SCENARIO.messages[0]));
    const bubbles = () => screen.getAllByTestId('receptionist-message-bubble');
    expect(bubbles()).toHaveLength(1);
    expect(bubbles()[0]).toHaveTextContent('Hola, quería sacar un turno para una limpieza.');

    // Typing indicator shows before the receptionist reply.
    advance(SNAPSHOT_DELAY_MS + MESSAGE_SETTLE_MS);
    expect(screen.getByTestId('receptionist-typing-indicator')).toBeInTheDocument();
    expect(bubbles()).toHaveLength(1);

    advance(getMessageDelayMs(RESERVAR_TURNO_SCENARIO.messages[1]));
    expect(screen.queryByTestId('receptionist-typing-indicator')).not.toBeInTheDocument();
    expect(bubbles()).toHaveLength(2);
    expect(bubbles()[1]).toHaveTextContent('¿Me decís tu nombre?');

    // Run the rest to completion and check full order.
    advance(TOTAL_DURATION_MS);
    const finalBubbles = bubbles();
    expect(finalBubbles).toHaveLength(RESERVAR_TURNO_SCENARIO.messages.length);
    finalBubbles.forEach((bubble, index) => {
      expect(bubble).toHaveTextContent(RESERVAR_TURNO_SCENARIO.messages[index].text);
    });
  });

  it('pause stops progression and resume continues it', () => {
    render(<ReceptionistSandbox />);
    fireEvent.click(screen.getByRole('button', { name: /Iniciar demo/i }));

    advanceToMessage(1);
    expect(screen.getAllByTestId('receptionist-message-bubble')).toHaveLength(1);
    const intelligence = within(
      screen.getByRole('region', { name: 'Inteligencia del Recepcionista IA' }),
    );
    const mirubro = within(screen.getByRole('region', { name: 'Procesamiento en MiRubro' }));
    expect(intelligence.getByText('Limpieza')).toBeInTheDocument();
    expect(mirubro.getByText('Nuevo')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Pausar/i }));
    expect(screen.getByRole('button', { name: /Reanudar/i })).toBeInTheDocument();

    advance(5000);
    expect(screen.getAllByTestId('receptionist-message-bubble')).toHaveLength(1);
    expect(intelligence.getByText('Limpieza')).toBeInTheDocument();
    expect(intelligence.queryByText('Lucía')).not.toBeInTheDocument();
    expect(mirubro.getByText('Nuevo')).toBeInTheDocument();
    expect(mirubro.queryByText('Lucía')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Reanudar/i }));
    expect(screen.getByRole('button', { name: /Pausar/i })).toBeInTheDocument();

    advance(TOTAL_DURATION_MS);
    expect(screen.getAllByTestId('receptionist-message-bubble')).toHaveLength(
      RESERVAR_TURNO_SCENARIO.messages.length,
    );
  });

  it('restart clears the conversation and returns to the idle button label', () => {
    render(<ReceptionistSandbox />);
    fireEvent.click(screen.getByRole('button', { name: /Iniciar demo/i }));
    advanceToMessage(2);
    expect(screen.getAllByTestId('receptionist-message-bubble')).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: /Reiniciar/i }));

    expect(screen.queryByTestId('receptionist-message-bubble')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Iniciar demo/i })).toBeInTheDocument();
    expect(screen.getByText('Iniciá la demo para ver la conversación.')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(vi.getTimerCount()).toBe(0);
    const intelligence = within(
      screen.getByRole('region', { name: 'Inteligencia del Recepcionista IA' }),
    );
    expect(intelligence.getByText('Sin detectar')).toBeInTheDocument();
    expect(intelligence.getByText('0 de 5 datos detectados')).toBeInTheDocument();
    const mirubro = within(screen.getByRole('region', { name: 'Procesamiento en MiRubro' }));
    expect(mirubro.getByText('Todavía no identificado')).toBeInTheDocument();
    expect(mirubro.getByText('Todavía no creado')).toBeInTheDocument();
    expect(mirubro.getByText('Sin turno')).toBeInTheDocument();
    expect(mirubro.getByText('Sin actividad todavía')).toBeInTheDocument();
  });

  it('shows a discreet completed state and allows repeating the simulation', () => {
    render(<ReceptionistSandbox />);
    fireEvent.click(screen.getByRole('button', { name: /Iniciar demo/i }));

    advance(TOTAL_DURATION_MS + 1000);

    expect(screen.getByText('Simulación completada')).toBeInTheDocument();
    const repeatButton = screen.getByRole('button', { name: /Repetir demo/i });
    expect(repeatButton).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(vi.getTimerCount()).toBe(0);
    const mirubro = within(screen.getByRole('region', { name: 'Procesamiento en MiRubro' }));
    expect(mirubro.getByText('Lucía')).toBeInTheDocument();
    expect(mirubro.getByText('Convertido')).toBeInTheDocument();
    expect(mirubro.getByText('Confirmada')).toBeInTheDocument();

    fireEvent.click(repeatButton);
    expect(screen.getByRole('button', { name: /Pausar/i })).toBeInTheDocument();
    const intelligence = within(
      screen.getByRole('region', { name: 'Inteligencia del Recepcionista IA' }),
    );
    expect(intelligence.getByText('Sin detectar')).toBeInTheDocument();
    expect(intelligence.getByText('0 de 5 datos detectados')).toBeInTheDocument();
    expect(mirubro.getByText('Todavía no identificado')).toBeInTheDocument();
    expect(mirubro.getByText('Todavía no creado')).toBeInTheDocument();
    expect(mirubro.getByText('Sin turno')).toBeInTheDocument();
    expect(mirubro.queryByText('Confirmada')).not.toBeInTheDocument();
    expect(mirubro.queryByText('Consulta recibida')).not.toBeInTheDocument();
  });

  it('never calls fetch while the simulation runs', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem');
    const xhrSpy = vi.spyOn(XMLHttpRequest.prototype, 'open');
    const intervalSpy = vi.spyOn(globalThis, 'setInterval');
    const websocketSpy = vi.fn();
    vi.stubGlobal('WebSocket', websocketSpy);

    render(<ReceptionistSandbox />);
    fireEvent.click(screen.getByRole('button', { name: /Iniciar demo/i }));
    for (let elapsed = 0; elapsed < TOTAL_DURATION_MS + 1000; elapsed += 50) {
      expect(vi.getTimerCount()).toBeLessThanOrEqual(1);
      advance(50);
    }

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(intervalSpy).not.toHaveBeenCalled();
    expect(websocketSpy).not.toHaveBeenCalled();
    expect(xhrSpy).not.toHaveBeenCalled();
    expect(storageSpy).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
    intervalSpy.mockRestore();
    xhrSpy.mockRestore();
    storageSpy.mockRestore();
  });

  it('clears pending timers on unmount without throwing', () => {
    const { unmount } = render(<ReceptionistSandbox />);
    fireEvent.click(screen.getByRole('button', { name: /Iniciar demo/i }));
    advanceToMessage(1);

    expect(() => unmount()).not.toThrow();
    expect(vi.getTimerCount()).toBe(0);
    expect(() => advance(10_000)).not.toThrow();
  });

  it('does not break when prefers-reduced-motion is active', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));

    render(<ReceptionistSandbox />);
    fireEvent.click(screen.getByRole('button', { name: /Iniciar demo/i }));

    expect(() => advance(TOTAL_DURATION_MS + 1000)).not.toThrow();
    expect(Element.prototype.scrollTo).toHaveBeenCalledWith(
      expect.objectContaining({ behavior: 'auto' }),
    );
  });

  it('keeps the Inteligencia and MiRubro panels visible while the chat is playing', () => {
    render(<ReceptionistSandbox />);
    fireEvent.click(screen.getByRole('button', { name: /Iniciar demo/i }));
    advanceToMessage(1);

    const intelligence = within(
      screen.getByRole('region', { name: 'Inteligencia del Recepcionista IA' }),
    );
    const mirubro = within(screen.getByRole('region', { name: 'Procesamiento en MiRubro' }));

    expect(intelligence.getAllByText('Intención detectada').length).toBeGreaterThan(0);
    expect(intelligence.getByText('Datos detectados')).toBeInTheDocument();
    expect(intelligence.getByText('Proceso')).toBeInTheDocument();
    expect(mirubro.getByText('Contacto')).toBeInTheDocument();
    expect(mirubro.getByText('Lead')).toBeInTheDocument();
    expect(mirubro.getByText('Reserva')).toBeInTheDocument();
  });

  it('updates MiRubro progressively with the simulated conversation', () => {
    render(<ReceptionistSandbox />);
    fireEvent.click(screen.getByRole('button', { name: /Iniciar demo/i }));
    const mirubro = within(screen.getByRole('region', { name: 'Procesamiento en MiRubro' }));

    advanceToMessage(1);
    expect(mirubro.getByText('Nuevo')).toBeInTheDocument();
    expect(mirubro.getByText('Reservar turno · Limpieza')).toBeInTheDocument();
    expect(mirubro.getByText('Consulta recibida')).toBeInTheDocument();
    expect(mirubro.getByText('Todavía no identificado')).toBeInTheDocument();
    expect(mirubro.getByTestId('mirubro-activity-event')).toHaveAttribute(
      'data-event-status',
      'active',
    );
    expect(mirubro.getByTestId('mirubro-activity-event')).toHaveAttribute('aria-current', 'step');

    advanceToMessage(3);
    expect(mirubro.getByText('Lucía')).toBeInTheDocument();
    expect(mirubro.getByText('+54 9 11 2345-6789')).toBeInTheDocument();
    expect(
      within(mirubro.getByTestId('mirubro-contact-card')).getByText('WhatsApp'),
    ).toBeInTheDocument();
    expect(mirubro.getByText('Identificado')).toBeInTheDocument();

    advanceToMessage(5);
    expect(mirubro.getByText('Calificado')).toBeInTheDocument();
    expect(mirubro.getByText('Preferencia: Mañana · Tarde')).toBeInTheDocument();

    advanceToMessage(6);
    expect(mirubro.getByText('Pendiente')).toBeInTheDocument();
    expect(mirubro.getByText('Disponibilidad consultada')).toBeInTheDocument();

    advanceToMessage(7);
    expect(mirubro.getByTestId('mirubro-booking-card')).toHaveTextContent('17:30');
    expect(mirubro.getByText('Horario seleccionado')).toBeInTheDocument();

    advanceToMessage(8);
    advance(MESSAGE_SETTLE_MS);
    expect(mirubro.getByText('Convertido')).toBeInTheDocument();
    expect(mirubro.getByTestId('mirubro-booking-card')).toHaveTextContent(/Mañana\s*·\s*17:30/);
    expect(mirubro.getByText('Confirmada')).toBeInTheDocument();
    expect(mirubro.getByText('Turno confirmado')).toBeInTheDocument();
    expect(mirubro.getAllByTestId('mirubro-activity-event')).toHaveLength(6);
    expect(mirubro.getAllByTestId('mirubro-activity-event').at(-1)).toHaveAttribute(
      'data-event-status',
      'completed',
    );
  });

  it('shows detected fields, progress and process states as messages appear', () => {
    render(<ReceptionistSandbox />);
    fireEvent.click(screen.getByRole('button', { name: /Iniciar demo/i }));

    const intelligence = within(
      screen.getByRole('region', { name: 'Inteligencia del Recepcionista IA' }),
    );
    advanceToMessage(1);
    expect(intelligence.getByText('Reservar turno')).toBeInTheDocument();
    expect(intelligence.getByTestId('intelligence-field-service')).toHaveAttribute(
      'data-field-status',
      'completed',
    );
    expect(intelligence.getByTestId('intelligence-field-name')).toHaveAttribute(
      'data-field-status',
      'pending',
    );
    expect(intelligence.queryByTestId('intelligence-field-check-name')).not.toBeInTheDocument();
    expect(intelligence.getByTestId('intelligence-field-check-service')).toBeInTheDocument();
    expect(intelligence.getByText('Limpieza')).toBeInTheDocument();
    expect(intelligence.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1');
    expect(
      intelligence
        .getAllByTestId('intelligence-step')
        .some((step) => step.getAttribute('data-step-status') === 'active'),
    ).toBe(true);
    expect(
      intelligence
        .getAllByTestId('intelligence-step')
        .some((step) => step.getAttribute('data-step-status') === 'pending'),
    ).toBe(true);

    advanceToMessage(3);
    expect(intelligence.getByTestId('intelligence-field-name')).toHaveAttribute(
      'data-field-status',
      'completed',
    );
    expect(intelligence.getByTestId('intelligence-field-check-name')).toBeInTheDocument();
    expect(intelligence.getByText('Lucía')).toBeInTheDocument();

    advanceToMessage(5);
    expect(intelligence.getByText('Mañana')).toBeInTheDocument();
    expect(intelligence.getByText('Tarde')).toBeInTheDocument();

    advance(MESSAGE_SETTLE_MS);
    expect(intelligence.getByText('Consultando agenda…')).toBeInTheDocument();
    advance(getMessageDelayMs(RESERVAR_TURNO_SCENARIO.messages[5]) + SNAPSHOT_DELAY_MS);
    expect(intelligence.getByText('Esperando respuesta')).toBeInTheDocument();
    expect(
      intelligence
        .getAllByTestId('intelligence-step')
        .find((step) => step.getAttribute('data-step-status') === 'active'),
    ).toHaveTextContent('Esperando selección');
    expect(
      intelligence
        .getAllByTestId('intelligence-step')
        .find((step) => step.getAttribute('data-step-status') === 'active'),
    ).toHaveAttribute('aria-current', 'step');

    advanceToMessage(7);
    expect(intelligence.getByText('17:30')).toBeInTheDocument();
    expect(
      intelligence
        .getAllByTestId('intelligence-step')
        .find((step) => step.getAttribute('data-step-status') === 'active'),
    ).toHaveTextContent('Confirmando turno');

    advanceToMessage(8);
    expect(intelligence.getByText('Completado')).toBeInTheDocument();
    expect(intelligence.getByText('5 de 5 datos detectados')).toBeInTheDocument();
    expect(intelligence.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '5');
    expect(intelligence.getByText('Conversación procesada')).toBeInTheDocument();
    expect(intelligence.getByText('Datos necesarios obtenidos')).toBeInTheDocument();
  });
});

/**
 * PR-2 — Frontend tests for CancelSubscriptionModal
 *
 * Test matrix (12 cases):
 *  1.  Botón visible para suscripción activa (can_cancel = true).
 *  2.  Botón oculto para suscripción cancelada (can_cancel = false).
 *  3.  Modal muestra nombre del negocio, plan y advertencias.
 *  4.  Motivo obligatorio — confirmar sin texto no llama al endpoint.
 *  5.  Botón deshabilitado durante el request.
 *  6.  Se llama al endpoint correcto al confirmar.
 *  7.  No se envía preapproval_id en el cuerpo del request.
 *  8.  No se envía información de MP desde el navegador.
 *  9.  Éxito invoca onSuccess y no muestra error.
 * 10.  Error de MP mantiene el modal abierto y muestra el mensaje.
 * 11.  Doble click no genera dos solicitudes.
 * 12.  No existe ningún elemento de reembolso en el modal.
 */

import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Next.js mocks ─────────────────────────────────────────────────────────────
vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

import type { AdminSubscriptionDetail } from '@/lib/admin/types';
import { CancelSubscriptionModal } from '@/components/admin/cancel-subscription-modal';
import { SuscripcionDetailContent } from '@/app/admin/suscripciones/[subscriptionId]/suscripcion-detail-content';

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeSubscription(overrides: Partial<AdminSubscriptionDetail> = {}): AdminSubscriptionDetail {
  return {
    id: 'sub-uuid-001',
    business: { id: 42, name: 'Acme Resto', slug: 'acme-resto', status: 'active' },
    plan_code: 'gestion_pro_monthly',
    service_type: 'gestion',
    status: 'active',
    admin_status: 'active',
    provider: 'mercadopago',
    provider_sub_id: 'PREAPPROVAL-1234567890abcdef',
    external_reference: 'SUB-abc123',
    is_active: true,
    trial_starts_at: null,
    trial_ends_at: null,
    current_period_start: '2026-06-01T00:00:00Z',
    current_period_end: '2026-07-01T00:00:00Z',
    grace_until: null,
    retry_count: 0,
    cancel_at_period_end: false,
    cancel_requested_at: null,
    cancel_reason: '',
    canceled_at: null,
    canceled_by_email: null,
    canceled_by_name: null,
    can_cancel: true,
    price_snapshot: {},
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-06-01T00:00:00Z',
    risk_badges: [],
    payments: [],
    events: [],
    invoice_events: [
      {
        id: 'inv-001',
        amount: '5000.00',
        currency: 'ARS',
        provider_status: 'authorized',
        paid_at: '2026-06-02T12:00:00Z',
        created_at: '2026-06-02T12:00:00Z',
      },
    ],
    webhook_errors: [],
    notes: [],
    ...overrides,
  };
}

// ── Tests: CancelSubscriptionModal ────────────────────────────────────────────

describe('CancelSubscriptionModal', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── Test 3: Modal shows business name, plan and warnings ──────────────────
  it('3 - renders business name, plan and warning text', () => {
    const sub = makeSubscription();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    expect(screen.getByText('Acme Resto')).toBeInTheDocument();
    // planLabel('gestion_pro_monthly') = 'Pro (mensual)'
    expect(screen.getByText(/Pro/)).toBeInTheDocument();
    expect(
      screen.getByText(/futuros cobros de Mercado Pago/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/pago ya realizado no será reembolsado/i),
    ).toBeInTheDocument();
  });

  // ── Test 4: Required reason field ─────────────────────────────────────────
  it('4 - confirm button disabled when reason is empty', () => {
    const sub = makeSubscription();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );
    const confirmBtn = screen.getByRole('button', { name: /confirmar cancelación/i });
    expect(confirmBtn).toBeDisabled();
  });

  it('4b - no fetch when reason is empty and button is clicked', async () => {
    const sub = makeSubscription();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );
    const confirmBtn = screen.getByRole('button', { name: /confirmar cancelación/i });
    fireEvent.click(confirmBtn);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  // ── Test 5: Button disabled during request ────────────────────────────────
  it('5 - button is disabled during pending request', async () => {
    fetchMock.mockReturnValue(new Promise(() => {})); // never resolves
    const sub = makeSubscription();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Motivo de prueba' } });

    const confirmBtn = screen.getByRole('button', { name: /confirmar cancelación/i });
    fireEvent.click(confirmBtn);

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /cancelando/i }),
      ).toBeDisabled(),
    );
  });

  // ── Test 6: Calls correct endpoint ────────────────────────────────────────
  it('6 - calls the correct cancel endpoint', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'canceled', message: 'OK' }),
    });
    const sub = makeSubscription();
    const onSuccess = vi.fn();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={onSuccess}
      />,
    );

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Cuenta de prueba' } });
    fireEvent.click(screen.getByRole('button', { name: /confirmar cancelación/i }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/platform-admin/subscriptions/sub-uuid-001/cancel/');
    expect(opts.method).toBe('POST');
  });

  // ── Test 7: preapproval_id NOT sent in request body ───────────────────────
  it('7 - does not send preapproval_id in request body', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
    const sub = makeSubscription();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Test reason' } });
    fireEvent.click(screen.getByRole('button', { name: /confirmar cancelación/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).not.toHaveProperty('preapproval_id');
    expect(body).not.toHaveProperty('provider_sub_id');
  });

  // ── Test 8: No MP information sent from browser ───────────────────────────
  it('8 - does not send MP-specific fields from browser', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
    const sub = makeSubscription();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Test reason' } });
    fireEvent.click(screen.getByRole('button', { name: /confirmar cancelación/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    // Only 'reason' should be in the body
    expect(Object.keys(body)).toEqual(['reason']);
  });

  // ── Test 9: Success calls onSuccess ───────────────────────────────────────
  it('9 - success triggers onSuccess callback without error message', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'canceled', message: 'La suscripción fue cancelada correctamente.' }),
    });
    const sub = makeSubscription();
    const onSuccess = vi.fn();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={onSuccess}
      />,
    );

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Cuenta de prueba' } });
    fireEvent.click(screen.getByRole('button', { name: /confirmar cancelación/i }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    // No error alert should appear
    expect(screen.queryByRole('alert')).toBeNull();
  });

  // ── Test 10: MP error keeps modal open and shows message ─────────────────
  it('10 - MP error keeps modal open with error message', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({ detail: 'Mercado Pago rechazó la cancelación.' }),
    });
    const sub = makeSubscription();
    const onSuccess = vi.fn();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={onSuccess}
      />,
    );

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Test reason' } });
    fireEvent.click(screen.getByRole('button', { name: /confirmar cancelación/i }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        /mercado pago rechazó/i,
      ),
    );
    // Modal stays open, onSuccess not called
    expect(onSuccess).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  // ── Test 11: Double click does not generate two requests ──────────────────
  it('11 - double click does not generate two requests', async () => {
    let resolveFirst: (v: any) => void;
    const pendingPromise = new Promise((res) => { resolveFirst = res; });
    fetchMock.mockReturnValueOnce(pendingPromise);

    const sub = makeSubscription();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Test reason' } });
    const confirmBtn = screen.getByRole('button', { name: /confirmar cancelación/i });

    // Click twice rapidly
    fireEvent.click(confirmBtn);
    fireEvent.click(confirmBtn);

    // Only one fetch call despite two clicks
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  // ── Test 12: No refund action in modal ────────────────────────────────────
  it('12 - modal contains no refund action', () => {
    const sub = makeSubscription();
    render(
      <CancelSubscriptionModal
        subscription={sub}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );
    expect(screen.queryByText(/reembolso/i)).toBeNull();
    expect(screen.queryByText(/devolver/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /reembolso/i })).toBeNull();
  });
});

// ── Tests: SuscripcionDetailContent cancel button visibility ─────────────────

describe('SuscripcionDetailContent — cancel button visibility', () => {
  // ── Test 1: Button visible for active subscription ────────────────────────
  it('1 - cancel button visible when can_cancel=true', () => {
    const sub = makeSubscription({ can_cancel: true, status: 'active' });
    render(<SuscripcionDetailContent subscription={sub} />);
    expect(
      screen.getByTestId('cancel-subscription-btn'),
    ).toBeInTheDocument();
  });

  // ── Test 2: Button hidden for canceled subscription ───────────────────────
  it('2 - cancel button hidden when can_cancel=false', () => {
    const sub = makeSubscription({
      can_cancel: false,
      status: 'canceled',
      is_active: false,
      canceled_at: '2026-07-01T00:00:00Z',
    });
    render(<SuscripcionDetailContent subscription={sub} />);
    expect(screen.queryByTestId('cancel-subscription-btn')).toBeNull();
  });
});

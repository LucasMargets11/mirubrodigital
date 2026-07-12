/**
 * Integration tests for SuscripcionDetailContent
 *
 * Covers: cancel button visibility, modal open/close, endpoint call,
 * request body safety, success/error handling, and router.refresh().
 */

import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Next.js mocks ─────────────────────────────────────────────────────────────

const mockRouterRefresh = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: mockRouterRefresh }),
}));

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

// ── Imports ───────────────────────────────────────────────────────────────────

import type { AdminSubscriptionDetail } from '@/lib/admin/types';
import { SuscripcionDetailContent } from '@/app/admin/suscripciones/[subscriptionId]/suscripcion-detail-content';

// ── Fixture ───────────────────────────────────────────────────────────────────

function makeSubscription(overrides: Partial<AdminSubscriptionDetail> = {}): AdminSubscriptionDetail {
  return {
    id: 'sub-detail-001',
    business: { id: 77, name: 'Pizzería Roma', slug: 'pizzeria-roma', status: 'active' },
    plan_code: 'gestion_pro_monthly',
    service_type: 'gestion',
    status: 'active',
    admin_status: 'active',
    provider: 'mercadopago',
    provider_sub_id: 'PREAP-1234567890abcdef',
    external_reference: 'SUB-abc',
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

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SuscripcionDetailContent — cancel button & modal integration', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    mockRouterRefresh.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ── 1. Cancel button visible when can_cancel=true ─────────────────────────
  it('1 - cancel button visible for cancellable subscription', () => {
    render(<SuscripcionDetailContent subscription={makeSubscription()} />);
    expect(screen.getByTestId('cancel-subscription-btn')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-subscription-btn')).toHaveTextContent(
      /cancelar/i,
    );
  });

  // ── 2. Cancel button hidden when can_cancel=false ─────────────────────────
  it('2 - cancel button hidden for already-canceled subscription', () => {
    const sub = makeSubscription({
      can_cancel: false,
      status: 'canceled',
      is_active: false,
      canceled_at: '2026-07-01T00:00:00Z',
    });
    render(<SuscripcionDetailContent subscription={sub} />);
    expect(screen.queryByTestId('cancel-subscription-btn')).toBeNull();
  });

  // ── 3. Click opens modal with business name and plan ──────────────────────
  it('3 - clicking button opens modal with business and plan info', () => {
    render(<SuscripcionDetailContent subscription={makeSubscription()} />);
    fireEvent.click(screen.getByTestId('cancel-subscription-btn'));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText('Pizzería Roma')).toBeInTheDocument();
    // Plan label (Pro mensual) or raw plan code
    expect(
      within(dialog).queryByText(/Pro/i) || within(dialog).queryByText(/gestion_pro_monthly/i),
    ).toBeTruthy();
  });

  // ── 4. Modal shows immediate-cancellation copy ────────────────────────────
  it('4 - modal copy warns about immediate access loss and no refund', () => {
    render(<SuscripcionDetailContent subscription={makeSubscription()} />);
    fireEvent.click(screen.getByTestId('cancel-subscription-btn'));
    // "inmediatamente" or "immediate" in the header / warnings
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toMatch(/inmediatamente/i);
    expect(dialog.textContent).toMatch(/reembolsado/i);
  });

  // ── 5. Success: calls exact endpoint, body = only reason, router.refresh() ─
  it('5 - success calls correct endpoint with only reason in body, then refreshes', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ status: 'canceled' }) });

    render(<SuscripcionDetailContent subscription={makeSubscription()} />);
    fireEvent.click(screen.getByTestId('cancel-subscription-btn'));

    const dialog = screen.getByRole('dialog');
    const textarea = within(dialog).getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Cuenta de prueba' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /confirmar/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());

    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/v1/platform-admin/subscriptions/sub-detail-001/cancel/');
    expect(opts.method).toBe('POST');

    const body = JSON.parse(opts.body);
    expect(Object.keys(body)).toEqual(['reason']);
    expect(body.reason).toBe('Cuenta de prueba');
    expect(body).not.toHaveProperty('provider_sub_id');
    expect(body).not.toHaveProperty('preapproval_id');

    await waitFor(() => expect(mockRouterRefresh).toHaveBeenCalledOnce());
  });

  // ── 6. Success closes modal ────────────────────────────────────────────────
  it('6 - modal closes after successful cancel', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });

    render(<SuscripcionDetailContent subscription={makeSubscription()} />);
    fireEvent.click(screen.getByTestId('cancel-subscription-btn'));
    const dialogClose = screen.getByRole('dialog');
    fireEvent.change(within(dialogClose).getByRole('textbox'), { target: { value: 'Motivo' } });
    fireEvent.click(within(dialogClose).getByRole('button', { name: /confirmar/i }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  // ── 7. Error: modal stays open, router.refresh NOT called ─────────────────
  it('7 - 502 error keeps modal open and does not refresh router', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({
        detail:
          'No pudimos confirmar la cancelación en Mercado Pago. La suscripción no fue modificada en MiRubro. Podés volver a intentarlo.',
      }),
    });

    render(<SuscripcionDetailContent subscription={makeSubscription()} />);
    fireEvent.click(screen.getByTestId('cancel-subscription-btn'));
    const dialog502 = screen.getByRole('dialog');
    fireEvent.change(within(dialog502).getByRole('textbox'), { target: { value: 'Motivo' } });
    fireEvent.click(within(dialog502).getByRole('button', { name: /confirmar/i }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        /no pudimos confirmar/i,
      ),
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(mockRouterRefresh).not.toHaveBeenCalled();
  });

  // ── 8. Error: can retry (confirm button re-enabled after error) ────────────
  it('8 - confirm button re-enables after a failed request', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({ detail: 'Error MP' }),
    });

    render(<SuscripcionDetailContent subscription={makeSubscription()} />);
    fireEvent.click(screen.getByTestId('cancel-subscription-btn'));
    const dialog8 = screen.getByRole('dialog');
    fireEvent.change(within(dialog8).getByRole('textbox'), { target: { value: 'Motivo' } });
    fireEvent.click(within(dialog8).getByRole('button', { name: /confirmar/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());

    const confirmBtn = within(dialog8).getByRole('button', { name: /confirmar/i });
    expect(confirmBtn).not.toBeDisabled();
  });

  // ── 9. Double click does not duplicate the request ────────────────────────
  it('9 - double click does not send duplicate requests', async () => {
    fetchMock.mockReturnValue(new Promise(() => {})); // never resolves

    render(<SuscripcionDetailContent subscription={makeSubscription()} />);
    fireEvent.click(screen.getByTestId('cancel-subscription-btn'));
    const dialog9 = screen.getByRole('dialog');
    fireEvent.change(within(dialog9).getByRole('textbox'), { target: { value: 'Motivo' } });

    const confirmBtn = within(dialog9).getByRole('button', { name: /confirmar/i });
    fireEvent.click(confirmBtn);
    fireEvent.click(confirmBtn);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  // ── 10. No refund action exists anywhere in the modal ────────────────────
  it('10 - modal contains no refund action', () => {
    render(<SuscripcionDetailContent subscription={makeSubscription()} />);
    fireEvent.click(screen.getByTestId('cancel-subscription-btn'));
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).not.toMatch(/acción de reembolso/i);
    expect(screen.queryByRole('button', { name: /reembolso/i })).toBeNull();
  });
});

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ReturnPage from '../page';

const mocks = vi.hoisted(() => ({
  params: new URLSearchParams(),
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => mocks.params,
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
}));

function response(status: number, body: unknown = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function checkoutStatus(
  status: 'pending' | 'linked' | 'active' | 'failed' | 'expired',
  canRetry = false,
) {
  return {
    checkout_id: 'checkout-id',
    status,
    plan_code: 'appointments',
    usage_tier: null,
    billing_cycle: 'monthly',
    subscription_status: null,
    can_retry: canRetry,
    failure_code: null,
  };
}

describe('/subscribe/return Turnos flow', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    mocks.params = new URLSearchParams();
    mocks.push.mockReset();
    mocks.replace.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('detects appointments_checkout_id and polls the owner-scoped status endpoint', async () => {
    mocks.params.set('appointments_checkout_id', 'checkout-id');
    fetchMock.mockResolvedValue(response(200, checkoutStatus('pending')));

    render(<ReturnPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toContain(
      '/api/v1/billing/appointments/checkouts/checkout-id/status/',
    );
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'include' });
    expect(screen.getByText('Estamos confirmando tu pago.')).toBeInTheDocument();
  });

  it('renders linked state while continuing to poll', async () => {
    vi.useFakeTimers();
    mocks.params.set('appointments_checkout_id', 'checkout-id');
    fetchMock.mockResolvedValue(response(200, checkoutStatus('linked')));

    render(<ReturnPage />);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(
      screen.getByText('Tu suscripción fue vinculada. Estamos esperando confirmación del pago.'),
    ).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('renders active state and routes the CTA to Turnos first-run', async () => {
    mocks.params.set('appointments_checkout_id', 'checkout-id');
    fetchMock.mockResolvedValue(response(200, checkoutStatus('active')));

    render(<ReturnPage />);

    fireEvent.click(await screen.findByRole('button', { name: 'Configurar Turnos' }));
    expect(mocks.push).toHaveBeenCalledWith('/app/turnos?onboarding=1');
  });

  it('renders failed and expired states with their retry destinations', async () => {
    mocks.params.set('appointments_checkout_id', 'checkout-id');
    fetchMock.mockResolvedValue(response(200, checkoutStatus('failed', true)));

    const { rerender } = render(<ReturnPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Reintentar contratación' }));
    expect(mocks.push).toHaveBeenCalledWith('/pricing?service=appointments');

    mocks.params = new URLSearchParams('appointments_checkout_id=expired-id');
    fetchMock.mockResolvedValue(response(200, checkoutStatus('expired', true)));
    rerender(<ReturnPage />);
    expect(await screen.findByText('El intento de contratación venció.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Volver a planes de Turnos' }));
    expect(mocks.push).toHaveBeenCalledWith('/pricing?service=appointments');
  });

  it('keeps browser timeout pending rather than reporting payment failure', async () => {
    vi.useFakeTimers();
    mocks.params.set('appointments_checkout_id', 'checkout-id');
    fetchMock.mockResolvedValue(response(200, checkoutStatus('pending')));

    render(<ReturnPage />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });

    expect(screen.getByText('Seguimos procesando la confirmación.')).toBeInTheDocument();
    expect(screen.queryByText('No pudimos completar la contratación.')).not.toBeInTheDocument();
  });

  it.each([401, 403])(
    'handles authentication response %s without polling forever',
    async (httpStatus) => {
      mocks.params.set('appointments_checkout_id', 'checkout-id');
      fetchMock.mockResolvedValue(response(httpStatus));

      render(<ReturnPage />);

      expect(
        await screen.findByText(
          'Iniciá sesión como propietario del negocio para consultar este intento.',
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Iniciar sesión' })).toBeInTheDocument();
    },
  );

  it('handles a missing or foreign checkout as not found', async () => {
    mocks.params.set('appointments_checkout_id', 'checkout-id');
    fetchMock.mockResolvedValue(response(404));

    render(<ReturnPage />);

    expect(
      await screen.findByText('No encontramos este intento de contratación para tu negocio.'),
    ).toBeInTheDocument();
  });

  it('keeps legacy intent_id polling and checkout_session_id redirect compatible', async () => {
    vi.useFakeTimers();
    mocks.params.set('checkout_session_id', 'legacy-session');
    const { rerender } = render(<ReturnPage />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(mocks.replace).toHaveBeenCalledWith(
      '/app/onboarding/checkout?session_id=legacy-session',
    );
    expect(fetchMock).not.toHaveBeenCalled();

    mocks.params = new URLSearchParams('intent_id=legacy-intent');
    fetchMock.mockResolvedValue(response(200, { active: false, status: 'pending' }));
    rerender(<ReturnPage />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/billing/intent-status?intent_id=legacy-intent'),
    );
  });

  it('cleans up Turnos polling timers on unmount', async () => {
    vi.useFakeTimers();
    mocks.params.set('appointments_checkout_id', 'checkout-id');
    fetchMock.mockResolvedValue(response(200, checkoutStatus('pending')));

    const { unmount } = render(<ReturnPage />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});

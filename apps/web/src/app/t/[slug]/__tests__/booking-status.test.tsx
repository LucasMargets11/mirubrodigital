import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnchorHTMLAttributes } from 'react';

import type { PublicAppointmentBooking, PublicAppointmentBusiness } from '@/features/appointments/types';

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>
            {children}
        </a>
    ),
}));

vi.mock('@/features/appointments/public-booking', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/features/appointments/public-booking')>();
    return { ...actual, redirectToCheckout: vi.fn() };
});

import {
    BOOKING_POLL_INTERVAL_MS,
    BOOKING_POLL_TIMEOUT_MS,
    deriveBookingView,
    redirectToCheckout,
    shouldPollBooking,
} from '@/features/appointments/public-booking';
import { BookingStatus } from '../booking-status';
import { TurnosFlowClient } from '../turnos-flow-client';

const API = 'http://api.test';
const SLUG = 'mi-negocio';
const TOKEN = '11111111-1111-4111-8111-111111111111';
const BOOKING_URL = `${API}/api/v1/appointments/public/${SLUG}/bookings/${TOKEN}/`;
const CHECKOUT_URL = `${BOOKING_URL}checkout/`;
const MP_URL = 'https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=PREF-SECRET-123';

type FakeResponse = { ok: boolean; status: number; json: () => Promise<unknown> };

function res(status: number, body?: unknown): FakeResponse {
    return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => {
            if (body === undefined) throw new Error('no body');
            return body;
        },
    };
}

function makeBooking(overrides: Partial<PublicAppointmentBooking> = {}): PublicAppointmentBooking {
    return {
        public_token: TOKEN,
        status: 'pending_payment',
        expires_at: new Date(Date.now() + 5 * 60_000).toISOString(),
        start_at: '2026-10-05T10:00:00-03:00',
        end_at: '2026-10-05T10:30:00-03:00',
        customer_name: 'Ana Cliente',
        service: { name: 'Corte', price: '2000.00', duration_minutes: 30 },
        professional: { name: 'Juan Profesional' },
        deposit_amount: '500.00',
        payment_status: null,
        ...overrides,
    };
}

// GET: cola de respuestas (la última queda fija). POST: cola o respuesta pendiente.
let getQueue: FakeResponse[];
let postQueue: Array<FakeResponse | Promise<FakeResponse>>;
let fetchMock: ReturnType<typeof vi.fn>;

function getCalls() {
    return fetchMock.mock.calls.filter(([, init]) => !init || (init as RequestInit).method !== 'POST');
}
function postCalls() {
    return fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST');
}

async function flush(ms = 0) {
    await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
    });
}

function renderStatus(props: Partial<React.ComponentProps<typeof BookingStatus>> = {}) {
    const onRestart = vi.fn();
    const utils = render(
        <BookingStatus apiUrl={API} slug={SLUG} publicToken={TOKEN} onRestart={onRestart} {...props} />,
    );
    return { ...utils, onRestart };
}

const businessData: PublicAppointmentBusiness = {
    business: { name: 'Mi Negocio', slug: SLUG, timezone: 'America/Argentina/Buenos_Aires' },
    categories: [],
    services: [],
} as unknown as PublicAppointmentBusiness;

beforeEach(() => {
    vi.useFakeTimers();
    getQueue = [];
    postQueue = [];
    fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === 'POST') {
            const next = postQueue.shift();
            if (!next) throw new Error('unexpected POST');
            return next;
        }
        if (getQueue.length === 0) throw new Error('unexpected GET');
        return getQueue.length > 1 ? getQueue.shift()! : getQueue[0];
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.mocked(redirectToCheckout).mockClear();
    window.history.replaceState({}, '', `/t/${SLUG}`);
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe('BookingStatus — checkout', () => {
    it('1. pending_payment con hold vigente habilita "Continuar al pago"', () => {
        renderStatus({ initialBooking: makeBooking() });
        expect(screen.getByRole('button', { name: 'Continuar al pago' })).toBeEnabled();
    });

    it('2. reserva sin seña confirmada no muestra checkout', () => {
        renderStatus({ initialBooking: makeBooking({ status: 'confirmed', expires_at: null, deposit_amount: '0.00' }) });
        expect(screen.getByText('Tu turno está confirmado.')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /pago/i })).not.toBeInTheDocument();
    });

    it('3. el click llama al endpoint correcto con body vacío', async () => {
        postQueue.push(res(201, { status: 'pending', checkout_url: MP_URL }));
        renderStatus({ initialBooking: makeBooking() });

        fireEvent.click(screen.getByRole('button', { name: 'Continuar al pago' }));
        await flush();

        expect(postCalls()).toHaveLength(1);
        const [url, init] = postCalls()[0] as [string, RequestInit];
        expect(url).toBe(CHECKOUT_URL);
        expect(init.method).toBe('POST');
        expect(init.body).toBeUndefined();
    });

    it('4. doble click hace un solo POST y deshabilita el botón', async () => {
        let resolvePost!: (value: FakeResponse) => void;
        postQueue.push(new Promise<FakeResponse>((resolve) => (resolvePost = resolve)));
        renderStatus({ initialBooking: makeBooking() });

        const button = screen.getByRole('button', { name: 'Continuar al pago' });
        fireEvent.click(button);
        fireEvent.click(button);
        await flush();

        expect(postCalls()).toHaveLength(1);
        expect(screen.getByRole('button', { name: 'Redirigiendo a Mercado Pago…' })).toBeDisabled();

        resolvePost(res(200, { status: 'pending', checkout_url: MP_URL }));
        await flush();
        expect(redirectToCheckout).toHaveBeenCalledTimes(1);
    });

    it('5. checkout exitoso redirige al checkout_url', async () => {
        postQueue.push(res(201, { status: 'pending', checkout_url: MP_URL }));
        renderStatus({ initialBooking: makeBooking() });

        fireEvent.click(screen.getByRole('button', { name: 'Continuar al pago' }));
        await flush();

        expect(redirectToCheckout).toHaveBeenCalledWith(MP_URL);
    });

    it('checkout_url no http(s) no se sigue', async () => {
        postQueue.push(res(201, { status: 'pending', checkout_url: 'javascript:alert(1)' }));
        getQueue.push(res(200, makeBooking()));
        renderStatus({ initialBooking: makeBooking() });

        fireEvent.click(screen.getByRole('button', { name: 'Continuar al pago' }));
        await flush();

        expect(redirectToCheckout).not.toHaveBeenCalled();
    });
});

describe('Retorno desde Mercado Pago', () => {
    it('6/7. `payment=success` no confirma: se consulta el booking real', async () => {
        getQueue.push(res(200, makeBooking({ payment_status: 'pending' })));
        window.history.replaceState({}, '', `/t/${SLUG}?booking=${TOKEN}&payment=success`);

        render(
            <TurnosFlowClient slug={SLUG} data={businessData} initialBookingToken={TOKEN} paymentHint="success" />,
        );
        expect(screen.getByText('Estamos verificando el estado de tu pago…')).toBeInTheDocument();
        await flush();

        expect(getCalls()[0][0]).toBe(`${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/v1/appointments/public/${SLUG}/bookings/${TOKEN}/`);
        expect(screen.queryByText(/confirmad/i)).not.toBeInTheDocument();
        expect(screen.getByText('Procesando tu pago…')).toBeInTheDocument();
    });

    it('8. confirmed del backend muestra éxito con los datos públicos', async () => {
        getQueue.push(res(200, makeBooking({ status: 'confirmed', payment_status: 'approved' })));
        renderStatus({ paymentHint: 'failure' });
        await flush();

        expect(screen.getByText('Tu turno está confirmado.')).toBeInTheDocument();
        expect(screen.getByText('Corte')).toBeInTheDocument();
        expect(screen.getByText('Juan Profesional')).toBeInTheDocument();
        expect(screen.getByText('05/10/2026 · 10:00')).toBeInTheDocument();
    });

    it('9/10. pending inicia polling y termina al llegar confirmed', async () => {
        getQueue.push(
            res(200, makeBooking({ payment_status: 'pending' })),
            res(200, makeBooking({ payment_status: 'pending' })),
            res(200, makeBooking({ status: 'confirmed', payment_status: 'approved' })),
        );
        renderStatus();
        await flush();
        expect(getCalls()).toHaveLength(1);
        expect(screen.getByText('Procesando tu pago…')).toBeInTheDocument();

        await flush(BOOKING_POLL_INTERVAL_MS);
        expect(getCalls()).toHaveLength(2);

        await flush(BOOKING_POLL_INTERVAL_MS);
        expect(getCalls()).toHaveLength(3);
        expect(screen.getByText('Tu turno está confirmado.')).toBeInTheDocument();

        await flush(BOOKING_POLL_INTERVAL_MS * 5);
        expect(getCalls()).toHaveLength(3);
    });

    it('11. el polling corta al timeout y deja "Actualizar estado" (solo GET)', async () => {
        getQueue.push(res(200, makeBooking({ payment_status: 'pending', expires_at: new Date(Date.now() + 9 * 60_000).toISOString() })));
        renderStatus();
        await flush();

        await flush(BOOKING_POLL_TIMEOUT_MS + BOOKING_POLL_INTERVAL_MS);
        const callsAtTimeout = getCalls().length;
        expect(callsAtTimeout).toBeLessThanOrEqual(Math.ceil(BOOKING_POLL_TIMEOUT_MS / BOOKING_POLL_INTERVAL_MS) + 1);
        expect(screen.getByText('Estamos esperando la confirmación del pago.')).toBeInTheDocument();

        await flush(BOOKING_POLL_INTERVAL_MS * 10);
        expect(getCalls()).toHaveLength(callsAtTimeout);

        fireEvent.click(screen.getByRole('button', { name: 'Actualizar estado' }));
        await flush();
        expect(getCalls()).toHaveLength(callsAtTimeout + 1);
        expect(postCalls()).toHaveLength(0);
    });

    it('12. requires_review muestra el mensaje de revisión, sin confirmar ni ofrecer pago', async () => {
        getQueue.push(res(200, makeBooking({ status: 'expired', payment_status: 'requires_review' })));
        renderStatus({ paymentHint: 'success' });
        await flush();

        expect(
            screen.getByText(/El pago fue recibido, pero necesitamos revisar la reserva antes de confirmarla\./),
        ).toBeInTheDocument();
        expect(screen.queryByText(/turno está confirmado/i)).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Continuar al pago|Intentar nuevamente/ })).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Actualizar estado' })).toBeInTheDocument();
    });

    it('13. expired sin pago muestra reserva vencida y permite volver a empezar', async () => {
        getQueue.push(res(200, makeBooking({ status: 'expired', payment_status: null })));
        const { onRestart } = renderStatus();
        await flush();

        expect(screen.getByText(/El tiempo para completar la reserva venció/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: 'Elegir otro horario' }));
        expect(onRestart).toHaveBeenCalled();
        expect(postCalls()).toHaveLength(0);
    });

    it.each(['rejected', 'cancelled', 'error'] as const)(
        '14a. %s + hold vigente: reintento refetchea y recién después llama al mismo checkout',
        async (paymentStatus) => {
            getQueue.push(res(200, makeBooking({ payment_status: paymentStatus })));
            postQueue.push(res(201, { status: 'pending', checkout_url: MP_URL }));
            renderStatus({ paymentHint: 'failure' });
            await flush();

            fireEvent.click(screen.getByRole('button', { name: 'Intentar nuevamente' }));
            await flush();

            const order = fetchMock.mock.calls.map(([, init]) => (init as RequestInit | undefined)?.method ?? 'GET');
            expect(order).toEqual(['GET', 'GET', 'POST']);
            expect(postCalls()[0][0]).toBe(CHECKOUT_URL);
            expect(redirectToCheckout).toHaveBeenCalledWith(MP_URL);
        },
    );

    it('14d. si el refetch previo al reintento ya no es retryable, no hay POST', async () => {
        getQueue.push(
            res(200, makeBooking({ payment_status: 'rejected' })),
            res(200, makeBooking({ status: 'confirmed', payment_status: 'approved' })),
        );
        renderStatus();
        await flush();

        fireEvent.click(screen.getByRole('button', { name: 'Intentar nuevamente' }));
        await flush();

        expect(postCalls()).toHaveLength(0);
        expect(screen.getByText('Tu turno está confirmado.')).toBeInTheDocument();
    });

    it('6C.1-1/2. pending no ofrece checkout (ni durante ni después del polling), solo "Actualizar estado"', async () => {
        getQueue.push(res(200, makeBooking({ payment_status: 'pending' })));
        renderStatus({ paymentHint: 'pending' });
        await flush();
        expect(screen.queryByRole('button', { name: /pago|Intentar nuevamente/i })).not.toBeInTheDocument();

        await flush(BOOKING_POLL_TIMEOUT_MS + BOOKING_POLL_INTERVAL_MS);
        expect(screen.getByText('Estamos esperando la confirmación del pago.')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Actualizar estado' })).toBeEnabled();
        expect(screen.queryByRole('button', { name: /pago|Intentar nuevamente/i })).not.toBeInTheDocument();
        expect(screen.queryByText(/Continuar al pago/)).not.toBeInTheDocument();
        expect(postCalls()).toHaveLength(0);
    });

    it.each([null, 'rejected', 'pending', 'uncertain'] as const)(
        '6C.1-8. expired (pago %s) nunca inicia otro checkout',
        async (paymentStatus) => {
            getQueue.push(res(200, makeBooking({ status: 'expired', payment_status: paymentStatus })));
            renderStatus();
            await flush(BOOKING_POLL_TIMEOUT_MS + BOOKING_POLL_INTERVAL_MS);

            expect(screen.queryByRole('button', { name: /Continuar al pago|Intentar nuevamente/ })).not.toBeInTheDocument();
            expect(postCalls()).toHaveLength(0);
        },
    );

    it('14b. payment_provider_error: refetch primero, reintento solo si el backend lo deja retryable', async () => {
        postQueue.push(res(502, { code: 'payment_provider_error', detail: 'x' }));
        getQueue.push(res(200, makeBooking({ payment_status: 'error' })));
        renderStatus({ initialBooking: makeBooking() });

        fireEvent.click(screen.getByRole('button', { name: 'Continuar al pago' }));
        await flush();

        const order = fetchMock.mock.calls.map(([, init]) => (init as RequestInit | undefined)?.method ?? 'GET');
        expect(order).toEqual(['POST', 'GET']);
        expect(screen.getByRole('button', { name: 'Intentar nuevamente' })).toBeEnabled();
    });

    it('14c. rejected con hold vencido no ofrece reintento', async () => {
        getQueue.push(res(200, makeBooking({ payment_status: 'rejected', expires_at: new Date(Date.now() - 1000).toISOString() })));
        renderStatus();
        await flush();
        expect(screen.queryByRole('button', { name: 'Intentar nuevamente' })).not.toBeInTheDocument();
    });

    it('15. uncertain no ofrece un segundo pago', async () => {
        getQueue.push(res(200, makeBooking({ payment_status: 'uncertain' })));
        renderStatus();
        await flush();

        expect(screen.getByText('Estamos verificando el estado del pago')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Continuar al pago|Intentar nuevamente/ })).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Actualizar estado' })).toBeInTheDocument();
    });

    it('16. payment_in_progress hace refetch sin error genérico', async () => {
        postQueue.push(res(409, { code: 'payment_in_progress', detail: 'x' }));
        getQueue.push(res(200, makeBooking({ payment_status: 'uncertain' })));
        renderStatus({ initialBooking: makeBooking() });

        fireEvent.click(screen.getByRole('button', { name: 'Continuar al pago' }));
        await flush();

        expect(getCalls()).toHaveLength(1);
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        expect(screen.getByText('Estamos verificando el estado del pago')).toBeInTheDocument();
    });

    it('17. payment_uncertain pasa a "verificando" y no crea otro checkout', async () => {
        postQueue.push(res(502, { code: 'payment_uncertain', detail: 'x' }));
        getQueue.push(res(200, makeBooking({ payment_status: 'uncertain' })));
        renderStatus({ initialBooking: makeBooking() });

        fireEvent.click(screen.getByRole('button', { name: 'Continuar al pago' }));
        await flush(BOOKING_POLL_TIMEOUT_MS);

        expect(postCalls()).toHaveLength(1);
        expect(redirectToCheckout).not.toHaveBeenCalled();
        expect(screen.getByText('Estamos verificando el estado del pago')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Continuar al pago|Intentar nuevamente/ })).not.toBeInTheDocument();
    });

    it('payment_unavailable muestra mensaje sin detalles técnicos', async () => {
        postQueue.push(res(503, { code: 'payment_unavailable', detail: 'mp_not_connected' }));
        getQueue.push(res(200, makeBooking()));
        renderStatus({ initialBooking: makeBooking() });

        fireEvent.click(screen.getByRole('button', { name: 'Continuar al pago' }));
        await flush();

        expect(screen.getByRole('alert')).toHaveTextContent('No pudimos iniciar el pago en este momento.');
        expect(document.body.textContent).not.toContain('mp_not_connected');
        expect(screen.getByRole('button', { name: 'Continuar al pago' })).toBeEnabled();
    });

    it('expired del checkout refresca y muestra vencida', async () => {
        postQueue.push(res(409, { code: 'expired', detail: 'x' }));
        getQueue.push(res(200, makeBooking({ status: 'expired' })));
        renderStatus({ initialBooking: makeBooking() });

        fireEvent.click(screen.getByRole('button', { name: 'Continuar al pago' }));
        await flush();

        expect(getCalls()).toHaveLength(1);
        expect(screen.getByText('Tu reserva venció')).toBeInTheDocument();
    });

    it('18. token inválido muestra reserva no encontrada', async () => {
        getQueue.push(res(404));
        renderStatus();
        await flush();
        expect(screen.getByText('No encontramos tu reserva')).toBeInTheDocument();
    });

    it('19. reload con ?booking= restaura la pantalla de estado sin rehacer el flujo', async () => {
        getQueue.push(res(200, makeBooking()));
        window.history.replaceState({}, '', `/t/${SLUG}?booking=${TOKEN}&payment=pending`);

        render(<TurnosFlowClient slug={SLUG} data={businessData} initialBookingToken={TOKEN} paymentHint="pending" />);
        await flush();

        expect(screen.queryByText('Elegí un servicio')).not.toBeInTheDocument();
        expect(screen.getByText('Tu horario está reservado temporalmente')).toBeInTheDocument();
        // La pista `payment=` se limpia; queda solo el token.
        expect(window.location.search).toBe(`?booking=${TOKEN}`);
    });

    it('20. ids de provider / secretos nunca aparecen en la UI', async () => {
        getQueue.push(
            res(200, {
                ...makeBooking({ payment_status: 'requires_review' }),
                provider_payment_id: 'PROVIDER-PAY-999',
                provider_preference_id: 'PREF-SECRET-123',
                external_reference: 'APPOINTMENT_PAYMENT-abc',
                review_reason: 'slot_conflict',
            }),
        );
        const { container } = renderStatus();
        await flush();

        const text = container.textContent ?? '';
        for (const needle of ['PROVIDER-PAY-999', 'PREF-SECRET-123', 'APPOINTMENT_PAYMENT-', 'slot_conflict', TOKEN]) {
            expect(text).not.toContain(needle);
        }
    });

    it('countdown en cero vuelve a consultar al backend', async () => {
        getQueue.push(res(200, makeBooking({ status: 'expired' })));
        renderStatus({ initialBooking: makeBooking({ expires_at: new Date(Date.now() + 3_000).toISOString() }) });
        expect(getCalls()).toHaveLength(0);

        await flush(4_000);
        expect(getCalls()).toHaveLength(1);
        expect(screen.getByText('Tu reserva venció')).toBeInTheDocument();
    });
});

describe('deriveBookingView / shouldPollBooking', () => {
    it('mapea estados según el backend', () => {
        expect(deriveBookingView(makeBooking())).toBe('awaiting_checkout');
        expect(deriveBookingView(makeBooking({ payment_status: 'pending' }))).toBe('payment_pending');
        expect(deriveBookingView(makeBooking({ payment_status: 'creating' }))).toBe('payment_pending');
        expect(deriveBookingView(makeBooking({ payment_status: 'cancelled' }))).toBe('payment_failed');
        expect(deriveBookingView(makeBooking({ payment_status: 'uncertain' }))).toBe('verifying');
        expect(deriveBookingView(makeBooking({ status: 'cancelled' }))).toBe('cancelled');
        expect(deriveBookingView(makeBooking({ status: 'confirmed', payment_status: 'requires_review' }))).toBe(
            'confirmed',
        );
    });

    it('solo hace polling cuando el webhook todavía puede cambiar el resultado', () => {
        expect(shouldPollBooking(makeBooking())).toBe(false);
        expect(shouldPollBooking(makeBooking({ payment_status: 'pending' }))).toBe(true);
        expect(shouldPollBooking(makeBooking({ status: 'expired', payment_status: 'pending' }))).toBe(true);
        expect(shouldPollBooking(makeBooking({ payment_status: 'uncertain' }))).toBe(false);
        expect(shouldPollBooking(makeBooking({ status: 'confirmed', payment_status: 'approved' }))).toBe(false);
    });
});

describe('Slice 6D — contacto por WhatsApp', () => {
    const WA_CONFIRMED =
        'https://wa.me/5491112345678?text=Hola%2C%20reserv%C3%A9%20un%20turno%20en%20Mi%20Negocio%20para%20Corte%20el%2005%2F10%2F2026%20a%20las%2010%3A00.%20Mi%20reserva%20est%C3%A1%20confirmada.';
    const WA_REVIEW =
        'https://wa.me/5491112345678?text=Hola%2C%20hice%20una%20reserva%20y%20el%20sistema%20indica%20que%20necesita%20revisi%C3%B3n.';

    let openSpy: ReturnType<typeof vi.spyOn>;
    beforeEach(() => {
        openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    });
    afterEach(() => {
        openSpy.mockRestore();
    });

    const confirmed = (url: string | null) =>
        makeBooking({ status: 'confirmed', expires_at: null, payment_status: 'approved', contact_whatsapp_url: url });

    it('1. confirmed + URL muestra "Abrir WhatsApp"', () => {
        renderStatus({ initialBooking: confirmed(WA_CONFIRMED) });
        expect(screen.getByRole('button', { name: 'Abrir WhatsApp' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Contactar al negocio' })).not.toBeInTheDocument();
    });

    it('2. confirmed sin URL no muestra botón', () => {
        renderStatus({ initialBooking: confirmed(null) });
        expect(screen.getByText('Tu turno está confirmado.')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /whatsapp|contactar/i })).not.toBeInTheDocument();
    });

    it('3. requires_review + URL muestra "Contactar al negocio" y no afirma confirmación', () => {
        renderStatus({
            initialBooking: makeBooking({
                status: 'expired',
                payment_status: 'requires_review',
                contact_whatsapp_url: WA_REVIEW,
            }),
        });
        expect(screen.getByRole('button', { name: 'Contactar al negocio' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Abrir WhatsApp' })).not.toBeInTheDocument();
        expect(screen.queryByText(/turno está confirmado/i)).not.toBeInTheDocument();
    });

    it.each([
        ['4. pending', { status: 'pending_payment', payment_status: 'pending' }],
        ['5. uncertain', { status: 'pending_payment', payment_status: 'uncertain' }],
        ['6. expired', { status: 'expired', payment_status: 'rejected' }],
    ] as const)('%s no muestra botón (aunque llegue una URL)', (_label, overrides) => {
        renderStatus({ initialBooking: makeBooking({ ...overrides, contact_whatsapp_url: WA_CONFIRMED }) });
        expect(screen.queryByRole('button', { name: /whatsapp|contactar al negocio/i })).not.toBeInTheDocument();
    });

    it('7/9. el click abre la URL exacta en otra pestaña con noopener,noreferrer', () => {
        renderStatus({ initialBooking: confirmed(WA_CONFIRMED) });
        fireEvent.click(screen.getByRole('button', { name: 'Abrir WhatsApp' }));
        expect(openSpy).toHaveBeenCalledTimes(1);
        expect(openSpy).toHaveBeenCalledWith(WA_CONFIRMED, '_blank', 'noopener,noreferrer');
    });

    it('8. no abre WhatsApp automáticamente al cargar ni al refrescar', async () => {
        getQueue.push(res(200, confirmed(WA_CONFIRMED)));
        renderStatus();
        await flush();
        expect(screen.getByRole('button', { name: 'Abrir WhatsApp' })).toBeInTheDocument();
        await flush(60_000);
        expect(openSpy).not.toHaveBeenCalled();
    });

    it('URL que no es https://wa.me se ignora', () => {
        for (const bad of ['javascript:alert(1)', 'https://evil.example/wa.me/549', 'http://wa.me/549111', 'data:text/html,x']) {
            const { unmount } = renderStatus({ initialBooking: confirmed(bad) });
            expect(screen.queryByRole('button', { name: 'Abrir WhatsApp' })).not.toBeInTheDocument();
            unmount();
        }
    });

    it('10. ningún dato financiero ni token aparece en la UI del botón', () => {
        const { container } = renderStatus({ initialBooking: confirmed(WA_CONFIRMED) });
        const text = container.textContent ?? '';
        expect(text).not.toContain(TOKEN);
        expect(text).not.toContain('wa.me');
        expect(text).not.toMatch(/Seña|\$ 500/);
        expect(container.innerHTML).not.toContain('href="https://wa.me');
    });
});

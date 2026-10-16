import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AnchorHTMLAttributes } from 'react';

import type { PublicAppointmentBusiness, PublicAppointmentProfessional } from '@/features/appointments/types';

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>
            {children}
        </a>
    ),
}));

import { TurnosFlowClient } from '../turnos-flow-client';

// Slice 7B.1: los profesionales del servicio se resuelven contra el backend;
// un error al cargarlos NUNCA se interpreta como "servicio sin profesionales".

const SLUG = 'mi-negocio';
const DATE = '2030-03-04';

const service = (id: string, name: string) => ({
    id,
    name,
    description: '',
    duration_minutes: 30,
    price: '1000.00',
    category: null,
});

const businessData = {
    business: { name: 'Mi Negocio', slug: SLUG, timezone: 'America/Argentina/Buenos_Aires' },
    categories: [],
    services: [service('svc-plain', 'Consulta'), service('svc-pro', 'Corte'), service('svc-pro2', 'Color')],
} as unknown as PublicAppointmentBusiness;

const ANA: PublicAppointmentProfessional = { id: 'prof-ana', name: 'Ana', description: '' };
const BRUNO: PublicAppointmentProfessional = { id: 'prof-bruno', name: 'Bruno', description: '' };

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

type Handler = FakeResponse | Promise<FakeResponse> | Error;

// Cola de respuestas por endpoint de profesionales (`?service=<id>`).
let professionalsQueue: Record<string, Handler[]>;
let fetchMock: ReturnType<typeof vi.fn>;

function callsTo(fragment: string) {
    return fetchMock.mock.calls.filter(([url]) => String(url).includes(fragment));
}

function bookingBodies() {
    return callsTo('/bookings/').map(([, init]) => JSON.parse((init as RequestInit).body as string));
}

beforeEach(() => {
    professionalsQueue = {};
    fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const u = new URL(url);
        if (u.pathname.endsWith('/professionals/')) {
            const next = professionalsQueue[u.searchParams.get('service') ?? '']?.shift();
            if (!next) throw new Error(`unexpected professionals GET ${url}`);
            if (next instanceof Error) throw next;
            return next;
        }
        if (u.pathname.endsWith('/availability/')) {
            return res(200, {
                date: DATE,
                service: u.searchParams.get('service'),
                professional: u.searchParams.get('professional'),
                slots: [{ start: `${DATE}T10:00:00-03:00`, end: `${DATE}T10:30:00-03:00` }],
            });
        }
        if (u.pathname.endsWith('/bookings/') && init?.method === 'POST') {
            return res(400, { detail: ['stop'] });
        }
        throw new Error(`unexpected fetch ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', `/t/${SLUG}`);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

function renderFlow() {
    return render(<TurnosFlowClient slug={SLUG} data={businessData} />);
}

function chooseService(name: string) {
    fireEvent.click(screen.getByRole('button', { name: new RegExp(name) }));
}

/** Abre el calendario propio, navega al mes de `date` y elige el día. */
async function pickDate(date: string) {
    fireEvent.click(await screen.findByRole('button', { name: /^Fecha:/ }));
    const [year, month] = date.split('-').map(Number);
    const monthName = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'][month - 1];
    for (let i = 0; i < 240 && !screen.queryByRole('heading', { name: new RegExp(`${monthName} ${year}`, 'i') }); i++) {
        fireEvent.click(screen.getByRole('button', { name: 'Mes siguiente' }));
    }
    fireEvent.click(document.querySelector(`[data-date="${date}"]`) as HTMLButtonElement);
}

async function pickDateSlotAndSubmit() {
    await pickDate(DATE);
    fireEvent.click(await screen.findByRole('button', { name: '10:00' }));
    fireEvent.change(screen.getByLabelText('Nombre y apellido'), { target: { value: 'Juana' } });
    fireEvent.change(screen.getByLabelText('Teléfono'), { target: { value: '1122334455' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));
    await waitFor(() => expect(callsTo('/bookings/')).toHaveLength(1));
}

async function expectProfessionalsError() {
    expect(await screen.findByText('No pudimos cargar los profesionales.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument();
    // No avanza a fecha/horario ni consulta disponibilidad o reserva.
    expect(screen.queryByRole('button', { name: /^Fecha:/ })).not.toBeInTheDocument();
    expect(callsTo('/availability/')).toHaveLength(0);
    expect(callsTo('/bookings/')).toHaveLength(0);
}

describe('TurnosFlowClient — profesionales (Slice 7B.1)', () => {
    it('1. profesionales=[] → flujo sin profesional', async () => {
        professionalsQueue['svc-plain'] = [res(200, [])];
        renderFlow();
        chooseService('Consulta');

        expect(await screen.findByText('Elegí fecha y horario')).toBeInTheDocument();
        await pickDateSlotAndSubmit();

        const availabilityUrl = new URL(String(callsTo('/availability/')[0][0]));
        expect(availabilityUrl.searchParams.has('professional')).toBe(false);
        expect(bookingBodies()[0]).toMatchObject({ service: 'svc-plain', professional: null });
    });

    it('2. profesionales presentes → selección obligatoria', async () => {
        professionalsQueue['svc-pro'] = [res(200, [ANA, BRUNO])];
        renderFlow();
        chooseService('Corte');

        expect(await screen.findByText('Elegí un profesional')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /^Fecha:/ })).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Ana' }));
        await pickDateSlotAndSubmit();

        const availabilityUrl = new URL(String(callsTo('/availability/')[0][0]));
        expect(availabilityUrl.searchParams.get('professional')).toBe('prof-ana');
        expect(bookingBodies()[0]).toMatchObject({ service: 'svc-pro', professional: 'prof-ana' });
    });

    it('3. 429 → error, sin fallback', async () => {
        professionalsQueue['svc-pro'] = [res(429, { detail: 'throttled' })];
        renderFlow();
        chooseService('Corte');
        await expectProfessionalsError();
    });

    it('4. 500 → error, sin fallback', async () => {
        professionalsQueue['svc-pro'] = [res(500)];
        renderFlow();
        chooseService('Corte');
        await expectProfessionalsError();
    });

    it('5. error de red → error, sin fallback', async () => {
        professionalsQueue['svc-pro'] = [new TypeError('Failed to fetch')];
        renderFlow();
        chooseService('Corte');
        await expectProfessionalsError();
    });

    it('body 200 que no es lista → error, sin fallback', async () => {
        professionalsQueue['svc-pro'] = [res(200, { detail: 'unexpected' })];
        renderFlow();
        chooseService('Corte');
        await expectProfessionalsError();
    });

    it('6. Reintentar vuelve a llamar al endpoint', async () => {
        professionalsQueue['svc-pro'] = [res(503), res(200, [ANA])];
        renderFlow();
        chooseService('Corte');
        await expectProfessionalsError();

        fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));

        expect(await screen.findByRole('button', { name: 'Ana' })).toBeInTheDocument();
        expect(callsTo('/professionals/')).toHaveLength(2);
        expect(String(callsTo('/professionals/')[1][0])).toContain('service=svc-pro');
        expect(screen.queryByText('No pudimos cargar los profesionales.')).not.toBeInTheDocument();
    });

    it('7. nunca reserva con professional=null por un error de fetch', async () => {
        professionalsQueue['svc-pro'] = [new TypeError('Failed to fetch'), res(500), res(200, [ANA])];
        renderFlow();
        chooseService('Corte');
        await expectProfessionalsError();
        fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
        await screen.findByText('No pudimos cargar los profesionales.');
        await waitFor(() => expect(callsTo('/professionals/')).toHaveLength(2));
        expect(screen.queryByRole('button', { name: /^Fecha:/ })).not.toBeInTheDocument();

        // Recién con la lista real se puede avanzar, y siempre con profesional.
        fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
        fireEvent.click(await screen.findByRole('button', { name: 'Ana' }));
        await pickDateSlotAndSubmit();

        const bodies = bookingBodies();
        expect(bodies).toHaveLength(1);
        expect(bodies[0].professional).toBe('prof-ana');
        expect(bodies.some((b) => b.professional === null)).toBe(false);
    });

    it('8. cambiar de servicio limpia el profesional elegido', async () => {
        professionalsQueue['svc-pro'] = [res(200, [ANA])];
        professionalsQueue['svc-pro2'] = [res(200, [BRUNO])];
        renderFlow();

        chooseService('Corte');
        fireEvent.click(await screen.findByRole('button', { name: 'Ana' }));
        expect(await screen.findByText('Corte · Ana')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: '← Volver' }));
        fireEvent.click(await screen.findByRole('button', { name: '← Volver' }));
        chooseService('Color');

        expect(await screen.findByRole('button', { name: 'Bruno' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Ana' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /^Fecha:/ })).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Bruno' }));
        await pickDateSlotAndSubmit();
        expect(bookingBodies()[0]).toMatchObject({ service: 'svc-pro2', professional: 'prof-bruno' });
    });

    it('8b. una respuesta tardía del servicio anterior se descarta', async () => {
        let resolveFirst!: (r: FakeResponse) => void;
        professionalsQueue['svc-pro'] = [new Promise<FakeResponse>((resolve) => (resolveFirst = resolve))];
        professionalsQueue['svc-plain'] = [res(200, [])];
        renderFlow();

        chooseService('Corte');
        expect(await screen.findByText('Cargando profesionales…')).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: '← Volver' }));
        chooseService('Consulta');
        expect(await screen.findByText('Elegí fecha y horario')).toBeInTheDocument();

        resolveFirst(res(200, [ANA]));
        await waitFor(() => expect(screen.queryByRole('button', { name: 'Ana' })).not.toBeInTheDocument());
        expect(screen.getByText('Elegí fecha y horario')).toBeInTheDocument();
        expect(screen.getByText('Consulta')).toBeInTheDocument();
    });
});

describe('TurnosFlowClient — calendario de fecha (Slice UI 02)', () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    it('elegir fecha dispara availability y la reserva sigue funcionando', async () => {
        professionalsQueue['svc-plain'] = [res(200, [])];
        renderFlow();
        chooseService('Consulta');
        expect(await screen.findByText('Elegí fecha y horario')).toBeInTheDocument();
        expect(document.querySelector('input[type="date"]')).toBeNull();

        await pickDate(DATE);
        await waitFor(() => expect(callsTo('/availability/')).toHaveLength(1));
        const url = new URL(String(callsTo('/availability/')[0][0]));
        expect(url.searchParams.get('date')).toBe(DATE);
        expect(url.searchParams.get('service')).toBe('svc-plain');
        expect(screen.getByRole('button', { name: /^Fecha:/ })).toHaveTextContent('lunes, 4 de marzo de 2030');
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(await screen.findByRole('button', { name: '10:00' })).toBeInTheDocument();
    });

    it('el mínimo es el "hoy" del Business, no el del navegador', async () => {
        // 02:00 UTC del 4/3 = 23:00 del 3/3 en Buenos Aires.
        vi.useFakeTimers({ toFake: ['Date'] });
        vi.setSystemTime(new Date('2030-03-04T02:00:00Z'));
        professionalsQueue['svc-plain'] = [res(200, [])];
        renderFlow();
        chooseService('Consulta');
        fireEvent.click(await screen.findByRole('button', { name: /^Fecha:/ }));

        const today = document.querySelector('[data-date="2030-03-03"]') as HTMLButtonElement;
        expect(today).toBeEnabled();
        expect(today).toHaveAttribute('aria-current', 'date');
        expect(document.querySelector('[data-date="2030-03-02"]')).toBeDisabled();
        expect(screen.getByRole('button', { name: 'Mes anterior' })).toBeDisabled();
        expect(callsTo('/availability/')).toHaveLength(0);
    });
});

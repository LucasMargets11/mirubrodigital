// Slice 7D.1: toda la agenda del panel usa Business.timezone, no la zona del
// navegador. Simulamos el navegador cambiando `process.env.TZ` por test
// (Node recalcula la zona local al asignarla).
process.env.TZ = 'America/Argentina/Buenos_Aires';

import { act, fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Appointment, AppointmentListParams, AppointmentPaymentSummary } from '@/features/appointments/types';
import { groupAppointmentsByDay, startOfWeek, weekRange } from '@/features/appointments/week';
import {
    DEFAULT_BUSINESS_TIME_ZONE,
    dateInTimeZone,
    resolveBusinessTimeZone,
    timeInTimeZone,
    todayInTimeZone,
} from '@/lib/business-time';

const AR = 'America/Argentina/Buenos_Aires';
const MADRID = 'Europe/Madrid';

let appointmentsData: Appointment[] = [];
const useAppointmentsSpy = vi.fn();
const availabilitySpy = vi.fn();
const updateSpy = vi.fn();
let slots: { start: string; end: string }[] = [];

vi.mock('@/features/appointments/hooks', () => ({
    useAppointments: (params: unknown) => {
        useAppointmentsSpy(params);
        return { data: appointmentsData, isLoading: false, isError: false };
    },
    useAppointmentServices: () => ({
        data: [{ id: 's1', name: 'Corte', duration_minutes: 30, price: '10000.00', is_active: true, category: null }],
    }),
    useAppointmentProfessionals: () => ({ data: [] }),
    useAppointmentAvailability: (params: unknown) => {
        availabilitySpy(params);
        return { data: { slots }, isLoading: false };
    },
    useCreateAppointment: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useUpdateAppointment: () => ({ mutateAsync: updateSpy, isPending: false }),
    useCancelAppointment: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('@/components/ui/modal', () => ({
    Modal: ({ open, title, children }: { open: boolean; title: string; children: ReactNode }) =>
        open ? (
            <div role="dialog" aria-label={title}>
                {children}
            </div>
        ) : null,
}));

import { TurnosClient } from '../turnos-client';

function setBrowserTZ(tz: string) {
    process.env.TZ = tz;
}

function summary(overrides: Partial<AppointmentPaymentSummary> = {}): AppointmentPaymentSummary {
    return {
        status: 'approved',
        amount: '3500.00',
        currency: 'ARS',
        paid_at: '2026-10-05T02:45:00Z', // 23:45 del 4 en AR; 04:45 del 5 en Madrid
        requires_review: false,
        review_reason: null,
        ...overrides,
    };
}

/** `startAt` con offset explícito, p.ej. '2026-10-04T23:30:00-03:00'. */
function appt(id: string, startAt: string, overrides: Partial<Appointment> = {}): Appointment {
    const start = new Date(startAt);
    return {
        id,
        service: { id: 's1', name: 'Corte', duration_minutes: 30, price: '10000.00', is_active: true, category: null },
        professional: null,
        customer_id: null,
        customer_name: `Cliente ${id}`,
        customer_phone: '1155554444',
        customer_email: '',
        start_at: startAt,
        end_at: new Date(start.getTime() + 30 * 60_000).toISOString(),
        status: 'confirmed',
        status_display: 'Confirmado',
        effective_status: 'confirmed',
        effective_status_display: 'Confirmado',
        expires_at: null,
        payment_summary: null,
        notes: '',
        source: 'manual',
        service_name: 'Corte',
        service_duration_minutes: 30,
        service_price: '10000.00',
        deposit_type: 'fixed',
        deposit_value: '3500.00',
        created_at: '2026-09-20T12:00:00Z',
        updated_at: '2026-09-20T12:00:00Z',
        ...overrides,
    };
}

function lastParams(): AppointmentListParams {
    return useAppointmentsSpy.mock.calls.at(-1)?.[0] as AppointmentListParams;
}

function day(date: string) {
    return within(screen.getByTestId(`week-day-${date}`));
}

// Domingo 4/10 23:30 en Buenos Aires = lunes 5/10 04:30 en Madrid.
const SUNDAY_LATE_AR = '2026-10-04T23:30:00-03:00';

beforeEach(() => {
    appointmentsData = [];
    slots = [];
    useAppointmentsSpy.mockClear();
    availabilitySpy.mockClear();
    updateSpy.mockReset();
    window.history.replaceState({}, '', '/app/turnos/turnos');
});

afterEach(() => {
    vi.useRealTimers();
    setBrowserTZ(AR);
});

describe('helpers de business-time', () => {
    it('la simulación de zona del navegador funciona', () => {
        setBrowserTZ(MADRID);
        expect(new Date(SUNDAY_LATE_AR).getDate()).toBe(5);
        setBrowserTZ(AR);
        expect(new Date(SUNDAY_LATE_AR).getDate()).toBe(4);
    });

    it('día y hora salen de la zona pedida, no del navegador', () => {
        for (const browser of [AR, MADRID, 'Asia/Tokyo', 'UTC']) {
            setBrowserTZ(browser);
            expect(dateInTimeZone(SUNDAY_LATE_AR, AR)).toBe('2026-10-04');
            expect(timeInTimeZone(SUNDAY_LATE_AR, AR)).toBe('23:30');
            expect(dateInTimeZone(SUNDAY_LATE_AR, MADRID)).toBe('2026-10-05');
            expect(timeInTimeZone(SUNDAY_LATE_AR, MADRID)).toBe('04:30');
        }
    });

    it('fallback explícito ante timezone faltante o inválida (nunca UTC)', () => {
        expect(resolveBusinessTimeZone(undefined)).toBe(DEFAULT_BUSINESS_TIME_ZONE);
        expect(resolveBusinessTimeZone('')).toBe(DEFAULT_BUSINESS_TIME_ZONE);
        expect(resolveBusinessTimeZone('Not/AZone')).toBe(DEFAULT_BUSINESS_TIME_ZONE);
        expect(resolveBusinessTimeZone(MADRID)).toBe(MADRID);
        expect(DEFAULT_BUSINESS_TIME_ZONE).toBe(AR);
    });

    // 6, 7, 11: semana lunes-domingo pura, igual en cualquier zona (incl. DST).
    it('semana, cambio de mes y de año no dependen del navegador', () => {
        for (const browser of [AR, MADRID, 'Pacific/Kiritimati', 'America/Los_Angeles']) {
            setBrowserTZ(browser);
            expect(weekRange('2026-10-01')).toMatchObject({ from: '2026-09-28', to: '2026-10-04' });
            expect(weekRange('2027-01-01')).toMatchObject({ from: '2026-12-28', to: '2027-01-03' });
            expect(startOfWeek('2026-10-25')).toBe('2026-10-19'); // DST de Europa
            expect(weekRange('2026-11-01').days).toHaveLength(7);
        }
    });

    it('agrupa por día del Business en cambio de mes y de año', () => {
        setBrowserTZ('Asia/Tokyo');
        const monthEnd = appt('m', '2026-09-30T23:45:00-03:00'); // Tokio: 1/10
        const yearEnd = appt('y', '2026-12-31T23:30:00-03:00'); // Tokio: 1/1/2027
        const sep = groupAppointmentsByDay([monthEnd], weekRange('2026-09-30').days, AR);
        expect(sep['2026-09-30'].map((a) => a.id)).toEqual(['m']);
        const dec = groupAppointmentsByDay([yearEnd], weekRange('2026-12-31').days, AR);
        expect(dec['2026-12-31'].map((a) => a.id)).toEqual(['y']);
        expect(dec['2027-01-01']).toEqual([]);
    });
});

describe('TurnosClient con Business.timezone', () => {
    // 1
    it('browser -03 / business -03: comportamiento normal', () => {
        setBrowserTZ(AR);
        appointmentsData = [appt('late', SUNDAY_LATE_AR)];
        render(<TurnosClient canManage={false} timeZone={AR} initialDate="2026-10-01" initialView="week" />);
        expect(day('2026-10-04').getByText('Cliente late')).toBeInTheDocument();
        expect(day('2026-10-04').getByText('23:30')).toBeInTheDocument();
    });

    // 2, 5, 9, 10
    it('browser Madrid / business Buenos Aires: domingo 23:30 sigue en domingo', () => {
        setBrowserTZ(MADRID);
        appointmentsData = [appt('late', SUNDAY_LATE_AR)];
        render(<TurnosClient canManage={false} timeZone={AR} initialDate="2026-10-01" initialView="week" />);
        expect(lastParams()).toMatchObject({ date_from: '2026-09-28', date_to: '2026-10-04' });
        expect(day('2026-10-04').getByText('Cliente late')).toBeInTheDocument();
        expect(day('2026-10-04').getByText('23:30')).toBeInTheDocument();
        expect(screen.queryByText('04:30')).not.toBeInTheDocument();
    });

    // 3
    it('browser Buenos Aires / business Madrid', () => {
        setBrowserTZ(AR);
        // Lunes 5/10 00:30 en Madrid = domingo 4/10 19:30 en Buenos Aires.
        appointmentsData = [appt('madrid', '2026-10-05T00:30:00+02:00')];
        render(<TurnosClient canManage={false} timeZone={MADRID} initialDate="2026-10-05" initialView="week" />);
        expect(lastParams()).toMatchObject({ date_from: '2026-10-05', date_to: '2026-10-11' });
        expect(day('2026-10-05').getByText('Cliente madrid')).toBeInTheDocument();
        expect(day('2026-10-05').getByText('00:30')).toBeInTheDocument();
    });

    // 4
    describe('"Hoy" usa la fecha del Business', () => {
        beforeEach(() => {
            vi.useFakeTimers({ toFake: ['Date'] });
        });

        it('business Buenos Aires, navegador Madrid (ya es lunes allá)', () => {
            setBrowserTZ(MADRID);
            vi.setSystemTime(new Date(SUNDAY_LATE_AR));
            expect(todayInTimeZone(AR)).toBe('2026-10-04');
            render(<TurnosClient canManage={false} timeZone={AR} />);
            expect(lastParams()).toMatchObject({ date: '2026-10-04' });
            fireEvent.click(screen.getByRole('button', { name: 'Semana' }));
            expect(lastParams()).toMatchObject({ date_from: '2026-09-28', date_to: '2026-10-04' });
            fireEvent.click(screen.getByRole('button', { name: 'Semana siguiente' }));
            fireEvent.click(screen.getByRole('button', { name: 'Hoy' }));
            expect(lastParams()).toMatchObject({ date_from: '2026-09-28', date_to: '2026-10-04' });
        });

        it('business Madrid, navegador Buenos Aires (allá ya es mañana)', () => {
            setBrowserTZ(AR);
            vi.setSystemTime(new Date('2026-10-04T20:00:00-03:00')); // 01:00 del 5 en Madrid
            render(<TurnosClient canManage={false} timeZone={MADRID} />);
            expect(lastParams()).toMatchObject({ date: '2026-10-05' });
        });

        it('sin timezone en sesión usa el default del proyecto, no UTC', () => {
            setBrowserTZ('UTC');
            vi.setSystemTime(new Date(SUNDAY_LATE_AR)); // en UTC ya es 5/10
            render(<TurnosClient canManage={false} />);
            expect(lastParams()).toMatchObject({ date: '2026-10-04' });
        });
    });

    // 8, 10
    it('vista Día: fecha y horas en la zona del Business', () => {
        setBrowserTZ(MADRID);
        appointmentsData = [
            appt('late', SUNDAY_LATE_AR, {
                status: 'pending_payment',
                effective_status: 'pending_payment',
                effective_status_display: 'Pendiente de pago',
                expires_at: '2026-10-05T02:40:00Z', // 23:40 AR
            }),
        ];
        render(<TurnosClient canManage={false} timeZone={AR} initialDate="2026-10-04" />);
        expect(lastParams()).toMatchObject({ date: '2026-10-04' });
        expect(screen.getByText(/domingo, 4 de octubre/i)).toBeInTheDocument();
        const row = within(screen.getByText('Cliente late').closest('[data-testid="appointment-card"]') as HTMLElement);
        expect(row.getByText('23:30')).toBeInTheDocument();
        expect(row.getByText('00:00')).toBeInTheDocument();
        expect(row.getByText('Reserva hasta 23:40')).toBeInTheDocument();
    });

    // 10 (modal) + 12
    it('editar un turno no desplaza fecha/hora por la zona del navegador', async () => {
        setBrowserTZ(MADRID);
        const late = appt('late', SUNDAY_LATE_AR, { payment_summary: summary() });
        appointmentsData = [late];
        slots = [{ start: SUNDAY_LATE_AR, end: '2026-10-05T00:00:00-03:00' }];
        updateSpy.mockResolvedValue(late);

        render(<TurnosClient canManage timeZone={AR} initialDate="2026-10-04" initialView="week" />);
        fireEvent.click(screen.getByTestId('week-appointment'));

        const dialog = within(screen.getByRole('dialog', { name: 'Editar turno' }));
        expect(dialog.getByRole('button', { name: /^Fecha:/ })).toHaveAttribute('data-value', '2026-10-04');
        expect(availabilitySpy.mock.calls.at(-1)?.[0]).toMatchObject({ date: '2026-10-04', excludeAppointmentId: 'late' });
        // Slot y fecha de pago en hora del negocio.
        expect(dialog.getByRole('button', { name: '23:30' })).toBeInTheDocument();
        expect(dialog.getByText('04/10/2026 23:45')).toBeInTheDocument();

        await act(async () => {
            fireEvent.click(dialog.getByRole('button', { name: 'Guardar' }));
        });
        expect(updateSpy).toHaveBeenCalledTimes(1);
        expect(updateSpy.mock.calls[0][0].payload.start_at).toBe(SUNDAY_LATE_AR);
    });
});

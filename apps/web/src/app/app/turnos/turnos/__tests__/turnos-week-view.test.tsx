// Slice 7D: vista semanal del calendario interno de Turnos.
// Zona -03:00 fija para el test (el código no la hardcodea).
process.env.TZ = 'America/Argentina/Buenos_Aires';

import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Appointment, AppointmentListParams, AppointmentPaymentSummary } from '@/features/appointments/types';
import { formatWeekLabel, groupAppointmentsByDay, startOfWeek, weekRange } from '@/features/appointments/week';

let appointmentsData: Appointment[] = [];
const useAppointmentsSpy = vi.fn();

vi.mock('@/features/appointments/hooks', () => ({
    useAppointments: (params: unknown) => {
        useAppointmentsSpy(params);
        return { data: appointmentsData, isLoading: false, isError: false };
    },
    useAppointmentServices: () => ({ data: [] }),
    useAppointmentProfessionals: () => ({ data: [] }),
    useAppointmentAvailability: () => ({ data: undefined, isLoading: false }),
    useCreateAppointment: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useUpdateAppointment: () => ({ mutateAsync: vi.fn(), isPending: false }),
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

function summary(overrides: Partial<AppointmentPaymentSummary> = {}): AppointmentPaymentSummary {
    return {
        status: 'approved',
        amount: '3500.00',
        currency: 'ARS',
        paid_at: '2026-10-01T13:05:00Z',
        requires_review: false,
        review_reason: null,
        ...overrides,
    };
}

/** `start` en hora local -03:00, p.ej. '2026-09-28T10:00'. */
function appt(id: string, start: string, overrides: Partial<Appointment> = {}): Appointment {
    const startAt = new Date(`${start}:00-03:00`);
    return {
        id,
        service: { id: 's1', name: 'Corte', duration_minutes: 30, price: '10000.00', is_active: true, category: null },
        professional: null,
        customer_id: null,
        customer_name: `Cliente ${id}`,
        customer_phone: '1155554444',
        customer_email: '',
        start_at: startAt.toISOString(),
        end_at: new Date(startAt.getTime() + 30 * 60_000).toISOString(),
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

function renderWeek(props: Partial<Parameters<typeof TurnosClient>[0]> = {}) {
    render(<TurnosClient canManage={false} initialDate="2026-10-01" initialView="week" {...props} />);
}

function day(date: string) {
    return within(screen.getByTestId(`week-day-${date}`));
}

beforeEach(() => {
    appointmentsData = [];
    useAppointmentsSpy.mockClear();
    window.history.replaceState({}, '', '/app/turnos/turnos');
});

describe('helpers de semana (lunes → domingo)', () => {
    it('calcula lunes-domingo desde cualquier día', () => {
        expect(weekRange('2026-10-01')).toEqual({
            from: '2026-09-28',
            to: '2026-10-04',
            days: ['2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'],
        });
        expect(startOfWeek('2026-09-28')).toBe('2026-09-28'); // lunes
        expect(startOfWeek('2026-10-04')).toBe('2026-09-28'); // domingo
    });

    it('cruza de año', () => {
        const range = weekRange('2027-01-01');
        expect(range.from).toBe('2026-12-28');
        expect(range.to).toBe('2027-01-03');
        expect(formatWeekLabel(range)).toBe('28 dic – 3 ene');
    });

    it('agrupa por día del Business y ordena por hora', () => {
        const range = weekRange('2026-10-01');
        const groups = groupAppointmentsByDay(
            [appt('b', '2026-09-28T15:00'), appt('late', '2026-10-04T23:30'), appt('a', '2026-09-28T09:00')],
            range.days,
            'America/Argentina/Buenos_Aires',
        );
        expect(groups['2026-09-28'].map((a) => a.id)).toEqual(['a', 'b']);
        // 23:30 -03:00 del domingo es lunes en UTC: igual cae en domingo.
        expect(groups['2026-10-04'].map((a) => a.id)).toEqual(['late']);
        expect(Object.keys(groups)).toHaveLength(7);
    });
});

describe('TurnosClient — Día / Semana', () => {
    // 1
    it('inicia en vista Día', () => {
        render(<TurnosClient canManage={false} initialDate="2026-10-01" />);
        expect(screen.getByRole('button', { name: 'Día' })).toHaveAttribute('aria-pressed', 'true');
        expect(lastParams()).toMatchObject({ date: '2026-10-01' });
        expect(lastParams().date_from).toBeUndefined();
        expect(screen.queryByTestId('week-grid')).not.toBeInTheDocument();
    });

    // 2, 3, 4
    it('cambia a Semana con una sola request lunes-domingo', () => {
        render(<TurnosClient canManage={false} initialDate="2026-10-01" />);
        useAppointmentsSpy.mockClear();
        fireEvent.click(screen.getByRole('button', { name: 'Semana' }));

        expect(screen.getByRole('button', { name: 'Semana' })).toHaveAttribute('aria-pressed', 'true');
        expect(screen.getByTestId('week-label')).toHaveTextContent('28 sep – 4 oct');
        const weekCalls = useAppointmentsSpy.mock.calls.map(([p]) => JSON.stringify(p));
        expect(new Set(weekCalls).size).toBe(1);
        expect(lastParams()).toEqual({ date_from: '2026-09-28', date_to: '2026-10-04', professional: undefined, status: undefined });
        expect(lastParams().date).toBeUndefined();
        expect(window.location.search).toContain('view=week');
        expect(window.location.search).toContain('date=2026-10-01');
    });

    it('respeta initialView="week" (refresh con ?view=week)', () => {
        renderWeek();
        expect(screen.getByRole('button', { name: 'Semana' })).toHaveAttribute('aria-pressed', 'true');
        expect(lastParams()).toMatchObject({ date_from: '2026-09-28', date_to: '2026-10-04' });
    });

    // 5, 6, 7
    it('agrupa por día, ordena por hora y marca días vacíos', () => {
        appointmentsData = [
            appt('mon-late', '2026-09-28T17:00'),
            appt('wed', '2026-09-30T11:00'),
            appt('mon-early', '2026-09-28T09:30'),
        ];
        renderWeek();
        const monday = screen.getByTestId('week-day-2026-09-28');
        const names = within(monday).getAllByTestId('week-appointment').map((el) => el.textContent ?? '');
        expect(names).toHaveLength(2);
        expect(names[0]).toContain('Cliente mon-early');
        expect(names[1]).toContain('Cliente mon-late');
        expect(day('2026-09-30').getByText('Cliente wed')).toBeInTheDocument();
        expect(day('2026-09-29').getByText('Sin turnos')).toBeInTheDocument();
        expect(screen.getAllByText('Sin turnos')).toHaveLength(5);
    });

    // 8
    it('semana anterior', () => {
        renderWeek();
        fireEvent.click(screen.getByRole('button', { name: 'Semana anterior' }));
        expect(screen.getByTestId('week-label')).toHaveTextContent('21 sep – 27 sep');
        expect(lastParams()).toMatchObject({ date_from: '2026-09-21', date_to: '2026-09-27' });
    });

    // 9 (cruza de mes)
    it('semana siguiente', () => {
        renderWeek();
        fireEvent.click(screen.getByRole('button', { name: 'Semana siguiente' }));
        expect(screen.getByTestId('week-label')).toHaveTextContent('5 oct – 11 oct');
        expect(lastParams()).toMatchObject({ date_from: '2026-10-05', date_to: '2026-10-11' });
        expect(window.location.search).toContain('date=2026-10-08');
    });

    // 10
    describe('Hoy', () => {
        beforeEach(() => {
            vi.useFakeTimers({ toFake: ['Date'] });
            vi.setSystemTime(new Date('2026-12-30T23:30:00-03:00')); // miércoles; en UTC ya es 31
        });
        afterEach(() => {
            vi.useRealTimers();
        });

        it('vuelve a la semana actual (local, no UTC)', () => {
            renderWeek();
            fireEvent.click(screen.getByRole('button', { name: 'Hoy' }));
            expect(screen.getByTestId('week-label')).toHaveTextContent('28 dic – 3 ene');
            expect(lastParams()).toMatchObject({ date_from: '2026-12-28', date_to: '2027-01-03' });
        });
    });

    // 11
    it('click en un turno abre el modal existente', () => {
        appointmentsData = [
            appt('paid', '2026-09-29T10:00', { payment_summary: summary() }),
        ];
        renderWeek({ canManage: true });
        fireEvent.click(screen.getByTestId('week-appointment'));
        const dialog = screen.getByRole('dialog', { name: 'Editar turno' });
        expect(within(dialog).getByRole('region', { name: 'Pago' })).toBeInTheDocument();
    });

    it('sin permiso de gestión las tarjetas no son botones', () => {
        appointmentsData = [appt('x', '2026-09-29T10:00')];
        renderWeek({ canManage: false });
        expect(screen.getByTestId('week-appointment').tagName).toBe('DIV');
    });

    // 12–16: misma semántica que 7B.3, sin recálculo en el frontend.
    it('muestra estados operativos y financieros del backend', () => {
        appointmentsData = [
            appt('confirmed', '2026-09-28T10:00'),
            appt('pending', '2026-09-29T10:00', {
                status: 'pending_payment',
                effective_status: 'pending_payment',
                effective_status_display: 'Pendiente de pago',
                expires_at: '2026-09-29T13:20:00Z',
                payment_summary: summary({ status: 'pending', paid_at: null }),
            }),
            appt('expired', '2026-09-30T10:00', {
                status: 'pending_payment',
                effective_status: 'expired',
                effective_status_display: 'Vencido',
                expires_at: '2026-09-20T13:20:00Z',
            }),
            appt('paid', '2026-10-01T10:00', { payment_summary: summary() }),
            appt('review', '2026-10-02T10:00', {
                status: 'expired',
                effective_status: 'expired',
                effective_status_display: 'Vencido',
                payment_summary: summary({ status: 'requires_review', requires_review: true, review_reason: 'approved_after_expiry' }),
            }),
            appt('verifying', '2026-10-03T10:00', {
                status: 'pending_payment',
                effective_status: 'pending_payment',
                effective_status_display: 'Pendiente de pago',
                payment_summary: summary({ status: 'uncertain', paid_at: null }),
            }),
        ];
        renderWeek();

        expect(day('2026-09-28').getByTestId('appointment-status')).toHaveTextContent('Confirmado');
        expect(day('2026-09-28').queryByTestId('appointment-payment')).not.toBeInTheDocument();

        expect(day('2026-09-29').getByTestId('appointment-status')).toHaveTextContent('Pendiente de pago');
        expect(day('2026-09-29').getByTestId('appointment-payment')).toHaveTextContent('Pago pendiente');

        expect(day('2026-09-30').getByTestId('appointment-status')).toHaveTextContent('Vencido');

        expect(day('2026-10-01').getByTestId('appointment-payment')).toHaveTextContent('Pagado');
        expect(day('2026-10-01').getByTestId('appointment-payment')).toHaveAttribute('data-tone', 'paid');

        const review = day('2026-10-02').getByTestId('appointment-payment');
        expect(review).toHaveTextContent('Requiere revisión');
        expect(review).toHaveAttribute('data-tone', 'review');
        expect(day('2026-10-02').getByTestId('week-appointment').className).toContain('border-rose-300');

        expect(day('2026-10-03').getByTestId('appointment-payment')).toHaveTextContent('Pago en verificación');
    });

    // 17
    it('responsive: los 7 días siempre se renderizan (1 columna → 7 desde md)', () => {
        renderWeek();
        const grid = screen.getByTestId('week-grid');
        expect(grid.className).toContain('grid-cols-1');
        expect(grid.className).toContain('md:grid-cols-7');
        const sections = within(grid).getAllByRole('region');
        expect(sections.map((s) => s.getAttribute('aria-label'))).toEqual([
            'Lun 28', 'Mar 29', 'Mié 30', 'Jue 1', 'Vie 2', 'Sáb 3', 'Dom 4',
        ]);
    });

    // 18
    it('volver a Día conserva la fecha ancla', () => {
        renderWeek();
        fireEvent.click(screen.getByRole('button', { name: 'Semana siguiente' }));
        fireEvent.click(screen.getByRole('button', { name: 'Día' }));
        expect(lastParams()).toMatchObject({ date: '2026-10-08' });
        expect(lastParams().date_from).toBeUndefined();
        expect(window.location.search).not.toContain('view=');
        expect(window.location.search).toContain('date=2026-10-08');
    });

    it('los filtros se aplican también a la semana', () => {
        renderWeek();
        fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'expired' } });
        expect(lastParams()).toMatchObject({ date_from: '2026-09-28', date_to: '2026-10-04', status: 'expired' });
    });
});

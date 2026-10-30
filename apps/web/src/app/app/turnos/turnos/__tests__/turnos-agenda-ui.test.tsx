// Slice UI 01: rediseño de las vistas Día y Semana (solo presentación).
// Zona -03:00 fija para el test (el código no la hardcodea).
process.env.TZ = 'America/Argentina/Buenos_Aires';

import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Appointment, AppointmentListParams, AppointmentPaymentSummary } from '@/features/appointments/types';

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
import { DayView } from '../day-view';

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

/** `start` en hora local -03:00, p.ej. '2026-10-02T10:30'. */
function appt(id: string, start: string, overrides: Partial<Appointment> = {}): Appointment {
    const startAt = new Date(`${start}:00-03:00`);
    return {
        id,
        service: { id: 's1', name: 'Coloración', duration_minutes: 90, price: '10000.00', is_active: true, category: null },
        professional: { id: 'p1', name: 'Lucía QA' } as Appointment['professional'],
        customer_id: null,
        customer_name: `Cliente ${id}`,
        customer_phone: '1155554444',
        customer_email: '',
        start_at: startAt.toISOString(),
        end_at: new Date(startAt.getTime() + 90 * 60_000).toISOString(),
        status: 'confirmed',
        status_display: 'Confirmado',
        effective_status: 'confirmed',
        effective_status_display: 'Confirmado',
        expires_at: null,
        payment_summary: null,
        notes: '',
        source: 'manual',
        service_name: 'Coloración completa',
        service_duration_minutes: 90,
        service_price: '10000.00',
        deposit_type: 'fixed',
        deposit_value: '3500.00',
        created_at: '2026-09-20T12:00:00Z',
        updated_at: '2026-09-20T12:00:00Z',
        ...overrides,
    };
}

const PENDING: Partial<Appointment> = {
    status: 'pending_payment',
    effective_status: 'pending_payment',
    effective_status_display: 'Pendiente de pago',
    expires_at: '2026-10-02T06:09:00Z', // 03:09 AR
    payment_summary: summary({ status: 'error', paid_at: null }),
};

function card(name: string) {
    return within(screen.getByText(name).closest('[data-testid="appointment-card"]') as HTMLElement);
}

function lastParams(): AppointmentListParams {
    return useAppointmentsSpy.mock.calls.at(-1)?.[0] as AppointmentListParams;
}

beforeEach(() => {
    appointmentsData = [];
    useAppointmentsSpy.mockClear();
    window.history.replaceState({}, '', '/app/turnos/turnos');
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-02T09:00:00-03:00')); // viernes
});

afterEach(() => {
    vi.useRealTimers();
});

describe('Vista Día (Slice UI 01)', () => {
    it('click en el cuerpo abre el mismo modal Editar turno', () => {
        appointmentsData = [appt('a', '2026-10-02T10:30')];
        render(<TurnosClient canManage />);
        fireEvent.click(screen.getByText('Cliente a'));
        expect(screen.getAllByRole('dialog', { name: 'Editar turno' })).toHaveLength(1);
    });

    it.each(['{Enter}', ' '])('%s en la card abre el modal Editar turno', async (key) => {
        const user = userEvent.setup();
        appointmentsData = [appt('a', '2026-10-02T10:30')];
        render(<TurnosClient canManage />);
        const el = screen.getByRole('button', { name: 'Abrir turno: 10:30 · Cliente a' });
        el.focus();
        expect(el).toHaveFocus();
        await user.keyboard(key);
        expect(screen.getAllByRole('dialog', { name: 'Editar turno' })).toHaveLength(1);
    });

    it('Editar llama una sola vez al handler; teclado y menú no propagan apertura', async () => {
        const user = userEvent.setup();
        const appointment = appt('a', '2026-10-02T10:30');
        const actions = { onEdit: vi.fn(), onStatus: vi.fn(), onCancel: vi.fn() };
        render(<DayView appointments={[appointment]} timeZone="America/Argentina/Buenos_Aires" actions={actions} />);
        const edit = screen.getByRole('button', { name: 'Editar' });
        edit.focus();
        expect(edit).toHaveFocus();
        await user.keyboard('{Enter}');
        expect(actions.onEdit).toHaveBeenCalledExactlyOnceWith(appointment);
        actions.onEdit.mockClear();
        await user.keyboard(' ');
        expect(actions.onEdit).toHaveBeenCalledExactlyOnceWith(appointment);
        actions.onEdit.mockClear();
        fireEvent.click(edit);
        expect(actions.onEdit).toHaveBeenCalledExactlyOnceWith(appointment);
        actions.onEdit.mockClear();
        fireEvent.click(screen.getByRole('button', { name: 'Abrir turno: 10:30 · Cliente a' }));
        expect(actions.onEdit).toHaveBeenCalledExactlyOnceWith(appointment);
        actions.onEdit.mockClear();
        expect(screen.getByTestId('appointment-card').querySelector('button button, button a')).toBeNull();

        const menu = screen.getByRole('button', { name: /Más acciones/ });
        fireEvent.keyDown(menu, { key: ' ' });
        fireEvent.click(menu);
        expect(menu).toHaveAttribute('aria-expanded', 'true');
        expect(actions.onEdit).not.toHaveBeenCalled();
        const completed = screen.getByRole('menuitem', { name: 'Marcar como completado' });
        fireEvent.keyDown(completed, { key: 'Enter' });
        fireEvent.click(completed);
        expect(actions.onStatus).toHaveBeenCalledExactlyOnceWith(appointment, 'completed');
        expect(actions.onEdit).not.toHaveBeenCalled();
    });

    it('abrir el menú no abre el modal de edición', () => {
        appointmentsData = [appt('a', '2026-10-02T10:30')];
        render(<TurnosClient canManage />);
        fireEvent.click(screen.getByRole('button', { name: /Más acciones/ }));
        expect(screen.getByRole('menu')).toBeInTheDocument();
        expect(screen.queryByRole('dialog', { name: 'Editar turno' })).not.toBeInTheDocument();
    });

    it('teléfono no dispara edición y sin permisos la card no es interactiva', () => {
        const appointment = appt('a', '2026-10-02T10:30');
        const actions = { onEdit: vi.fn(), onStatus: vi.fn(), onCancel: vi.fn() };
        const { unmount } = render(<DayView appointments={[appointment]} timeZone="America/Argentina/Buenos_Aires" actions={actions} />);
        fireEvent.click(screen.getByRole('link', { name: /1155554444/ }));
        expect(actions.onEdit).not.toHaveBeenCalled();
        unmount();
        render(<DayView appointments={[appointment]} timeZone="America/Argentina/Buenos_Aires" />);
        const el = screen.getByTestId('appointment-card');
        expect(el).not.toHaveAttribute('tabindex');
        expect(el).not.toHaveAttribute('role', 'button');
        fireEvent.click(el);
        fireEvent.keyDown(el, { key: 'Enter' });
        expect(screen.queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Abrir turno:/ })).not.toBeInTheDocument();
    });

    it('renderiza cada turno como tarjeta con hora, cliente, servicio y profesional', () => {
        appointmentsData = [appt('a', '2026-10-02T10:30'), appt('b', '2026-10-02T13:30', { professional: null })];
        render(<TurnosClient canManage={false} />);

        const cards = screen.getAllByTestId('appointment-card');
        expect(cards).toHaveLength(2);
        expect(screen.queryByRole('table')).not.toBeInTheDocument();

        const first = card('Cliente a');
        expect(first.getByText('10:30')).toBeInTheDocument();
        expect(first.getByText('12:00')).toBeInTheDocument();
        expect(first.getByText(/Coloración completa/)).toHaveTextContent('Lucía QA');
        expect(first.getByRole('link', { name: /1155554444/ })).toHaveAttribute('href', 'tel:1155554444');
        expect(card('Cliente b').getByText('Sin asignar')).toBeInTheDocument();
        expect(screen.getByText('2 turnos')).toBeInTheDocument();
    });

    it('marca "Hoy" y navega día anterior / siguiente', () => {
        render(<TurnosClient canManage={false} />);
        expect(screen.getByTestId('day-label')).toHaveTextContent(/viernes, 2 de octubre/i);
        expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Hoy');

        fireEvent.click(screen.getByRole('button', { name: 'Día siguiente' }));
        expect(lastParams()).toMatchObject({ date: '2026-10-03' });
        expect(screen.getByRole('heading', { level: 2 })).not.toHaveTextContent('Hoy');

        fireEvent.click(screen.getByRole('button', { name: 'Día anterior' }));
        fireEvent.click(screen.getByRole('button', { name: 'Día anterior' }));
        expect(lastParams()).toMatchObject({ date: '2026-10-01' });

        fireEvent.click(screen.getByRole('button', { name: 'Hoy' }));
        expect(lastParams()).toMatchObject({ date: '2026-10-02' });
    });

    it('separa estado del turno y estado del pago', () => {
        appointmentsData = [appt('p', '2026-10-02T10:30', PENDING)];
        render(<TurnosClient canManage={false} />);
        const c = card('Cliente p');
        expect(c.getByTestId('appointment-status')).toHaveTextContent('Pendiente de pago');
        expect(c.getByTestId('appointment-payment')).toHaveTextContent('Error al iniciar el pago');
        expect(c.getByTestId('appointment-status')).not.toHaveTextContent('Error');
        expect(c.getByText('Reserva hasta 03:09')).toBeInTheDocument();
    });

    it('requires_review: borde de alerta, badge de revisión y motivo', () => {
        appointmentsData = [
            appt('r', '2026-10-02T10:30', {
                payment_summary: summary({ status: 'requires_review', requires_review: true, review_reason: 'slot_conflict' }),
            }),
        ];
        render(<TurnosClient canManage={false} />);
        const el = screen.getByTestId('appointment-card');
        expect(el.className).toContain('border-rose-300');
        const c = card('Cliente r');
        expect(c.getByTestId('appointment-status')).toHaveTextContent('Confirmado');
        expect(c.getByTestId('appointment-payment')).toHaveAttribute('data-tone', 'review');
        expect(c.getByText(/el horario ya estaba ocupado/)).toBeInTheDocument();
    });

    it('confirmed: "Editar" visible y cambios de estado en el menú ⋯', () => {
        appointmentsData = [appt('c', '2026-10-02T10:30')];
        render(<TurnosClient canManage />);
        const c = card('Cliente c');
        expect(c.getByRole('button', { name: 'Editar' })).toBeInTheDocument();
        expect(c.queryByRole('menuitem')).not.toBeInTheDocument();

        const trigger = c.getByRole('button', { name: /Más acciones para el turno de Cliente c a las 10:30/ });
        expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
        fireEvent.click(trigger);
        expect(trigger).toHaveAttribute('aria-expanded', 'true');
        expect(c.getAllByRole('menuitem').map((el) => el.textContent)).toEqual([
            'Marcar como completado',
            'Marcar como no asistió',
            'Cancelar turno',
        ]);
        expect(c.getByRole('menuitem', { name: 'Marcar como completado' })).toHaveFocus();

        fireEvent.click(c.getByRole('menuitem', { name: 'Marcar como no asistió' }));
        expect(screen.getByRole('dialog', { name: 'Marcar como no asistió' })).toBeInTheDocument();
        expect(c.queryByRole('menu')).not.toBeInTheDocument();
    });

    it('el menú se cierra con Escape y devuelve el foco', () => {
        appointmentsData = [appt('c', '2026-10-02T10:30')];
        render(<TurnosClient canManage />);
        const trigger = screen.getByRole('button', { name: /Más acciones/ });
        fireEvent.click(trigger);
        fireEvent.keyDown(screen.getByRole('menu'), { key: 'ArrowDown' });
        expect(screen.getByRole('menuitem', { name: 'Marcar como no asistió' })).toHaveFocus();
        fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' });
        expect(screen.queryByRole('menu')).not.toBeInTheDocument();
        expect(trigger).toHaveFocus();
    });

    it('cancelar desde el menú abre la confirmación existente', () => {
        appointmentsData = [appt('c', '2026-10-02T10:30')];
        render(<TurnosClient canManage />);
        fireEvent.click(screen.getByRole('button', { name: /Más acciones/ }));
        fireEvent.click(screen.getByRole('menuitem', { name: 'Cancelar turno' }));
        expect(screen.getByRole('dialog', { name: 'Cancelar turno' })).toBeInTheDocument();
    });

    it.each(['pending_payment', 'completed', 'cancelled', 'no_show', 'expired'] as const)(
        '%s: solo "Editar", sin menú de cambios de estado',
        (status) => {
            appointmentsData = [appt('x', '2026-10-02T10:30', { status, effective_status: status, effective_status_display: status })];
            render(<TurnosClient canManage />);
            const c = card('Cliente x');
            expect(c.getByRole('button', { name: 'Editar' })).toBeInTheDocument();
            expect(c.queryByRole('button', { name: /Más acciones/ })).not.toBeInTheDocument();
        },
    );

    it('sin permiso de gestión no hay acciones ni "Nuevo turno"', () => {
        appointmentsData = [appt('c', '2026-10-02T10:30')];
        render(<TurnosClient canManage={false} />);
        const c = card('Cliente c');
        expect(c.queryByRole('button')).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Nuevo turno/ })).not.toBeInTheDocument();
    });

    it('empty state del día', () => {
        render(<TurnosClient canManage />);
        expect(screen.getByText('No hay turnos para este día.')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Crear turno' })).toBeInTheDocument();
    });
});

describe('Vista Semana (Slice UI 01)', () => {
    function renderWeek(canManage = false) {
        render(<TurnosClient canManage={canManage} initialView="week" />);
    }

    it('cabecera de cada día: nombre corto, número, Hoy y cantidad', () => {
        appointmentsData = [appt('a', '2026-10-02T10:30', PENDING), appt('b', '2026-10-02T13:30'), appt('c', '2026-09-28T09:00')];
        renderWeek();

        const friday = screen.getByTestId('week-day-2026-10-02');
        expect(friday).toHaveAttribute('aria-current', 'date');
        const header = within(friday).getByRole('heading');
        expect(header).toHaveTextContent('Vie');
        expect(header).toHaveTextContent('2');
        expect(header).toHaveTextContent('Hoy');
        expect(header).toHaveTextContent('2 turnos');

        const monday = screen.getByTestId('week-day-2026-09-28');
        expect(monday).not.toHaveAttribute('aria-current');
        expect(within(monday).getByRole('heading')).toHaveTextContent('1 turno');
        expect(within(monday).getByRole('heading')).not.toHaveTextContent('Hoy');

        expect(screen.getByTestId('week-label')).toHaveTextContent('28 sep – 4 oct');
        expect(screen.getByText('Esta semana')).toBeInTheDocument();
        expect(screen.getByText('3 turnos')).toBeInTheDocument();
    });

    it('tarjetas compactas con estado del turno y del pago separados', () => {
        appointmentsData = [appt('a', '2026-10-02T10:30', PENDING), appt('b', '2026-10-02T13:30')];
        renderWeek();
        const cards = within(screen.getByTestId('week-day-2026-10-02')).getAllByTestId('week-appointment');
        expect(cards).toHaveLength(2);
        const [first, second] = cards.map((el) => within(el));
        expect(first.getByText('10:30')).toBeInTheDocument();
        expect(first.getByTestId('appointment-status')).toHaveTextContent('Pendiente de pago');
        expect(first.getByTestId('appointment-payment')).toHaveTextContent('Error al iniciar el pago');
        expect(second.getByTestId('appointment-status')).toHaveTextContent('Confirmado');
        expect(second.queryByTestId('appointment-payment')).not.toBeInTheDocument();
    });

    it('semana sin turnos: estado general + días vacíos discretos', () => {
        renderWeek(true);
        expect(screen.getByText('No hay turnos esta semana.')).toBeInTheDocument();
        expect(screen.getAllByText('Sin turnos')).toHaveLength(7);
        expect(screen.getAllByRole('region')).toHaveLength(7);
    });

    it('con filtros activos, el estado vacío lo aclara', () => {
        renderWeek();
        fireEvent.change(screen.getByLabelText(/^Estado/), { target: { value: 'cancelled' } });
        expect(screen.getByText('Con los filtros seleccionados.')).toBeInTheDocument();
    });

    it('fuera de la semana actual no se marca "Hoy"', () => {
        renderWeek();
        fireEvent.click(screen.getByRole('button', { name: 'Semana siguiente' }));
        expect(screen.queryByText('Esta semana')).not.toBeInTheDocument();
        expect(document.querySelector('[aria-current="date"]')).toBeNull();
    });
});

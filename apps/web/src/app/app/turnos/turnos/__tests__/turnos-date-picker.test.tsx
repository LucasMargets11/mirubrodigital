// Slice UI 02: el "Ir a fecha" del panel usa el calendario propio y
// reutiliza la misma lógica de Día / Semana (changeDate + weekRange).
process.env.TZ = 'Europe/Madrid';

import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AppointmentListParams } from '@/features/appointments/types';

const useAppointmentsSpy = vi.fn();
const availabilitySpy = vi.fn();

vi.mock('@/features/appointments/hooks', () => ({
    useAppointments: (params: unknown) => {
        useAppointmentsSpy(params);
        return { data: [], isLoading: false, isError: false };
    },
    useAppointmentServices: () => ({ data: [] }),
    useAppointmentProfessionals: () => ({ data: [] }),
    useAppointmentAvailability: (params: unknown) => {
        availabilitySpy(params);
        return { data: undefined, isLoading: false };
    },
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

const AR = 'America/Argentina/Buenos_Aires';

function lastParams(): AppointmentListParams {
    return useAppointmentsSpy.mock.calls.at(-1)?.[0] as AppointmentListParams;
}

function openGoToDate() {
    fireEvent.click(screen.getByRole('button', { name: /^Ir a fecha:/ }));
    return within(screen.getByRole('dialog', { name: 'Elegí una fecha' }));
}

function pick(date: string) {
    fireEvent.click(document.querySelector(`[role="dialog"] [data-date="${date}"]`) as HTMLButtonElement);
}

beforeEach(() => {
    useAppointmentsSpy.mockClear();
    availabilitySpy.mockClear();
    window.history.replaceState({}, '', '/app/turnos/turnos');
});

describe('TurnosClient — calendario "Ir a fecha"', () => {
    it('no quedan inputs de fecha nativos en la agenda ni en el formulario', () => {
        render(<TurnosClient canManage timeZone={AR} initialDate="2026-10-02" />);
        fireEvent.click(screen.getByRole('button', { name: /Nuevo turno/ }));
        expect(document.querySelector('input[type="date"]')).toBeNull();
    });

    it('Día: elegir fecha carga ese día, cierra y sincroniza la URL', () => {
        render(<TurnosClient canManage={false} timeZone={AR} initialDate="2026-10-02" />);
        const calendar = openGoToDate();
        expect(calendar.getByRole('heading', { name: 'Octubre 2026' })).toBeInTheDocument();
        pick('2026-10-15');

        expect(lastParams()).toMatchObject({ date: '2026-10-15' });
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(screen.getByTestId('day-label')).toHaveTextContent('jueves, 15 de octubre');
        expect(window.location.search).toContain('date=2026-10-15');
        expect(window.location.search).not.toContain('view=');
    });

    it('Semana: elegir fecha navega a la semana que la contiene (misma request lunes-domingo)', () => {
        render(<TurnosClient canManage={false} timeZone={AR} initialDate="2026-10-02" initialView="week" />);
        expect(screen.getByRole('button', { name: /^Ir a fecha:/ })).toHaveTextContent('28 sep – 4 oct');
        const calendar = openGoToDate();
        // La semana visible queda resaltada; la selección sigue siendo el ancla.
        expect(calendar.getAllByRole('gridcell').filter((c) => c.getAttribute('aria-selected') === 'true')).toHaveLength(1);
        pick('2026-10-15');

        expect(lastParams()).toEqual({ date_from: '2026-10-12', date_to: '2026-10-18', professional: undefined, status: undefined });
        expect(screen.getByTestId('week-label')).toHaveTextContent('12 oct – 18 oct');
        expect(screen.getByRole('button', { name: /^Ir a fecha:/ })).toHaveTextContent('12 oct – 18 oct');
        expect(window.location.search).toContain('view=week');
        expect(window.location.search).toContain('date=2026-10-15');
    });

    it('formulario: elegir fecha reconsulta disponibilidad para ese día', () => {
        render(<TurnosClient canManage timeZone={AR} initialDate="2026-10-02" />);
        fireEvent.click(screen.getByRole('button', { name: /Nuevo turno/ }));
        const form = within(screen.getByRole('dialog', { name: 'Nuevo turno' }));
        fireEvent.click(form.getByRole('button', { name: /^Fecha:/ }));
        pick('2026-10-09');
        expect(form.getByRole('button', { name: /^Fecha:/ })).toHaveAttribute('data-value', '2026-10-09');
        expect(availabilitySpy.mock.calls.at(-1)?.[0]).toMatchObject({ date: '2026-10-09' });
    });
});

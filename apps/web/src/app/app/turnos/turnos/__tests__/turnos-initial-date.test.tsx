// Slice 7C: el panel abre en la fecha LOCAL, no en la fecha UTC.
// 7D.1: "local" = zona del Business; sin `timeZone` usa el default del
// proyecto (Buenos Aires), que acá coincide con la zona del navegador.
// Zona con offset -03:00 fija para el test (el código no la hardcodea).
process.env.TZ = 'America/Argentina/Buenos_Aires';

import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const useAppointmentsSpy = vi.fn();

vi.mock('@/features/appointments/hooks', () => ({
    useAppointments: (params: unknown) => {
        useAppointmentsSpy(params);
        return { data: [], isLoading: false, isError: false };
    },
    useAppointmentServices: () => ({ data: [] }),
    useAppointmentProfessionals: () => ({ data: [] }),
    useAppointmentAvailability: () => ({ data: undefined, isLoading: false }),
    useCreateAppointment: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useUpdateAppointment: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useCancelAppointment: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import { TurnosClient } from '../turnos-client';

function initialDateAt(instant: string): string {
    vi.setSystemTime(new Date(instant));
    useAppointmentsSpy.mockClear();
    render(<TurnosClient canManage={false} />);
    return (useAppointmentsSpy.mock.calls[0][0] as { date: string }).date;
}

describe('TurnosClient — fecha inicial', () => {
    beforeEach(() => {
        vi.useFakeTimers({ toFake: ['Date'] });
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('usa una zona -03:00 en este test', () => {
        expect(new Date('2026-09-29T23:30:00-03:00').getTimezoneOffset()).toBe(180);
    });

    it('de noche (-03:00) no salta al día siguiente por UTC', () => {
        // 23:30 en -03:00 = 02:30Z del 30: toISOString() daría 2026-09-30.
        expect(initialDateAt('2026-09-29T23:30:00-03:00')).toBe('2026-09-29');
        expect(initialDateAt('2026-09-29T21:00:00-03:00')).toBe('2026-09-29');
    });

    it('un cambio real de día sí cambia la fecha', () => {
        expect(initialDateAt('2026-09-30T00:05:00-03:00')).toBe('2026-09-30');
    });

    it('respeta initialDate explícita', () => {
        vi.setSystemTime(new Date('2026-09-29T23:30:00-03:00'));
        useAppointmentsSpy.mockClear();
        render(<TurnosClient canManage={false} initialDate="2026-10-05" />);
        expect((useAppointmentsSpy.mock.calls[0][0] as { date: string }).date).toBe('2026-10-05');
    });
});

import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Appointment, AppointmentPaymentSummary } from '@/features/appointments/types';

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

// Valores distintivos que el backend NUNCA manda; si aparecieran en la UI
// sería porque algún componente los inventa o los filtra de otro lado.
const PROVIDER_LEAKS = ['APPOINTMENT_PAYMENT-', 'PREF-', 'mercadopago', 'approved_after_expiry', 'slot_conflict'];

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

function appt(overrides: Partial<Appointment> = {}): Appointment {
    return {
        id: 'a1',
        service: { id: 's1', name: 'Corte', duration_minutes: 30, price: '10000.00', is_active: true, category: null },
        professional: null,
        customer_id: null,
        customer_name: 'Juana Pérez',
        customer_phone: '1155554444',
        customer_email: '',
        start_at: '2026-10-05T13:00:00Z',
        end_at: '2026-10-05T13:30:00Z',
        status: 'confirmed',
        status_display: 'Confirmado',
        effective_status: 'confirmed',
        effective_status_display: 'Confirmado',
        expires_at: null,
        payment_summary: null,
        notes: '',
        source: 'public',
        service_name: 'Corte',
        service_duration_minutes: 30,
        service_price: '10000.00',
        deposit_type: 'fixed',
        deposit_value: '3500.00',
        created_at: '2026-10-01T12:00:00Z',
        updated_at: '2026-10-01T12:00:00Z',
        ...overrides,
    };
}

function renderRow(appointment: Appointment, canManage = false) {
    appointmentsData = [appointment];
    render(<TurnosClient canManage={canManage} initialDate="2026-10-05" />);
    const row = screen.getByText(appointment.customer_name).closest('[data-testid="appointment-card"]') as HTMLElement;
    return within(row);
}

beforeEach(() => {
    appointmentsData = [];
    useAppointmentsSpy.mockClear();
});

describe('Turnos · estado operativo y financiero (Slice 7B.3)', () => {
    it('confirmado sin seña: solo "Confirmado", sin badge financiero', () => {
        const row = renderRow(appt());
        expect(row.getByTestId('appointment-status')).toHaveTextContent('Confirmado');
        expect(row.queryByTestId('appointment-payment')).not.toBeInTheDocument();
    });

    it('pending_payment: "Pendiente de pago" + "Pago pendiente" + vencimiento del hold', () => {
        const row = renderRow(
            appt({
                status: 'pending_payment',
                status_display: 'Pendiente de pago',
                effective_status: 'pending_payment',
                effective_status_display: 'Pendiente de pago',
                expires_at: '2026-10-01T12:15:00Z',
                payment_summary: summary({ status: 'pending', paid_at: null }),
            }),
        );
        expect(row.getByTestId('appointment-status')).toHaveTextContent('Pendiente de pago');
        expect(row.getByTestId('appointment-payment')).toHaveTextContent('Pago pendiente');
        expect(row.getByText(/Reserva hasta/)).toBeInTheDocument();
    });

    it('hold vencido: usa effective_status "Vencido" aunque status siga pending_payment', () => {
        const row = renderRow(
            appt({
                status: 'pending_payment',
                status_display: 'Pendiente de pago',
                effective_status: 'expired',
                effective_status_display: 'Vencido',
                expires_at: '2026-10-01T12:15:00Z',
            }),
        );
        expect(row.getByTestId('appointment-status')).toHaveTextContent('Vencido');
        expect(row.queryByText('Pendiente de pago')).not.toBeInTheDocument();
        expect(row.queryByText(/Reserva hasta/)).not.toBeInTheDocument();
    });

    it('approved: "Confirmado" + badge "Pagado" con el importe de la seña', () => {
        const row = renderRow(appt({ payment_summary: summary() }));
        expect(row.getByTestId('appointment-status')).toHaveTextContent('Confirmado');
        const badge = row.getByTestId('appointment-payment');
        expect(badge).toHaveTextContent('Pagado');
        expect(badge.textContent).toMatch(/3\.500/);
    });

    it('requires_review: badge persistente con copy humano del motivo', () => {
        const row = renderRow(
            appt({
                status: 'expired',
                status_display: 'Vencido',
                effective_status: 'expired',
                effective_status_display: 'Vencido',
                payment_summary: summary({
                    status: 'requires_review',
                    requires_review: true,
                    review_reason: 'approved_after_expiry',
                }),
            }),
        );
        const badge = row.getByTestId('appointment-payment');
        expect(badge).toHaveTextContent('Pago recibido · Requiere revisión');
        expect(badge).toHaveAttribute('data-tone', 'review');
        expect(row.getByText(/se acreditó después de que venció la reserva/)).toBeInTheDocument();
        expect(row.queryByText('approved_after_expiry')).not.toBeInTheDocument();
    });

    it('requires_review con motivo desconocido cae a un copy genérico', () => {
        const row = renderRow(
            appt({
                payment_summary: summary({
                    status: 'requires_review',
                    requires_review: true,
                    review_reason: 'algo_nuevo' as never,
                }),
            }),
        );
        expect(row.getByText('El pago se acreditó pero requiere revisión manual.')).toBeInTheDocument();
        expect(row.queryByText(/algo_nuevo/)).not.toBeInTheDocument();
    });

    it('uncertain: "Pago en verificación", nunca "Pagado"', () => {
        const row = renderRow(
            appt({
                status: 'pending_payment',
                effective_status: 'pending_payment',
                effective_status_display: 'Pendiente de pago',
                expires_at: '2026-10-01T12:15:00Z',
                payment_summary: summary({ status: 'uncertain', paid_at: null }),
            }),
        );
        expect(row.getByTestId('appointment-payment')).toHaveTextContent('Pago en verificación');
        expect(row.queryByText(/Pagado/)).not.toBeInTheDocument();
    });

    it.each([
        ['rejected', 'Pago rechazado'],
        ['cancelled', 'Pago cancelado'],
        ['error', 'Error al iniciar el pago'],
    ] as const)('%s: muestra "%s" y nunca "Pagado"', (status, label) => {
        const row = renderRow(
            appt({
                status: 'expired',
                effective_status: 'expired',
                effective_status_display: 'Vencido',
                payment_summary: summary({ status, paid_at: null }),
            }),
        );
        expect(row.getByTestId('appointment-payment')).toHaveTextContent(label);
        expect(row.queryByText(/Pagado/)).not.toBeInTheDocument();
    });

    it('la señal de revisión sale del turno: no depende de ninguna notificación', () => {
        // El panel no consume BusinessNotification: el mismo payload del turno
        // (notificación ya leída o no) siempre muestra el badge.
        const reviewed = appt({
            payment_summary: summary({ status: 'requires_review', requires_review: true, review_reason: 'slot_conflict' }),
        });
        const first = renderRow(reviewed);
        expect(first.getByTestId('appointment-payment')).toHaveTextContent('Requiere revisión');
    });

    it('el detalle muestra la sección Pago con estado, seña, fecha y aviso', () => {
        renderRow(
            appt({
                payment_summary: summary({ status: 'requires_review', requires_review: true, review_reason: 'slot_conflict' }),
            }),
            true,
        );
        fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
        const section = within(screen.getByRole('region', { name: 'Pago' }));
        expect(section.getByText('Pago recibido · Requiere revisión')).toBeInTheDocument();
        expect(section.getByText(/3\.500/)).toBeInTheDocument();
        expect(section.getByText('Fecha de pago')).toBeInTheDocument();
        expect(section.getByRole('note')).toHaveTextContent('el horario ya estaba ocupado');
    });

    it('ningún provider id ni código técnico aparece en la UI', () => {
        appointmentsData = [
            appt({ id: 'a1', payment_summary: summary() }),
            appt({
                id: 'a2',
                customer_name: 'Pedro',
                payment_summary: summary({ status: 'requires_review', requires_review: true, review_reason: 'slot_conflict' }),
            }),
        ];
        const { container } = render(<TurnosClient canManage initialDate="2026-10-05" />);
        for (const leak of PROVIDER_LEAKS) {
            expect(container.textContent).not.toContain(leak);
        }
    });

    it('el filtro de estado ofrece Pendiente de pago y Vencido y lo manda al backend', () => {
        render(<TurnosClient canManage={false} initialDate="2026-10-05" />);
        const select = screen.getByLabelText(/^Estado/);
        expect(within(select).getByRole('option', { name: 'Pendiente de pago' })).toBeInTheDocument();
        fireEvent.change(select, { target: { value: 'expired' } });
        expect(useAppointmentsSpy).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'expired' }));
    });
});

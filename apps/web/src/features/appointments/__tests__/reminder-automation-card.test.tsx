import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// CUSTOMER 07B: "Recordatorios automáticos" en Turnos → Configuración.
// Apagados por defecto; solo owner/admin (`manage_reminder_automations`)
// editan; el manager los ve en solo lectura. Nunca se envía nada al cliente.

const hooks = vi.hoisted(() => ({
    useReminderAutomationSettings: vi.fn(),
    useUpdateReminderAutomationSettings: vi.fn(),
}));
vi.mock('../hooks', () => hooks);

import { ApiError } from '@/lib/api/client';

import { ReminderAutomationCard, validateHours } from '../reminder-automation-card';

const DEFAULTS = {
    appointment_reminder_enabled: false,
    appointment_reminder_hours_before: 24,
    no_show_followup_enabled: false,
    no_show_followup_delay_hours: 24,
};

const mutateAsync = vi.fn();

beforeEach(() => {
    vi.clearAllMocks();
    hooks.useReminderAutomationSettings.mockReturnValue({ data: DEFAULTS, isLoading: false, isError: false });
    mutateAsync.mockImplementation(async (payload) => ({ ...DEFAULTS, ...payload }));
    hooks.useUpdateReminderAutomationSettings.mockReturnValue({ mutateAsync, isPending: false });
});

const beforeToggle = () => screen.getByRole('checkbox', { name: /antes de cada turno confirmado/ });
const noShowToggle = () => screen.getByRole('checkbox', { name: /seguimiento después de un no-show/ });
const hoursInput = () => screen.getByLabelText('Anticipación');
const delayInput = () => screen.getByLabelText('Después de');
const saveButton = () => screen.getByRole('button', { name: 'Guardar cambios' });

describe('ReminderAutomationCard', () => {
    it('muestra ambas reglas, apagadas por defecto, y aclara que son internas', () => {
        render(<ReminderAutomationCard canManage />);
        expect(screen.getByRole('heading', { name: 'Recordatorios automáticos' })).toBeInTheDocument();
        expect(screen.getByText(/Estos recordatorios son internos\. MiRubro no enviará mensajes al cliente/)).toBeInTheDocument();
        expect(beforeToggle()).not.toBeChecked();
        expect(noShowToggle()).not.toBeChecked();
        expect(hoursInput()).toHaveValue(24);
        expect(delayInput()).toHaveValue(24);
        expect(saveButton()).toBeDisabled();
    });

    it('activar una regla y cambiar horas → PATCH con números', async () => {
        render(<ReminderAutomationCard canManage />);
        fireEvent.click(beforeToggle());
        fireEvent.change(hoursInput(), { target: { value: '48' } });
        fireEvent.click(noShowToggle());
        fireEvent.change(delayInput(), { target: { value: '72' } });
        fireEvent.click(saveButton());
        await waitFor(() =>
            expect(mutateAsync).toHaveBeenCalledWith({
                appointment_reminder_enabled: true,
                appointment_reminder_hours_before: 48,
                no_show_followup_enabled: true,
                no_show_followup_delay_hours: 72,
            }),
        );
    });

    it('valida límites antes de enviar', () => {
        render(<ReminderAutomationCard canManage />);
        for (const value of ['0', '169', '-3', '2.5', '']) {
            fireEvent.change(hoursInput(), { target: { value } });
            expect(saveButton()).toBeDisabled();
            expect(screen.getByRole('alert')).toBeInTheDocument();
        }
        fireEvent.change(hoursInput(), { target: { value: '168' } });
        fireEvent.change(delayInput(), { target: { value: '721' } });
        expect(screen.getByRole('alert')).toHaveTextContent('Debe estar entre 1 y 720 horas.');
        expect(saveButton()).toBeDisabled();
        fireEvent.change(delayInput(), { target: { value: '720' } });
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        expect(saveButton()).toBeEnabled();
        expect(mutateAsync).not.toHaveBeenCalled();
    });

    it('validateHours usa los mismos rangos que el backend', () => {
        expect(validateHours('appointment_reminder_hours_before', '1')).toBeNull();
        expect(validateHours('appointment_reminder_hours_before', '168')).toBeNull();
        expect(validateHours('appointment_reminder_hours_before', '169')).not.toBeNull();
        expect(validateHours('no_show_followup_delay_hours', '720')).toBeNull();
        expect(validateHours('no_show_followup_delay_hours', '0')).not.toBeNull();
    });

    it('muestra el error del backend', async () => {
        mutateAsync.mockRejectedValue(new ApiError('Forbidden', 403, { detail: 'x' }));
        render(<ReminderAutomationCard canManage />);
        fireEvent.click(beforeToggle());
        fireEvent.click(saveButton());
        expect(await screen.findByRole('alert')).toHaveTextContent('Tu rol no puede cambiar esta configuración.');
    });

    it('sin permiso de edición: solo lectura (manager)', () => {
        hooks.useReminderAutomationSettings.mockReturnValue({
            data: { ...DEFAULTS, appointment_reminder_enabled: true, appointment_reminder_hours_before: 12 },
            isLoading: false,
            isError: false,
        });
        render(<ReminderAutomationCard canManage={false} />);
        expect(beforeToggle()).toBeChecked();
        expect(beforeToggle()).toBeDisabled();
        expect(noShowToggle()).toBeDisabled();
        expect(hoursInput()).toHaveValue(12);
        expect(hoursInput()).toBeDisabled();
        expect(delayInput()).toBeDisabled();
        expect(screen.queryByRole('button', { name: 'Guardar cambios' })).not.toBeInTheDocument();
        expect(screen.getByText(/Solo el dueño o un administrador/)).toBeInTheDocument();
    });

    it('mobile: controles con target táctil', () => {
        render(<ReminderAutomationCard canManage />);
        expect(beforeToggle().closest('label')).toHaveClass('min-h-11');
        expect(hoursInput()).toHaveClass('min-h-11');
        expect(saveButton()).toHaveClass('min-h-11');
    });
});

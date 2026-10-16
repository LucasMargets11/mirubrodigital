import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// CUSTOMER 07D.4A: "Comunicaciones automáticas" (emails al cliente al vencer
// un recordatorio automático). Apagadas por defecto; solo owner/admin editan.

const hooks = vi.hoisted(() => ({
    useCommunicationAutomationSettings: vi.fn(),
    useUpdateCommunicationAutomationSettings: vi.fn(),
}));
vi.mock('../hooks', () => hooks);

import { ApiError } from '@/lib/api/client';

import { CommunicationAutomationCard } from '../communication-automation-card';

const mutateAsync = vi.fn();

function withServer(overrides: Record<string, unknown> = {}) {
    hooks.useCommunicationAutomationSettings.mockReturnValue({
        data: { appointment_email_enabled: false, no_show_email_enabled: false, email_delivery_mode: 'simulation', ...overrides },
        isLoading: false,
        isError: false,
    });
}

beforeEach(() => {
    vi.clearAllMocks();
    withServer();
    mutateAsync.mockImplementation(async (payload) => payload);
    hooks.useUpdateCommunicationAutomationSettings.mockReturnValue({ mutateAsync, isPending: false });
});

const appointmentEmail = () => screen.getByRole('checkbox', { name: 'Enviar email automáticamente' });
const noShowEmail = () => screen.getByRole('checkbox', { name: 'Enviar seguimiento por email' });
const saveButton = () => screen.getByRole('button', { name: 'Guardar cambios' });

describe('CommunicationAutomationCard', () => {
    it('muestra título, copy y todo apagado por defecto', () => {
        render(<CommunicationAutomationCard canManage />);
        expect(screen.getByRole('heading', { name: 'Comunicaciones automáticas' })).toBeInTheDocument();
        expect(
            screen.getByText(/Cuando llegue la hora del recordatorio, MiRubro preparará un email si el cliente tiene Email permitido/),
        ).toBeInTheDocument();
        expect(screen.getByText(/Los canales externos todavía dependen de la configuración del proveedor\./)).toBeInTheDocument();
        expect(appointmentEmail()).not.toBeChecked();
        expect(noShowEmail()).not.toBeChecked();
        expect(saveButton()).toBeDisabled();
    });

    it('muestra "Modo simulación" solo si el backend lo informa', () => {
        const { unmount } = render(<CommunicationAutomationCard canManage />);
        expect(screen.getByText('Modo simulación')).toBeInTheDocument();
        unmount();
        withServer({ email_delivery_mode: 'live' });
        render(<CommunicationAutomationCard canManage />);
        expect(screen.queryByText('Modo simulación')).not.toBeInTheDocument();
        expect(screen.getByText(/Los canales externos todavía dependen/)).toBeInTheDocument();
    });

    it('guarda los switches', async () => {
        render(<CommunicationAutomationCard canManage />);
        fireEvent.click(appointmentEmail());
        expect(saveButton()).toBeEnabled();
        fireEvent.click(saveButton());
        await waitFor(() =>
            expect(mutateAsync).toHaveBeenCalledWith({ appointment_email_enabled: true, no_show_email_enabled: false }),
        );
        expect(await screen.findByRole('status')).toHaveTextContent('Configuración guardada.');
    });

    it('manager: solo lectura, sin botón', () => {
        withServer({ appointment_email_enabled: true });
        render(<CommunicationAutomationCard canManage={false} />);
        expect(appointmentEmail()).toBeChecked();
        expect(appointmentEmail()).toBeDisabled();
        expect(noShowEmail()).toBeDisabled();
        expect(screen.getByText('Solo el dueño o un administrador pueden cambiar esta configuración.')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Guardar cambios' })).not.toBeInTheDocument();
    });

    it('403 → mensaje de rol', async () => {
        mutateAsync.mockRejectedValue(new ApiError('forbidden', 403, {}));
        render(<CommunicationAutomationCard canManage />);
        fireEvent.click(noShowEmail());
        fireEvent.click(saveButton());
        expect(await screen.findByRole('alert')).toHaveTextContent('Tu rol no puede cambiar esta configuración.');
    });

    it('error de carga', () => {
        hooks.useCommunicationAutomationSettings.mockReturnValue({ data: undefined, isLoading: false, isError: true });
        render(<CommunicationAutomationCard canManage />);
        expect(screen.getByRole('alert')).toHaveTextContent('No pudimos cargar la configuración.');
    });
});

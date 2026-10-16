import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// CUSTOMER 07D.3A.1: "Email para respuestas" (Reply-To de los emails al
// cliente). Vacío = sin Reply-To. Solo owner/admin editan; manager lo ve.

const hooks = vi.hoisted(() => ({
    useCustomerCommunicationSettings: vi.fn(),
    useUpdateCustomerCommunicationSettings: vi.fn(),
}));
vi.mock('../hooks', () => hooks);

import { ApiError } from '@/lib/api/client';

import { ReplyToEmailCard, validateReplyToEmail } from '../reply-to-email-card';

const mutateAsync = vi.fn();

function withServer(reply_to_email: string) {
    hooks.useCustomerCommunicationSettings.mockReturnValue({ data: { reply_to_email }, isLoading: false, isError: false });
}

beforeEach(() => {
    vi.clearAllMocks();
    withServer('');
    mutateAsync.mockImplementation(async (payload) => payload);
    hooks.useUpdateCustomerCommunicationSettings.mockReturnValue({ mutateAsync, isPending: false });
});

const input = () => screen.getByLabelText('Email');
const saveButton = () => screen.getByRole('button', { name: 'Guardar' });

describe('ReplyToEmailCard', () => {
    it('muestra el título y el copy, vacío por defecto', () => {
        render(<ReplyToEmailCard canManage />);
        expect(screen.getByRole('heading', { name: 'Email para respuestas' })).toBeInTheDocument();
        expect(
            screen.getByText('Cuando un cliente responda a un correo enviado por MiRubro, la respuesta llegará a esta dirección.'),
        ).toBeInTheDocument();
        expect(input()).toHaveValue('');
        expect(saveButton()).toBeDisabled();
    });

    it('valida formato y no guarda un email inválido', () => {
        render(<ReplyToEmailCard canManage />);
        fireEvent.change(input(), { target: { value: 'no-es-email' } });
        expect(screen.getByRole('alert')).toHaveTextContent('Ingresá un email válido');
        expect(saveButton()).toBeDisabled();
        expect(validateReplyToEmail('')).toBeNull();
        expect(validateReplyToEmail('hola@negocio.com')).toBeNull();
        expect(validateReplyToEmail('a b@c.com')).not.toBeNull();
    });

    it('guarda el email recortado', async () => {
        render(<ReplyToEmailCard canManage />);
        fireEvent.change(input(), { target: { value: '  hola@negocio.com ' } });
        fireEvent.click(saveButton());
        await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ reply_to_email: 'hola@negocio.com' }));
        expect(await screen.findByRole('status')).toHaveTextContent('Configuración guardada.');
    });

    it('permite vaciarlo (sin Reply-To)', async () => {
        withServer('hola@negocio.com');
        render(<ReplyToEmailCard canManage />);
        expect(input()).toHaveValue('hola@negocio.com');
        fireEvent.change(input(), { target: { value: '' } });
        fireEvent.click(saveButton());
        await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ reply_to_email: '' }));
    });

    it('manager: solo lectura, sin botón', () => {
        withServer('hola@negocio.com');
        render(<ReplyToEmailCard canManage={false} />);
        expect(input()).toBeDisabled();
        expect(screen.queryByRole('button', { name: 'Guardar' })).not.toBeInTheDocument();
        expect(screen.getByText(/Solo el dueño o un administrador/)).toBeInTheDocument();
    });

    it('403 del backend → mensaje de rol', async () => {
        mutateAsync.mockRejectedValue(new ApiError('Forbidden', 403, {}));
        render(<ReplyToEmailCard canManage />);
        fireEvent.change(input(), { target: { value: 'hola@negocio.com' } });
        fireEvent.click(saveButton());
        expect(await screen.findByText('Tu rol no puede cambiar esta configuración.')).toBeInTheDocument();
    });
});

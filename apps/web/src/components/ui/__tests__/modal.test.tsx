import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Modal } from '../modal';

// CUSTOMER 04C.1: `eyebrow` opcional. Sin prop se mantiene "Formulario" (resto de modales sin cambios).
describe('Modal eyebrow', () => {
    it('muestra "Formulario" por defecto', () => {
        render(<Modal open title="Editar cliente" onClose={vi.fn()}>cuerpo</Modal>);
        expect(within(screen.getByRole('dialog', { name: 'Editar cliente' })).getByText('Formulario')).toBeInTheDocument();
    });

    it('oculta el rótulo con eyebrow={null} y acepta uno propio', () => {
        const { unmount } = render(<Modal open eyebrow={null} title="Nota" onClose={vi.fn()} footer={<span />}>cuerpo</Modal>);
        expect(within(screen.getByRole('dialog', { name: 'Nota' })).queryByText('Formulario')).not.toBeInTheDocument();
        unmount();
        render(<Modal open eyebrow="Clientes" title="Nota" onClose={vi.fn()}>cuerpo</Modal>);
        expect(within(screen.getByRole('dialog', { name: 'Nota' })).getByText('Clientes')).toBeInTheDocument();
    });
});

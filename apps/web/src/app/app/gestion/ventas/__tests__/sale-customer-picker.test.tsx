import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

const mockMutateAsync = vi.fn();
const mockUseCreateCustomer = vi.fn(() => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
}));
const mockUseCustomers = vi.fn((_filters?: unknown, _options?: unknown) => ({
    data: { results: [] },
    isLoading: false,
    isError: false,
}));

vi.mock('@/features/customers/hooks', () => ({
    useCreateCustomer: () => mockUseCreateCustomer(),
    useCustomers: (...args: unknown[]) => (mockUseCustomers as unknown as (...a: unknown[]) => unknown)(...args),
}));

vi.mock('@/lib/api/client', () => ({
    ApiError: class ApiError extends Error {
        status: number;
        payload: unknown;
        constructor(message: string, status: number, payload?: unknown) {
            super(message);
            this.status = status;
            this.payload = payload;
        }
    },
}));

import { SaleCustomerPicker, CONSUMER_FINAL_SELECTION } from '../sale-customer-picker';

function wrapper({ children }: { children: ReactNode }) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('SaleCustomerPicker — Consumidor Final', () => {
    beforeEach(() => {
        mockMutateAsync.mockReset();
        mockUseCreateCustomer.mockClear();
        mockUseCustomers.mockClear();
    });

    afterEach(() => {
        vi.clearAllMocks();
    });

    it('renders the four modes including "Consumidor Final"', () => {
        render(<SaleCustomerPicker value={null} onChange={() => {}} />, { wrapper });
        expect(screen.getByLabelText(/Elegir opción Consumidor Final/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/Elegir opción Solo nombre/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/Elegir opción Nuevo cliente/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/Elegir opción Cliente existente/i)).toBeInTheDocument();
    });

    it('selecting "Consumidor Final" does NOT call useCreateCustomer', async () => {
        const onChange = vi.fn();
        render(<SaleCustomerPicker value={null} onChange={onChange} />, { wrapper });

        fireEvent.click(screen.getByLabelText(/Elegir opción Consumidor Final/i));

        await waitFor(() => {
            expect(onChange).toHaveBeenCalledWith(CONSUMER_FINAL_SELECTION);
        });
        expect(mockMutateAsync).not.toHaveBeenCalled();
        expect(mockUseCreateCustomer).toHaveBeenCalled();
    });

    it('"Solo nombre" with empty input does NOT create a "Consumidor Final" customer', async () => {
        const onChange = vi.fn();
        render(<SaleCustomerPicker value={null} onChange={onChange} />, { wrapper });

        fireEvent.click(screen.getByLabelText(/Elegir opción Solo nombre/i));

        const button = screen.getByRole('button', { name: /Continuar/i });
        fireEvent.click(button);

        expect(mockMutateAsync).not.toHaveBeenCalled();
        expect(onChange).not.toHaveBeenCalled();
        expect(screen.getByText(/al menos 2 caracteres/i)).toBeInTheDocument();
    });

    it('"Solo nombre" with a real name creates a customer and returns it', async () => {
        const created = {
            id: 'new-uuid',
            name: 'Juan Pérez',
            doc_type: 'dni',
            doc_number: '',
            email: '',
            phone: '',
        };
        mockMutateAsync.mockResolvedValue(created);

        const onChange = vi.fn();
        render(<SaleCustomerPicker value={null} onChange={onChange} />, { wrapper });

        fireEvent.click(screen.getByLabelText(/Elegir opción Solo nombre/i));
        const input = screen.getByPlaceholderText(/Juan Pérez/i);
        fireEvent.change(input, { target: { value: 'Juan Pérez' } });
        fireEvent.click(screen.getByRole('button', { name: /Continuar/i }));

        await waitFor(() => {
            expect(mockMutateAsync).toHaveBeenCalledWith(
                expect.objectContaining({ name: 'Juan Pérez' })
            );
        });
        await waitFor(() => {
            expect(onChange).toHaveBeenCalledWith(
                expect.objectContaining({ id: 'new-uuid', name: 'Juan Pérez' })
            );
        });
    });
});
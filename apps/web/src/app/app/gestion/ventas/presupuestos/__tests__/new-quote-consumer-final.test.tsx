import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

const mockCreateQuoteMutate = vi.fn();
const mockCreateCustomerMutate = vi.fn();

vi.mock('@/features/gestion/hooks', () => ({
    useCreateQuote: () => ({
        mutateAsync: mockCreateQuoteMutate,
        isPending: false,
    }),
    useBusinessBillingProfileQuery: () => ({
        data: { is_complete: true, legal_name: 'Test', tax_id: '30-12345678-9', commercial_address: null },
        isLoading: false,
        isError: false,
    }),
    useDocumentSeriesQuery: () => ({
        data: [
            {
                id: 'series-1',
                document_type: 'quote',
                letter: 'X',
                prefix: '',
                point_of_sale: 1,
                next_number: 1,
                is_active: true,
                is_default: true,
            },
        ],
        isLoading: false,
        isError: false,
    }),
}));

vi.mock('@/features/customers/hooks', () => ({
    useCreateCustomer: () => ({
        mutateAsync: mockCreateCustomerMutate,
        isPending: false,
    }),
    useCustomers: () => ({ data: { results: [] }, isLoading: false, isError: false }),
}));

vi.mock('@/components/app/product-search-list', () => ({
    ProductSearchList: ({ onSelect }: { onSelect: (p: unknown) => void }) => (
        <button
            type="button"
            data-testid="add-test-product"
            onClick={() =>
                onSelect({
                    id: 'p1',
                    name: 'Yerba Mate 500g',
                    sku: 'YER500',
                    barcode: null,
                    price: '100',
                    stock_min: '0',
                    stock_quantity: '10',
                    is_active: true,
                    category: null,
                    created_at: '2025-01-01',
                    updated_at: '2025-01-01',
                })
            }
        >
            add
        </button>
    ),
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

const mockRouterPush = vi.fn();
vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: mockRouterPush }),
}));

function wrapper({ children }: { children: ReactNode }) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function renderNewQuote() {
    const { NewQuoteClient } = await import('../nuevo/new-quote-client');
    return render(<NewQuoteClient />, { wrapper });
}

describe('NewQuoteClient — Consumidor Final submission', () => {
    beforeEach(() => {
        mockCreateQuoteMutate.mockReset();
        mockCreateQuoteMutate.mockResolvedValue({ id: 'quote-1' });
        mockCreateCustomerMutate.mockReset();
        mockRouterPush.mockReset();
    });

    afterEach(() => {
        vi.clearAllMocks();
    });

    it('sends customer_id: null and customer_name: "Consumidor Final" without creating a CRM customer', async () => {
        await renderNewQuote();

        fireEvent.click(screen.getByLabelText(/Elegir opción Consumidor Final/i));
        fireEvent.click(screen.getByTestId('add-test-product'));

        const saveBtn = screen.getByRole('button', { name: /Guardar presupuesto/i });
        expect(saveBtn).not.toBeDisabled();
        fireEvent.click(saveBtn);

        await waitFor(() => {
            expect(mockCreateQuoteMutate).toHaveBeenCalledTimes(1);
        });

        const payload = mockCreateQuoteMutate.mock.calls[0][0];
        expect(payload.customer_id).toBeNull();
        expect(payload.customer_name).toBe('Consumidor Final');
        expect(payload.items).toEqual([
            expect.objectContaining({ product_id: 'p1', quantity: 1, unit_price: 100 }),
        ]);

        expect(mockCreateCustomerMutate).not.toHaveBeenCalled();
    });
});

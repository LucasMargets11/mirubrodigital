import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

const mockCreateSaleMutate = vi.fn();
const mockProductSelect = vi.fn();
const mockCreateCustomerMutate = vi.fn();
const mockCustomersQuery = vi.fn((_filters?: unknown, _options?: unknown) => ({ data: { results: [] }, isLoading: false, isError: false }));

let settingsRequireCustomer = true;
let activeSession: { id: string } | null = null;

vi.mock('@/features/gestion/hooks', () => ({
    useCreateSale: () => ({
        mutateAsync: mockCreateSaleMutate,
        isPending: false,
    }),
    useCommercialSettingsQuery: () => ({
        data: {
            require_customer_for_sales: settingsRequireCustomer,
            allow_sell_without_stock: true,
            allow_negative_price_or_discount: false,
            warn_on_low_stock_threshold_enabled: true,
            low_stock_threshold_default: 5,
            enable_sales_notes: true,
            block_sales_if_no_open_cash_session: false,
        },
    }),
}));

vi.mock('@/features/cash/hooks', () => ({
    useCashSummary: () => ({
        data: { session: activeSession },
        isLoading: false,
        isError: false,
    }),
}));

vi.mock('@/features/customers/hooks', () => ({
    useCreateCustomer: () => ({
        mutateAsync: mockCreateCustomerMutate,
        isPending: false,
    }),
    useCustomers: (...args: unknown[]) => (mockCustomersQuery as unknown as (...a: unknown[]) => unknown)(...args),
}));

vi.mock('@/components/app/toast', () => ({
    ToastBubble: () => null,
}));

vi.mock('@/components/app/product-search-list', () => ({
    ProductSearchList: ({ onSelect, disabled }: { onSelect: (p: unknown) => void; disabled?: boolean }) => (
        <div>
            <span data-testid="product-search-disabled">{disabled ? 'disabled' : 'enabled'}</span>
            <button
                type="button"
                data-testid="add-test-product"
                onClick={() => {
                    mockProductSelect();
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
                    });
                }}
            >
                add
            </button>
        </div>
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

async function renderNewSale() {
    const { NewSaleClient } = await import('../new-sale-client');
    return render(<NewSaleClient />, { wrapper });
}

describe('NewSaleClient — Consumidor Final submission', () => {
    beforeEach(() => {
        mockCreateSaleMutate.mockReset();
        mockCreateSaleMutate.mockResolvedValue({ id: 'sale-1' });
        mockProductSelect.mockReset();
        mockRouterPush.mockReset();
        activeSession = null;
        settingsRequireCustomer = false;
    });

    afterEach(() => {
        vi.clearAllMocks();
    });

    it('with requires_customer_for_sales=false: consumer_final sends customer_id: null', async () => {
        await renderNewSale();

        fireEvent.click(screen.getByLabelText(/Elegir opción Consumidor Final/i));
        fireEvent.click(screen.getByTestId('add-test-product'));

        const confirmBtn = screen.getByRole('button', { name: /Confirmar venta/i });
        expect(confirmBtn).not.toBeDisabled();
        fireEvent.click(confirmBtn);

        await waitFor(() => {
            expect(mockCreateSaleMutate).toHaveBeenCalledTimes(1);
        });
        const payload = mockCreateSaleMutate.mock.calls[0][0];
        expect(payload.customer_id).toBeNull();
        expect(payload.items).toEqual([
            expect.objectContaining({ product_id: 'p1', quantity: 1, unit_price: 100 }),
        ]);
    });

    it('with requires_customer_for_sales=true: consumer_final blocks confirm with warning', async () => {
        settingsRequireCustomer = true;
        await renderNewSale();

        fireEvent.click(screen.getByLabelText(/Elegir opción Consumidor Final/i));
        fireEvent.click(screen.getByTestId('add-test-product'));

        expect(
            screen.getByText(/Con cliente obligatorio no se admite Consumidor Final/i)
        ).toBeInTheDocument();

        const confirmBtn = screen.getByRole('button', { name: /Confirmar venta/i });
        expect(confirmBtn).toBeDisabled();

        fireEvent.click(confirmBtn);
        expect(mockCreateSaleMutate).not.toHaveBeenCalled();
    });

    it('Solo nombre with empty input shows validation and does not submit', async () => {
        await renderNewSale();

        fireEvent.click(screen.getByLabelText(/Elegir opción Solo nombre/i));
        fireEvent.click(screen.getByTestId('add-test-product'));
        fireEvent.click(screen.getByRole('button', { name: /Continuar/i }));

        await waitFor(() => {
            expect(screen.getByText(/al menos 2 caracteres/i)).toBeInTheDocument();
        });
        expect(mockCreateSaleMutate).not.toHaveBeenCalled();
    });

    it('Solo nombre with a real name creates the customer and uses its id in the sale payload', async () => {
        mockCreateCustomerMutate.mockReset();
        mockCreateCustomerMutate.mockResolvedValue({
            id: 'new-cust',
            name: 'Juan Pérez',
            doc_type: 'dni',
            doc_number: '',
            email: '',
            phone: '',
        });

        await renderNewSale();

        fireEvent.click(screen.getByLabelText(/Elegir opción Solo nombre/i));
        const input = screen.getByPlaceholderText(/Juan Pérez/i);
        fireEvent.change(input, { target: { value: 'Juan Pérez' } });
        fireEvent.click(screen.getByTestId('add-test-product'));
        fireEvent.click(screen.getByRole('button', { name: /Continuar/i }));

        await waitFor(() => {
            expect(screen.getByText(/Cliente seleccionado \(Solo nombre\)/i)).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole('button', { name: /Confirmar venta/i }));

        await waitFor(() => {
            expect(mockCreateSaleMutate).toHaveBeenCalledTimes(1);
        });
        const payload = mockCreateSaleMutate.mock.calls[0][0];
        expect(payload.customer_id).toBe('new-cust');
    });
});
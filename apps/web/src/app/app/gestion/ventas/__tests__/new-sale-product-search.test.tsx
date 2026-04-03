import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Product } from '@/features/gestion/types';

// ── Mocks ────────────────────────────────────────────────────────────

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/components/app/toast', () => ({
    ToastBubble: () => null,
}));

vi.mock('../sale-customer-picker', () => ({
    SaleCustomerPicker: () => <div data-testid="customer-picker" />,
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

const mockProducts: Product[] = [
    {
        id: 'p1',
        name: 'Yerba Mate 500g',
        sku: 'YER500',
        barcode: '7791234567890',
        price: '850',
        stock_min: '5',
        stock_quantity: '20',
        is_active: true,
        category: null,
        created_at: '2025-01-01',
        updated_at: '2025-01-01',
    },
    {
        id: 'p2',
        name: 'Café Molido 250g',
        sku: 'CAF250',
        barcode: '7799876543210',
        price: '1200',
        stock_min: '3',
        stock_quantity: '8',
        is_active: true,
        category: null,
        created_at: '2025-01-01',
        updated_at: '2025-01-01',
    },
    {
        id: 'p3',
        name: 'Azúcar 1kg',
        sku: 'AZU1K',
        barcode: null,
        price: '600',
        stock_min: '10',
        stock_quantity: '0',
        is_active: true,
        category: null,
        created_at: '2025-01-01',
        updated_at: '2025-01-01',
    },
];

let mockUseProductsReturn: {
    data: Product[] | undefined;
    isLoading: boolean;
    isError: boolean;
};

vi.mock('@/features/gestion/hooks', () => ({
    useProducts: () => mockUseProductsReturn,
    useCommercialSettingsQuery: () => ({
        data: {
            require_customer_for_sales: false,
            allow_sell_without_stock: false,
            allow_negative_price_or_discount: false,
            warn_on_low_stock_threshold_enabled: true,
            low_stock_threshold_default: 5,
            enable_sales_notes: true,
            block_sales_if_no_open_cash_session: false,
        },
    }),
    useCreateSale: () => ({
        mutateAsync: vi.fn(),
        isPending: false,
    }),
}));

vi.mock('@/features/cash/hooks', () => ({
    useCashSummary: () => ({
        data: { session: null },
        isLoading: false,
        isError: false,
    }),
}));

// ── Helpers ──────────────────────────────────────────────────────────

function wrapper({ children }: { children: React.ReactNode }) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function renderComponent() {
    // Dynamic import to ensure mocks are applied
    const { NewSaleClient } = await import('../new-sale-client');
    return render(<NewSaleClient />, { wrapper });
}

function getSearchInput() {
    return screen.getByRole('combobox', { name: /buscar producto/i });
}

// ── Tests ────────────────────────────────────────────────────────────

describe('NewSaleClient — product search UX & accessibility', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        mockUseProductsReturn = { data: undefined, isLoading: false, isError: false };
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('renders a visible label and combobox input', async () => {
        await renderComponent();
        expect(screen.getByText('Buscar producto')).toBeInTheDocument();
        const input = getSearchInput();
        expect(input).toHaveAttribute('role', 'combobox');
        expect(input).toHaveAttribute('aria-autocomplete', 'list');
    });

    it('shows helpful hint when search is empty instead of min-char warning', async () => {
        await renderComponent();
        expect(screen.getByText(/buscá un producto por nombre/i)).toBeInTheDocument();
        expect(screen.queryByText(/al menos 2 caracteres/i)).not.toBeInTheDocument();
    });

    it('does NOT show a redundant "Buscar por nombre o SKU" button', async () => {
        await renderComponent();
        expect(screen.queryByRole('button', { name: /buscar por nombre o sku/i })).not.toBeInTheDocument();
    });

    it('triggers search from 1 character (no min 2 restriction)', async () => {
        mockUseProductsReturn = { data: mockProducts, isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'Y' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByText('Yerba Mate 500g')).toBeInTheDocument();
        });
    });

    it('shows clear button with aria-label when search has text', async () => {
        mockUseProductsReturn = { data: mockProducts, isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'yer' } });
        act(() => { vi.advanceTimersByTime(300); });

        const clearButton = screen.getByRole('button', { name: /limpiar búsqueda/i });
        expect(clearButton).toBeInTheDocument();
    });

    it('clears search when clear button is clicked', async () => {
        mockUseProductsReturn = { data: mockProducts, isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'yer' } });
        act(() => { vi.advanceTimersByTime(300); });

        const clearButton = screen.getByRole('button', { name: /limpiar búsqueda/i });
        fireEvent.click(clearButton);

        expect(input).toHaveValue('');
    });

    it('shows "no results" message with search term', async () => {
        mockUseProductsReturn = { data: [], isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'zzz' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByText(/no encontramos productos para/i)).toBeInTheDocument();
            expect(screen.getByText(/probá con otro nombre/i)).toBeInTheDocument();
        });
    });

    it('renders a listbox with role="listbox" for results', async () => {
        mockUseProductsReturn = { data: mockProducts, isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            const listbox = screen.getByRole('listbox', { name: /resultados de búsqueda/i });
            expect(listbox).toBeInTheDocument();
        });
    });

    it('each product result has role="option"', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            const listbox = screen.getByRole('listbox', { name: /resultados de búsqueda/i });
            const options = within(listbox).getAllByRole('option');
            expect(options.length).toBe(2);
        });
    });

    it('navigates results with ArrowDown and ArrowUp keys', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            const listbox = screen.getByRole('listbox', { name: /resultados de búsqueda/i });
            expect(within(listbox).getAllByRole('option').length).toBe(2);
        });

        const listbox = screen.getByRole('listbox', { name: /resultados de búsqueda/i });

        fireEvent.keyDown(input, { key: 'ArrowDown' });
        const firstOption = within(listbox).getAllByRole('option')[0];
        expect(firstOption).toHaveAttribute('aria-selected', 'true');

        fireEvent.keyDown(input, { key: 'ArrowDown' });
        const secondOption = within(listbox).getAllByRole('option')[1];
        expect(secondOption).toHaveAttribute('aria-selected', 'true');
        expect(firstOption).toHaveAttribute('aria-selected', 'false');

        fireEvent.keyDown(input, { key: 'ArrowUp' });
        expect(firstOption).toHaveAttribute('aria-selected', 'true');
    });

    it('closes listbox with Escape key', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByRole('listbox', { name: /resultados de búsqueda/i })).toBeInTheDocument();
        });

        fireEvent.keyDown(input, { key: 'Escape' });
        expect(screen.queryByRole('listbox', { name: /resultados de búsqueda/i })).not.toBeInTheDocument();
    });

    it('has an aria-live region for screen reader announcements', async () => {
        mockUseProductsReturn = { data: mockProducts, isLoading: false, isError: false };
        await renderComponent();

        const liveRegion = document.querySelector('[aria-live="polite"]');
        expect(liveRegion).toBeInTheDocument();
    });

    it('input has aria-controls pointing to the listbox id', async () => {
        mockUseProductsReturn = { data: mockProducts, isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        expect(input).toHaveAttribute('aria-controls', 'product-search-listbox');
    });

    it('keeps listbox open when clicking outside (no context loss)', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'yer' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByRole('listbox', { name: /resultados de búsqueda/i })).toBeInTheDocument();
        });

        // Click outside — listbox should stay open to preserve search context
        fireEvent.mouseDown(document.body);
        expect(screen.getByRole('listbox', { name: /resultados de búsqueda/i })).toBeInTheDocument();
    });

    it('reopens listbox on focus after Escape closed it', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderComponent();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'yer' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByRole('listbox', { name: /resultados de búsqueda/i })).toBeInTheDocument();
        });

        // Escape closes listbox
        fireEvent.keyDown(input, { key: 'Escape' });
        expect(screen.queryByRole('listbox', { name: /resultados de búsqueda/i })).not.toBeInTheDocument();

        // Re-focus input should reopen listbox when search has text
        fireEvent.focus(input);
        await waitFor(() => {
            expect(screen.getByRole('listbox', { name: /resultados de búsqueda/i })).toBeInTheDocument();
        });
    });
});

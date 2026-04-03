import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Product } from '@/features/gestion/types';

// ── Mocks ────────────────────────────────────────────────────────────

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
}));

vi.mock('@/lib/format', () => ({
    formatCurrencySmart: (v: number) => `$${v}`,
}));

// ── Helpers ──────────────────────────────────────────────────────────

function wrapper({ children }: { children: React.ReactNode }) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

async function renderSelector(props: Record<string, unknown> = {}) {
    const { ProductSearchList } = await import('../product-search-list');
    const onSelect = vi.fn();
    const result = render(
        <ProductSearchList onSelect={onSelect} {...props} />,
        { wrapper },
    );
    return { ...result, onSelect };
}

function getSearchInput() {
    return screen.getByRole('combobox', { name: /buscar producto/i });
}

// ── Tests ────────────────────────────────────────────────────────────

describe('ProductSearchList — shared component', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        mockUseProductsReturn = { data: undefined, isLoading: false, isError: false };
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('renders a combobox input with correct ARIA attributes', async () => {
        await renderSelector();
        const input = getSearchInput();
        expect(input).toHaveAttribute('role', 'combobox');
        expect(input).toHaveAttribute('aria-autocomplete', 'list');
    });

    it('shows placeholder hint when search is empty', async () => {
        await renderSelector();
        expect(screen.getByText(/buscá un producto por nombre/i)).toBeInTheDocument();
    });

    it('shows results after typing and debounce', async () => {
        mockUseProductsReturn = { data: mockProducts, isLoading: false, isError: false };
        await renderSelector();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'yer' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByText('Yerba Mate 500g')).toBeInTheDocument();
        });
    });

    it('renders a listbox with role for results', async () => {
        mockUseProductsReturn = { data: mockProducts, isLoading: false, isError: false };
        await renderSelector();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByRole('listbox', { name: /resultados de búsqueda/i })).toBeInTheDocument();
        });
    });

    it('each result has role="option"', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderSelector();

        fireEvent.change(getSearchInput(), { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            const listbox = screen.getByRole('listbox');
            expect(within(listbox).getAllByRole('option').length).toBe(2);
        });
    });

    it('navigates with ArrowDown and ArrowUp', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderSelector();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(within(screen.getByRole('listbox')).getAllByRole('option').length).toBe(2);
        });

        fireEvent.keyDown(input, { key: 'ArrowDown' });
        const options = within(screen.getByRole('listbox')).getAllByRole('option');
        expect(options[0]).toHaveAttribute('aria-selected', 'true');

        fireEvent.keyDown(input, { key: 'ArrowDown' });
        expect(options[1]).toHaveAttribute('aria-selected', 'true');
        expect(options[0]).toHaveAttribute('aria-selected', 'false');

        fireEvent.keyDown(input, { key: 'ArrowUp' });
        expect(options[0]).toHaveAttribute('aria-selected', 'true');
    });

    it('selects product with Enter and calls onSelect', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        const { onSelect } = await renderSelector();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByRole('listbox')).toBeInTheDocument();
        });

        fireEvent.keyDown(input, { key: 'ArrowDown' });
        fireEvent.keyDown(input, { key: 'Enter' });

        expect(onSelect).toHaveBeenCalledTimes(1);
        expect(onSelect).toHaveBeenCalledWith(mockProducts[0]);
    });

    it('keeps listbox open after selecting (for rapid multi-item entry)', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderSelector();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByRole('listbox')).toBeInTheDocument();
        });

        // Click product
        fireEvent.click(within(screen.getByRole('listbox')).getAllByRole('option')[0]);

        // Listbox should remain visible
        expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    it('closes listbox with Escape', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderSelector();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByRole('listbox')).toBeInTheDocument();
        });

        fireEvent.keyDown(input, { key: 'Escape' });
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });

    it('reopens on focus after Escape', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderSelector();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByRole('listbox')).toBeInTheDocument();
        });

        fireEvent.keyDown(input, { key: 'Escape' });
        fireEvent.focus(input);

        await waitFor(() => {
            expect(screen.getByRole('listbox')).toBeInTheDocument();
        });
    });

    it('shows disabled message when disabled', async () => {
        await renderSelector({
            disabled: true,
            disabledMessage: 'Elegí un cliente primero.',
        });

        expect(screen.getByText('Elegí un cliente primero.')).toBeInTheDocument();
        expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    });

    it('shows "✓ en lista" for products in selectedProductIds', async () => {
        mockUseProductsReturn = { data: mockProducts.slice(0, 2), isLoading: false, isError: false };
        await renderSelector({ selectedProductIds: ['p1'] });

        fireEvent.change(getSearchInput(), { target: { value: 'a' } });
        act(() => { vi.advanceTimersByTime(300); });

        await waitFor(() => {
            expect(screen.getByText('✓ en lista')).toBeInTheDocument();
        });
    });

    it('shows clear button with aria-label', async () => {
        mockUseProductsReturn = { data: mockProducts, isLoading: false, isError: false };
        await renderSelector();

        fireEvent.change(getSearchInput(), { target: { value: 'yer' } });
        act(() => { vi.advanceTimersByTime(300); });

        expect(screen.getByRole('button', { name: /limpiar búsqueda/i })).toBeInTheDocument();
    });

    it('clears search upon clicking clear', async () => {
        mockUseProductsReturn = { data: mockProducts, isLoading: false, isError: false };
        await renderSelector();

        const input = getSearchInput();
        fireEvent.change(input, { target: { value: 'yer' } });
        act(() => { vi.advanceTimersByTime(300); });

        fireEvent.click(screen.getByRole('button', { name: /limpiar búsqueda/i }));
        expect(input).toHaveValue('');
    });

    it('has an aria-live region', async () => {
        await renderSelector();
        expect(document.querySelector('[aria-live="polite"]')).toBeInTheDocument();
    });
});

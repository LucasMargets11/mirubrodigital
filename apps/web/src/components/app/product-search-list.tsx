"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import type { Product } from '@/features/gestion/types';
import { useProducts } from '@/features/gestion/hooks';
import { formatCurrencySmart } from '@/lib/format';

// ── Stock helpers ────────────────────────────────────────────────────

type StockStatus = 'ok' | 'low' | 'out';
type StockFilter = 'all' | 'in' | 'low' | 'out';

const STOCK_FILTER_OPTIONS: { value: StockFilter; label: string }[] = [
    { value: 'all', label: 'Todos' },
    { value: 'in', label: 'Con stock' },
    { value: 'low', label: 'Bajo stock' },
    { value: 'out', label: 'Sin stock' },
];

function toNumber(value: string | number | null | undefined) {
    if (typeof value === 'number') return value;
    if (typeof value === 'string') {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }
    return 0;
}

function getAvailableQuantity(product: Product) {
    return Math.max(0, toNumber(product.stock_quantity));
}

type StockMetaConfig = { warnLowStock: boolean; defaultThreshold: number };

function getStockMeta(
    product: Product,
    config?: StockMetaConfig,
): { quantity: number; status: StockStatus } {
    const quantity = getAvailableQuantity(product);
    if (quantity === 0) return { quantity: 0, status: 'out' };
    const productThreshold = Math.max(0, toNumber(product.stock_min));
    const baseThreshold = Math.max(productThreshold, config?.defaultThreshold ?? 5);
    const effectiveThreshold = config?.warnLowStock === false ? 0 : baseThreshold;
    if (effectiveThreshold > 0 && quantity <= effectiveThreshold) {
        return { quantity, status: 'low' };
    }
    return { quantity, status: 'ok' };
}

function StockBadge({ status }: { status: StockStatus }) {
    const config: Record<StockStatus, { color: string; label: string }> = {
        ok: { color: 'bg-emerald-500', label: 'Stock OK' },
        low: { color: 'bg-amber-400', label: 'Stock bajo' },
        out: { color: 'bg-rose-500', label: 'Sin stock' },
    };
    return (
        <span className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600" aria-live="polite">
            <span className={`h-2.5 w-2.5 rounded-full ${config[status].color}`} aria-hidden />
            {config[status].label}
        </span>
    );
}

// ── Component props ──────────────────────────────────────────────────

export type ProductSearchListProps = {
    /** Called when the user selects a product. */
    onSelect: (product: Product) => void;
    /** Disable the search (e.g. customer required). */
    disabled?: boolean;
    /** Message shown when search is disabled. */
    disabledMessage?: string;
    /** Placeholder for the search input. */
    searchPlaceholder?: string;
    /** Show stock filter buttons. Default: true */
    showStockFilter?: boolean;
    /** Show stock info in each result row. Default: true */
    showStockInfo?: boolean;
    /** Default stock filter. Default: 'in' */
    defaultStockFilter?: StockFilter;
    /** Low stock threshold config. */
    stockMetaConfig?: StockMetaConfig;
    /** IDs of products currently in the cart — used to show "✓ en lista" badge. */
    selectedProductIds?: string[];
    /** Minimum characters to trigger search. Default: 1 */
    minSearchLength?: number;
    /** Label text for the search. */
    searchLabel?: string;
    /** Clear search after selecting? Default: false (keep list open for rapid entry). */
    clearOnSelect?: boolean;
    /** Ref forwarded to the search input for external focus management. */
    inputRef?: React.RefObject<HTMLInputElement | null>;
    /** Unique id prefix for ARIA attributes. */
    idPrefix?: string;
};

// ── Component ────────────────────────────────────────────────────────

export function ProductSearchList({
    onSelect,
    disabled = false,
    disabledMessage,
    searchPlaceholder = 'Nombre, SKU o código de barras',
    showStockFilter = true,
    showStockInfo = true,
    defaultStockFilter = 'in',
    stockMetaConfig,
    selectedProductIds = [],
    minSearchLength = 1,
    searchLabel = 'Buscar producto',
    clearOnSelect = false,
    inputRef: externalInputRef,
    idPrefix = 'product-search',
}: ProductSearchListProps) {
    const internalInputRef = useRef<HTMLInputElement>(null);
    const inputRef = externalInputRef ?? internalInputRef;
    const listboxRef = useRef<HTMLUListElement>(null);

    const [search, setSearch] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [highlightedIndex, setHighlightedIndex] = useState(-1);
    const [listboxOpen, setListboxOpen] = useState(true);
    const [stockFilter, setStockFilter] = useState<StockFilter>(defaultStockFilter);

    // Debounce: 50ms for barcode-like (numeric ≥4 digits), 250ms otherwise
    useEffect(() => {
        const trimmed = search.trim();
        if (!trimmed) {
            setDebouncedSearch('');
            return;
        }
        const looksLikeBarcode = /^\d{4,}$/.test(trimmed);
        const delay = looksLikeBarcode ? 50 : 250;
        const handle = setTimeout(() => setDebouncedSearch(trimmed), delay);
        return () => clearTimeout(handle);
    }, [search]);

    const trimmedSearch = debouncedSearch;
    const shouldSearch = trimmedSearch.length >= minSearchLength;
    const canFetch = !disabled && shouldSearch;

    const productsQuery = useProducts(trimmedSearch, false, undefined, { enabled: canFetch });
    const rawProducts = canFetch ? (productsQuery.data ?? []) : [];

    // Apply stock filter
    const filteredProducts = useMemo(() => {
        if (!showStockFilter) return rawProducts;
        return rawProducts.filter((product) => {
            const meta = getStockMeta(product, stockMetaConfig);
            if (stockFilter === 'all') return true;
            if (stockFilter === 'in') return meta.status !== 'out';
            return meta.status === stockFilter;
        });
    }, [rawProducts, stockFilter, stockMetaConfig, showStockFilter]);

    // Sort by relevance
    const sortedProducts = useMemo(() => {
        if (!trimmedSearch) return filteredProducts;
        const q = trimmedSearch.toLowerCase();
        return [...filteredProducts].sort((a, b) => {
            const score = (p: Product) => {
                const sku = (p.sku || '').toLowerCase();
                const name = p.name.toLowerCase();
                if (sku === q) return 0;
                if (sku.startsWith(q)) return 1;
                if (name.startsWith(q)) return 2;
                return 3;
            };
            return score(a) - score(b);
        });
    }, [filteredProducts, trimmedSearch]);

    const products = sortedProducts.slice(0, 40);

    // Aria-live announcement
    const searchAnnouncement = useMemo(() => {
        if (!shouldSearch) return '';
        if (productsQuery.isLoading) return 'Buscando productos...';
        if (productsQuery.isError) return 'Error al buscar productos.';
        if (products.length === 0) return `Sin resultados para "${search.trim()}".`;
        return `${products.length} producto${products.length === 1 ? '' : 's'} encontrado${products.length === 1 ? '' : 's'}.`;
    }, [shouldSearch, productsQuery.isLoading, productsQuery.isError, products.length, search]);

    // Reset highlighted index when results change
    useEffect(() => {
        setHighlightedIndex(-1);
    }, [products.length, trimmedSearch]);

    // Scroll highlighted into view
    useEffect(() => {
        if (highlightedIndex < 0 || !listboxRef.current) return;
        const items = listboxRef.current.querySelectorAll('[role="option"]');
        const el = items[highlightedIndex];
        if (el && typeof el.scrollIntoView === 'function') {
            el.scrollIntoView({ block: 'nearest' });
        }
    }, [highlightedIndex]);

    const handleSearchChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
        setSearch(event.target.value);
        setListboxOpen(true);
    }, []);

    const clearSearch = useCallback(() => {
        setSearch('');
        setDebouncedSearch('');
        setListboxOpen(true);
        inputRef.current?.focus();
    }, [inputRef]);

    const handleSelect = useCallback((product: Product) => {
        onSelect(product);
        if (clearOnSelect) {
            setSearch('');
            setDebouncedSearch('');
        }
        // Keep listbox open for rapid multi-item entry
        setListboxOpen(true);
        requestAnimationFrame(() => {
            inputRef.current?.focus();
        });
    }, [onSelect, clearOnSelect, inputRef]);

    const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLInputElement>) => {
        if (!listboxOpen || products.length === 0) {
            if (event.key === 'ArrowDown' && products.length > 0) {
                event.preventDefault();
                setListboxOpen(true);
                setHighlightedIndex(0);
            }
            return;
        }
        switch (event.key) {
            case 'ArrowDown':
                event.preventDefault();
                setHighlightedIndex((prev) => (prev < products.length - 1 ? prev + 1 : 0));
                break;
            case 'ArrowUp':
                event.preventDefault();
                setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : products.length - 1));
                break;
            case 'Enter':
                event.preventDefault();
                if (highlightedIndex >= 0 && highlightedIndex < products.length) {
                    handleSelect(products[highlightedIndex]);
                }
                break;
            case 'Escape':
                event.preventDefault();
                setListboxOpen(false);
                setHighlightedIndex(-1);
                break;
        }
    }, [listboxOpen, products, highlightedIndex, handleSelect]);

    const listboxId = `${idPrefix}-listbox`;
    const activeDescendantId = highlightedIndex >= 0 && products[highlightedIndex]
        ? `${idPrefix}-option-${products[highlightedIndex].id}`
        : undefined;
    const inputId = `${idPrefix}-input`;

    const selectedSet = useMemo(() => new Set(selectedProductIds), [selectedProductIds]);

    return (
        <div>
            {disabled && disabledMessage ? (
                <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
                    {disabledMessage}
                </div>
            ) : (
                <>
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div className="relative w-full">
                            <label htmlFor={inputId} className="mb-1 block text-xs font-semibold text-slate-600">
                                {searchLabel}
                            </label>
                            <div className="relative">
                                <input
                                    id={inputId}
                                    ref={inputRef}
                                    type="search"
                                    role="combobox"
                                    aria-expanded={listboxOpen && products.length > 0}
                                    aria-controls={listboxId}
                                    aria-activedescendant={activeDescendantId}
                                    aria-autocomplete="list"
                                    autoComplete="off"
                                    value={search}
                                    onChange={handleSearchChange}
                                    onKeyDown={handleKeyDown}
                                    onFocus={() => { if (search.trim()) setListboxOpen(true); }}
                                    placeholder={searchPlaceholder}
                                    disabled={disabled}
                                    className="w-full rounded-2xl border border-slate-200 px-4 py-2 pr-9 text-sm disabled:cursor-not-allowed disabled:bg-slate-50 focus:border-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-1"
                                />
                                {search && (
                                    <button
                                        type="button"
                                        onMouseDown={(e) => e.preventDefault()}
                                        onClick={clearSearch}
                                        aria-label="Limpiar búsqueda"
                                        className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full p-1 text-slate-400 hover:text-slate-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-900"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden="true">
                                            <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                                        </svg>
                                    </button>
                                )}
                            </div>
                        </div>
                        {showStockFilter && (
                            <div className="flex flex-wrap gap-2 md:self-end">
                                {STOCK_FILTER_OPTIONS.map((option) => (
                                    <button
                                        key={option.value}
                                        type="button"
                                        onClick={() => setStockFilter(option.value)}
                                        disabled={disabled}
                                        aria-pressed={stockFilter === option.value}
                                        className={`rounded-full px-4 py-1 text-xs font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 ${
                                            stockFilter === option.value
                                                ? 'bg-slate-900 text-white'
                                                : 'border border-slate-200 text-slate-600 hover:border-slate-900'
                                        } disabled:cursor-not-allowed disabled:opacity-50`}
                                    >
                                        {option.label}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    {/* Aria-live region for screen reader announcements */}
                    <div aria-live="polite" aria-atomic="true" className="sr-only">
                        {searchAnnouncement}
                    </div>
                    {!shouldSearch ? (
                        <div className="mt-4 rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
                            Buscá un producto por nombre, SKU o escaneá un código de barras.
                        </div>
                    ) : (
                        <div className="mt-4 rounded-2xl border border-slate-100">
                            {productsQuery.isLoading ? (
                                <p className="p-4 text-sm text-slate-500">Buscando productos...</p>
                            ) : productsQuery.isError ? (
                                <p className="p-4 text-sm text-rose-600">No pudimos cargar los productos. Intentá nuevamente.</p>
                            ) : products.length === 0 ? (
                                <div className="p-4 text-sm text-slate-500">
                                    <p>No encontramos productos para &ldquo;{search.trim()}&rdquo;.</p>
                                    <p className="mt-1 text-xs text-slate-400">Probá con otro nombre, SKU o código de barras.</p>
                                </div>
                            ) : !listboxOpen ? null : (
                                <ul
                                    id={listboxId}
                                    ref={listboxRef}
                                    role="listbox"
                                    aria-label="Resultados de búsqueda de productos"
                                    className="max-h-80 divide-y divide-slate-100 overflow-y-auto"
                                >
                                    {products.map((product, index) => {
                                        const stockMeta = showStockInfo ? getStockMeta(product, stockMetaConfig) : null;
                                        const isHighlighted = index === highlightedIndex;
                                        const isSelected = selectedSet.has(product.id);
                                        return (
                                            <li
                                                key={product.id}
                                                id={`${idPrefix}-option-${product.id}`}
                                                role="option"
                                                aria-selected={isHighlighted}
                                                aria-label={[
                                                    product.name,
                                                    `SKU ${product.sku || 'sin SKU'}`,
                                                    formatCurrencySmart(Number(product.price)),
                                                    stockMeta ? (stockMeta.status === 'out' ? 'sin stock' : `stock ${stockMeta.quantity}`) : '',
                                                ].filter(Boolean).join(', ')}
                                                onMouseDown={(e) => e.preventDefault()}
                                                onClick={() => handleSelect(product)}
                                                onMouseEnter={() => setHighlightedIndex(index)}
                                                className={`flex cursor-pointer flex-wrap items-center justify-between gap-4 px-4 py-3 transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-slate-900 ${
                                                    isHighlighted ? 'bg-slate-100' : 'hover:bg-slate-50 active:bg-slate-100'
                                                }`}
                                            >
                                                <div className="min-w-0 flex-1">
                                                    <p className="font-medium text-slate-900">{product.name}</p>
                                                    <p className="text-xs text-slate-400">
                                                        {product.sku || product.barcode || 'Sin código'}
                                                    </p>
                                                    {stockMeta && (
                                                        <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                                                            <StockBadge status={stockMeta.status} />
                                                            <span>Stock: {stockMeta.quantity}</span>
                                                        </div>
                                                    )}
                                                </div>
                                                <div className="flex flex-col items-end gap-2 sm:flex-row sm:items-center">
                                                    {isSelected && (
                                                        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                                                            ✓ en lista
                                                        </span>
                                                    )}
                                                    <p className="text-sm font-semibold text-slate-600">
                                                        {formatCurrencySmart(Number(product.price))}
                                                    </p>
                                                    {stockMeta && (
                                                        <span
                                                            className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                                                                stockMeta.status === 'out'
                                                                    ? 'border-slate-100 text-slate-400'
                                                                    : 'border-slate-200 text-slate-600'
                                                            }`}
                                                            aria-hidden="true"
                                                        >
                                                            {stockMeta.status === 'out' ? 'Sin stock' : 'Agregar'}
                                                        </span>
                                                    )}
                                                </div>
                                            </li>
                                        );
                                    })}
                                </ul>
                            )}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

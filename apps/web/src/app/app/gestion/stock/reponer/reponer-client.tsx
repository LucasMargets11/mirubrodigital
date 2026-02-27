"use client";

import {
    useDeferredValue,
    useEffect,
    useMemo,
    useRef,
    useState,
    useCallback,
} from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import {
    Loader2,
    ShoppingCart,
    AlertCircle,
    Trash2,
    Search,
    PackageCheck,
    CheckCircle2,
} from 'lucide-react';

import { createReplenishment } from '@/lib/api/replenishment';
import { listAccounts } from '@/lib/api/treasury';
import { useProducts } from '@/features/gestion/hooks';
import { todayDateString } from '@/lib/dates';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RestockLine {
    /** Unique key for React lists */
    key: number;
    product_id: string;
    name: string;
    sku?: string;
    current_stock?: number;
    qty: string;
    unit_cost: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _lineKey = 0;
const nextKey = () => ++_lineKey;

function lineTotal(item: RestockLine): number {
    const q = parseFloat(item.qty);
    const c = parseFloat(item.unit_cost);
    if (!isNaN(q) && !isNaN(c) && q > 0 && c >= 0) return q * c;
    return 0;
}

function formatCurrency(n: number) {
    return n.toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

/** Highlight occurrences of `term` inside `text` with a <mark> */
function Highlight({ text, term }: { text: string; term: string }) {
    if (!term.trim()) return <>{text}</>;
    const idx = text.toLowerCase().indexOf(term.toLowerCase());
    if (idx === -1) return <>{text}</>;
    return (
        <>
            {text.slice(0, idx)}
            <mark className="bg-orange-100 text-orange-800 rounded-sm px-0.5">
                {text.slice(idx, idx + term.length)}
            </mark>
            {text.slice(idx + term.length)}
        </>
    );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ReponerClient() {
    const router = useRouter();

    // -- Header form fields --
    const [accountId, setAccountId] = useState('');
    const [supplierName, setSupplierName] = useState('');
    const [invoiceNumber, setInvoiceNumber] = useState('');
    const [occurredAt, setOccurredAt] = useState(() => todayDateString());
    const [notes, setNotes] = useState('');

    // -- Restock lines (the "cart") --
    const [lines, setLines] = useState<RestockLine[]>([]);

    // -- Validation errors --
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [globalError, setGlobalError] = useState('');

    // -- Product search --
    const [searchRaw, setSearchRaw] = useState('');
    const deferredSearch = useDeferredValue(searchRaw);
    const [highlighted, setHighlighted] = useState(-1);
    const searchInputRef = useRef<HTMLInputElement>(null);
    const listRef = useRef<HTMLUListElement>(null);

    // qty input refs keyed by line.key for auto-focus
    const qtyRefs = useRef<Record<number, HTMLInputElement | null>>({});

    // -- Accounts --
    const accountsQuery = useQuery({ queryKey: ['treasury', 'accounts'], queryFn: listAccounts });
    const accounts = accountsQuery.data ?? [];

    // -- Products (load all once, filter client-side) --
    const productsQuery = useProducts('', true);
    const allProducts = useMemo(() => productsQuery.data ?? [], [productsQuery.data]);

    // -- Filtered suggestions --
    const suggestions = useMemo(() => {
        const term = deferredSearch.trim().toLowerCase();
        if (!term) return allProducts.slice(0, 40);
        return allProducts
            .filter(
                (p: any) =>
                    p.name.toLowerCase().includes(term) ||
                    (p.sku ?? '').toLowerCase().includes(term),
            )
            .slice(0, 40);
    }, [allProducts, deferredSearch]);

    // Reset highlighted when suggestions change
    useEffect(() => {
        setHighlighted(-1);
    }, [suggestions]);

    // Scroll highlighted item into view
    useEffect(() => {
        if (!listRef.current || highlighted < 0) return;
        const el = listRef.current.querySelectorAll('[role="option"]')[highlighted] as HTMLElement | undefined;
        el?.scrollIntoView({ block: 'nearest' });
    }, [highlighted]);

    // -- Set with product_ids already added --
    const addedIds = useMemo(() => new Set(lines.map((l) => l.product_id)), [lines]);

    // ---------------------------------------------------------------------------
    // Line management
    // ---------------------------------------------------------------------------

    const addProduct = useCallback(
        (product: any) => {
            if (addedIds.has(product.id)) {
                // Already added: increment qty and focus qty input
                setLines((prev) =>
                    prev.map((l) => {
                        if (l.product_id !== product.id) return l;
                        const next = (parseFloat(l.qty) || 0) + 1;
                        return { ...l, qty: String(next) };
                    }),
                );
                const existing = lines.find((l) => l.product_id === product.id);
                if (existing) {
                    setTimeout(() => qtyRefs.current[existing.key]?.focus(), 50);
                }
                return;
            }
            const key = nextKey();
            const newLine: RestockLine = {
                key,
                product_id: product.id,
                name: product.name,
                sku: product.sku ?? undefined,
                current_stock: product.current_stock ?? undefined,
                qty: '1',
                unit_cost: '',
            };
            setLines((prev) => [...prev, newLine]);
            // Auto-focus qty input of the new row
            setTimeout(() => qtyRefs.current[key]?.focus(), 50);
        },
        [addedIds, lines],
    );

    const removeLine = useCallback((lineKey: number) => {
        setLines((prev) => prev.filter((l) => l.key !== lineKey));
    }, []);

    const patchLine = useCallback((lineKey: number, patch: Partial<RestockLine>) => {
        setLines((prev) => prev.map((l) => (l.key === lineKey ? { ...l, ...patch } : l)));
    }, []);

    // ---------------------------------------------------------------------------
    // Keyboard navigation in search list
    // ---------------------------------------------------------------------------

    function handleSearchKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setHighlighted((h) => Math.min(h + 1, suggestions.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setHighlighted((h) => Math.max(h - 1, 0));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            const idx = highlighted >= 0 ? highlighted : 0;
            if (suggestions[idx]) {
                addProduct(suggestions[idx]);
                // keep focus on search
                searchInputRef.current?.focus();
            }
        } else if (e.key === 'Escape') {
            setSearchRaw('');
        }
    }

    // ---------------------------------------------------------------------------
    // Totals
    // ---------------------------------------------------------------------------

    const grandTotal = useMemo(
        () => lines.reduce((acc, l) => acc + lineTotal(l), 0),
        [lines],
    );

    const allCostsFilled = lines.length > 0 && lines.every((l) => {
        const c = parseFloat(l.unit_cost);
        return !isNaN(c) && c >= 0;
    });

    // ---------------------------------------------------------------------------
    // Validation
    // ---------------------------------------------------------------------------

    function validate() {
        const errs: Record<string, string> = {};
        if (!accountId) errs.accountId = 'Seleccioná una cuenta.';
        if (!supplierName.trim()) errs.supplierName = 'El proveedor es requerido.';
        if (!occurredAt) errs.occurredAt = 'La fecha es requerida.';
        if (lines.length === 0) errs.lines = 'Agregá al menos un producto.';
        lines.forEach((l) => {
            const q = parseFloat(l.qty);
            if (isNaN(q) || q <= 0) errs[`qty_${l.key}`] = 'Cantidad inválida.';
            const c = parseFloat(l.unit_cost);
            if (isNaN(c) || c < 0) errs[`cost_${l.key}`] = 'Costo inválido.';
        });
        return errs;
    }

    const isFormInvalid = useMemo(() => {
        if (!accountId || !supplierName.trim() || !occurredAt) return true;
        if (lines.length === 0) return true;
        return lines.some((l) => {
            const q = parseFloat(l.qty);
            const c = parseFloat(l.unit_cost);
            return isNaN(q) || q <= 0 || isNaN(c) || c < 0;
        });
    }, [accountId, supplierName, occurredAt, lines]);

    // ---------------------------------------------------------------------------
    // Submit
    // ---------------------------------------------------------------------------

    const mutation = useMutation({
        mutationFn: createReplenishment,
        onSuccess: (data) => {
            router.push(`/app/gestion/stock/compras/${data.id}`);
        },
        onError: (err: any) => {
            setGlobalError(err?.message ?? 'Error al guardar la reposición.');
        },
    });

    function handleSubmit() {
        setGlobalError('');
        const errs = validate();
        setErrors(errs);
        if (Object.keys(errs).length > 0) return;

        mutation.mutate({
            account_id: Number(accountId),
            supplier_name: supplierName.trim(),
            invoice_number: invoiceNumber.trim() || undefined,
            occurred_at: occurredAt,
            notes: notes.trim() || undefined,
            items: lines.map((l) => ({
                product_id: l.product_id,
                quantity: parseFloat(l.qty),
                unit_cost: parseFloat(l.unit_cost),
            })),
        });
    }

    // ---------------------------------------------------------------------------
    // Render
    // ---------------------------------------------------------------------------

    return (
        <div className="space-y-6 pb-28 md:pb-8">
            {/* ── Page Header ───────────────────────────────────────── */}
            <div className="flex items-center gap-3">
                <div className="p-3 rounded-2xl bg-orange-100 text-orange-600">
                    <ShoppingCart className="h-6 w-6" />
                </div>
                <div>
                    <h1 className="text-xl font-bold text-slate-900">Nueva Reposición de Stock</h1>
                    <p className="text-sm text-slate-500">
                        Registrá compras a proveedor con impacto en stock y finanzas
                    </p>
                </div>
            </div>

            {/* ── Header form card ──────────────────────────────────── */}
            <div className="bg-white rounded-3xl border border-slate-200 shadow-sm p-6 space-y-5">
                {/* Row 1: Account + Date */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label htmlFor="account-select" className="block text-sm font-medium text-slate-700 mb-1">
                            Cuenta de pago <span className="text-rose-500">*</span>
                        </label>
                        <select
                            id="account-select"
                            value={accountId}
                            onChange={(e) => setAccountId(e.target.value)}
                            className={cn(
                                'w-full rounded-xl border text-sm px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-orange-400',
                                errors.accountId ? 'border-rose-400' : 'border-slate-300',
                            )}
                        >
                            <option value="">Seleccioná una cuenta</option>
                            {accounts.map((a: any) => (
                                <option key={a.id} value={a.id}>{a.name}</option>
                            ))}
                        </select>
                        {errors.accountId && <p className="text-xs text-rose-600 mt-1">{errors.accountId}</p>}
                    </div>
                    <div>
                        <label htmlFor="date-input" className="block text-sm font-medium text-slate-700 mb-1">
                            Fecha de compra <span className="text-rose-500">*</span>
                        </label>
                        <input
                            id="date-input"
                            type="date"
                            value={occurredAt}
                            onChange={(e) => setOccurredAt(e.target.value)}
                            className={cn(
                                'w-full rounded-xl border text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400',
                                errors.occurredAt ? 'border-rose-400' : 'border-slate-300',
                            )}
                        />
                        {errors.occurredAt && <p className="text-xs text-rose-600 mt-1">{errors.occurredAt}</p>}
                    </div>
                </div>

                {/* Row 2: Supplier + Invoice */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label htmlFor="supplier-input" className="block text-sm font-medium text-slate-700 mb-1">
                            Proveedor <span className="text-rose-500">*</span>
                        </label>
                        <input
                            id="supplier-input"
                            type="text"
                            value={supplierName}
                            onChange={(e) => setSupplierName(e.target.value)}
                            placeholder="Nombre del proveedor"
                            className={cn(
                                'w-full rounded-xl border text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400',
                                errors.supplierName ? 'border-rose-400' : 'border-slate-300',
                            )}
                        />
                        {errors.supplierName && <p className="text-xs text-rose-600 mt-1">{errors.supplierName}</p>}
                    </div>
                    <div>
                        <label htmlFor="invoice-input" className="block text-sm font-medium text-slate-700 mb-1">
                            N° Factura / Remito
                        </label>
                        <input
                            id="invoice-input"
                            type="text"
                            value={invoiceNumber}
                            onChange={(e) => setInvoiceNumber(e.target.value)}
                            placeholder="Opcional"
                            className="w-full rounded-xl border border-slate-300 text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400"
                        />
                    </div>
                </div>

                {/* Notes */}
                <div>
                    <label htmlFor="notes-input" className="block text-sm font-medium text-slate-700 mb-1">Notas</label>
                    <textarea
                        id="notes-input"
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        rows={2}
                        placeholder="Observaciones opcionales..."
                        className="w-full rounded-xl border border-slate-300 text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none"
                    />
                </div>
            </div>

            {/* ── 2-column product section ──────────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">

                {/* ── LEFT: Product search ─────────────────────────── */}
                <div className="bg-white rounded-3xl border border-slate-200 shadow-sm flex flex-col">
                    {/* Panel header */}
                    <div className="px-5 py-4 border-b border-slate-100">
                        <h2 className="font-semibold text-slate-900 text-sm">Buscar productos</h2>
                        <p className="text-xs text-slate-400 mt-0.5">
                            Hacé clic o presioná Enter para agregar
                        </p>
                    </div>

                    {/* Search input */}
                    <div className="px-4 pt-4 pb-2">
                        <label htmlFor="product-search" className="sr-only">Buscar por nombre o SKU</label>
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
                            <input
                                id="product-search"
                                ref={searchInputRef}
                                type="text"
                                value={searchRaw}
                                onChange={(e) => setSearchRaw(e.target.value)}
                                onKeyDown={handleSearchKeyDown}
                                placeholder="Buscar por nombre o SKU…"
                                autoComplete="off"
                                aria-label="Buscar productos por nombre o SKU"
                                aria-controls="product-listbox"
                                aria-haspopup="listbox"
                                className="w-full rounded-xl border border-slate-300 text-sm pl-9 pr-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-orange-400"
                            />
                        </div>
                        <p className="text-xs text-slate-400 mt-1.5">
                            <kbd className="bg-slate-100 border border-slate-200 rounded px-1 text-[10px]">↑↓</kbd>{' '}
                            navegar &nbsp;·&nbsp;
                            <kbd className="bg-slate-100 border border-slate-200 rounded px-1 text-[10px]">Enter</kbd>{' '}
                            agregar
                        </p>
                    </div>

                    {/* Product list */}
                    <div className="px-2 pb-3 flex-1 min-h-0">
                        {productsQuery.isLoading ? (
                            <div className="flex items-center justify-center py-16 text-slate-400 gap-2">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                <span className="text-sm">Cargando productos…</span>
                            </div>
                        ) : suggestions.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-12 text-slate-400 gap-2">
                                <PackageCheck className="h-8 w-8 opacity-30" />
                                <p className="text-sm">No se encontraron productos</p>
                            </div>
                        ) : (
                            <ul
                                id="product-listbox"
                                ref={listRef}
                                role="listbox"
                                aria-label="Resultados de búsqueda"
                                className="overflow-y-auto max-h-[420px] divide-y divide-slate-50 rounded-xl"
                            >
                                {suggestions.map((p: any, idx: number) => {
                                    const isAdded = addedIds.has(p.id);
                                    const isHighlighted = idx === highlighted;
                                    return (
                                        <li
                                            key={p.id}
                                            role="option"
                                            aria-selected={isAdded}
                                            onClick={() => {
                                                addProduct(p);
                                                searchInputRef.current?.focus();
                                            }}
                                            className={cn(
                                                'flex items-center justify-between px-3 py-2.5 rounded-xl cursor-pointer transition-colors',
                                                isHighlighted
                                                    ? 'bg-orange-50'
                                                    : 'hover:bg-slate-50',
                                            )}
                                        >
                                            <div className="min-w-0">
                                                <p className="text-sm font-medium text-slate-900 truncate">
                                                    <Highlight text={p.name} term={deferredSearch} />
                                                </p>
                                                {p.sku && (
                                                    <p className="text-xs text-slate-400 font-mono mt-0.5">
                                                        <Highlight text={p.sku} term={deferredSearch} />
                                                    </p>
                                                )}
                                            </div>
                                            <div className="shrink-0 ml-3">
                                                {isAdded ? (
                                                    <span className="inline-flex items-center gap-1 text-[11px] font-medium bg-green-50 text-green-700 border border-green-200 rounded-full px-2 py-0.5">
                                                        <CheckCircle2 className="h-3 w-3" />
                                                        Agregado
                                                    </span>
                                                ) : (
                                                    <span className="text-[11px] text-orange-500 font-medium opacity-0 group-hover:opacity-100">
                                                        + Agregar
                                                    </span>
                                                )}
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </div>
                </div>

                {/* ── RIGHT: Restock lines ─────────────────────────── */}
                <div className="bg-white rounded-3xl border border-slate-200 shadow-sm flex flex-col">
                    {/* Panel header */}
                    <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                        <div>
                            <h2 className="font-semibold text-slate-900 text-sm">Productos a reponer</h2>
                            <p className="text-xs text-slate-400 mt-0.5">
                                {lines.length === 0
                                    ? 'Ningún producto seleccionado'
                                    : `${lines.length} producto${lines.length > 1 ? 's' : ''} seleccionado${lines.length > 1 ? 's' : ''}`}
                            </p>
                        </div>
                    </div>

                    {errors.lines && (
                        <p className="px-5 py-2 text-xs text-rose-600 bg-rose-50">{errors.lines}</p>
                    )}

                    {/* Lines */}
                    {lines.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 text-slate-300 gap-2">
                            <ShoppingCart className="h-10 w-10 opacity-40" />
                            <p className="text-sm text-slate-400">
                                Seleccioná productos desde el panel izquierdo
                            </p>
                        </div>
                    ) : (
                        <>
                            {/* Column headers */}
                            <div className="grid grid-cols-[1fr_80px_90px_68px_28px] gap-2 px-5 py-2 border-b border-slate-100">
                                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Producto</span>
                                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide text-right">Cant.</span>
                                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide text-right">Costo u.</span>
                                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide text-right">Subtotal</span>
                                <span className="sr-only">Eliminar</span>
                            </div>

                            <div className="divide-y divide-slate-50 overflow-y-auto max-h-[420px]">
                                {lines.map((line) => {
                                    const total = lineTotal(line);
                                    const hasTotal = total > 0;
                                    return (
                                        <div
                                            key={line.key}
                                            className="grid grid-cols-[1fr_80px_90px_68px_28px] gap-2 items-start px-5 py-3"
                                        >
                                            {/* Product name + SKU */}
                                            <div className="min-w-0 pt-0.5">
                                                <p className="text-sm font-medium text-slate-900 truncate leading-tight">
                                                    {line.name}
                                                </p>
                                                {line.sku && (
                                                    <p className="text-[11px] text-slate-400 font-mono">{line.sku}</p>
                                                )}
                                                {errors[`qty_${line.key}`] && (
                                                    <p className="text-[11px] text-rose-600 mt-0.5">{errors[`qty_${line.key}`]}</p>
                                                )}
                                                {errors[`cost_${line.key}`] && (
                                                    <p className="text-[11px] text-rose-600 mt-0.5">{errors[`cost_${line.key}`]}</p>
                                                )}
                                            </div>

                                            {/* Qty */}
                                            <div>
                                                <label
                                                    htmlFor={`qty-${line.key}`}
                                                    className="sr-only"
                                                >
                                                    Cantidad para {line.name}
                                                </label>
                                                <input
                                                    id={`qty-${line.key}`}
                                                    ref={(el) => { qtyRefs.current[line.key] = el; }}
                                                    type="number"
                                                    min="0.01"
                                                    step="0.01"
                                                    value={line.qty}
                                                    onChange={(e) => patchLine(line.key, { qty: e.target.value })}
                                                    onFocus={(e) => e.target.select()}
                                                    className={cn(
                                                        'w-full rounded-lg border text-sm px-2 py-1.5 font-mono text-right focus:outline-none focus:ring-2 focus:ring-orange-400',
                                                        errors[`qty_${line.key}`] ? 'border-rose-400' : 'border-slate-300',
                                                    )}
                                                    placeholder="0"
                                                />
                                            </div>

                                            {/* Unit cost */}
                                            <div>
                                                <label
                                                    htmlFor={`cost-${line.key}`}
                                                    className="sr-only"
                                                >
                                                    Costo unitario para {line.name}
                                                </label>
                                                <input
                                                    id={`cost-${line.key}`}
                                                    type="number"
                                                    min="0"
                                                    step="0.01"
                                                    value={line.unit_cost}
                                                    onChange={(e) => patchLine(line.key, { unit_cost: e.target.value })}
                                                    className={cn(
                                                        'w-full rounded-lg border text-sm px-2 py-1.5 font-mono text-right focus:outline-none focus:ring-2 focus:ring-orange-400',
                                                        errors[`cost_${line.key}`] ? 'border-rose-400' : 'border-slate-300',
                                                    )}
                                                    placeholder="0.00"
                                                />
                                            </div>

                                            {/* Subtotal */}
                                            <div className="text-sm font-mono font-semibold text-right text-slate-700 pt-1.5">
                                                {hasTotal ? `$${formatCurrency(total)}` : <span className="text-slate-300">—</span>}
                                            </div>

                                            {/* Delete */}
                                            <div className="flex justify-center pt-1">
                                                <button
                                                    type="button"
                                                    onClick={() => removeLine(line.key)}
                                                    aria-label={`Eliminar ${line.name} de la reposición`}
                                                    className="text-slate-300 hover:text-rose-500 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 rounded"
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                </button>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </>
                    )}

                    {/* Summary + CTA */}
                    <div className="mt-auto border-t border-slate-100 px-5 py-4 bg-slate-50 rounded-b-3xl space-y-3">
                        {/* Totals row */}
                        <div className="flex items-center justify-between text-sm">
                            <span className="text-slate-500">
                                Items: <strong className="text-slate-900">{lines.length}</strong>
                            </span>
                            {allCostsFilled && lines.length > 0 ? (
                                <span className="font-bold font-mono text-orange-600">
                                    Total: ${formatCurrency(grandTotal)}
                                </span>
                            ) : lines.length > 0 ? (
                                <span className="text-xs text-slate-400">Completá los costos para ver el total</span>
                            ) : null}
                        </div>

                        {/* Global error */}
                        {globalError && (
                            <div className="flex items-center gap-2 p-3 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-700">
                                <AlertCircle className="h-4 w-4 shrink-0" />
                                {globalError}
                            </div>
                        )}

                        {/* Actions */}
                        <div className="flex gap-2">
                            <Button
                                variant="outline"
                                onClick={() => router.back()}
                                disabled={mutation.isPending}
                                className="flex-1"
                            >
                                Cancelar
                            </Button>
                            <Button
                                onClick={handleSubmit}
                                disabled={isFormInvalid || mutation.isPending}
                                className="flex-1 bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-40"
                            >
                                {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Registrar reposición
                            </Button>
                        </div>
                    </div>
                </div>
            </div>

            {/* ── Mobile sticky footer ──────────────────────────────── */}
            <div className="fixed bottom-0 left-0 right-0 z-30 flex md:hidden items-center justify-between gap-3 px-4 py-3 bg-white border-t border-slate-200 shadow-lg">
                <div className="text-sm">
                    <span className="text-slate-500">{lines.length} item{lines.length !== 1 ? 's' : ''}</span>
                    {allCostsFilled && lines.length > 0 && (
                        <span className="ml-2 font-bold font-mono text-orange-600">${formatCurrency(grandTotal)}</span>
                    )}
                </div>
                <Button
                    onClick={handleSubmit}
                    disabled={isFormInvalid || mutation.isPending}
                    className="bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-40"
                >
                    {mutation.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                    Registrar reposición
                </Button>
            </div>
        </div>
    );
}

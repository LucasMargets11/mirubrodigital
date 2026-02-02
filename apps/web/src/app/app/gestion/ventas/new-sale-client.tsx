"use client";

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';

import { ToastBubble } from '@/components/app/toast';
import { SaleCustomerPicker } from './sale-customer-picker';

import { useCashSummary } from '@/features/cash/hooks';
import { useCommercialSettingsQuery, useCreateSale, useProducts } from '@/features/gestion/hooks';
import type { PaymentMethod, Product, SalePayload } from '@/features/gestion/types';
import type { CustomerSummary } from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';

const DEFAULT_LOW_STOCK_THRESHOLD = 5;

type ToastState = {
    message: string;
    tone: 'success' | 'warning' | 'error';
};

type BackendErrorPayload = {
    error?: {
        code?: string;
        message?: string;
        product_id?: string;
        available_stock?: string;
        requested_qty?: string;
    };
};

type CartItem = {
    product: Product;
    quantity: number;
    unitPrice: number;
};

type StockStatus = 'ok' | 'low' | 'out';
type StockFilter = 'all' | 'in' | 'low' | 'out';

const paymentOptions: { value: PaymentMethod; label: string }[] = [
    { value: 'cash', label: 'Efectivo' },
    { value: 'card', label: 'Tarjeta' },
    { value: 'transfer', label: 'Transferencia' },
    { value: 'other', label: 'Otro' },
];

const stockFilterOptions: { value: StockFilter; label: string }[] = [
    { value: 'all', label: 'Todos' },
    { value: 'in', label: 'Con stock' },
    { value: 'low', label: 'Bajo stock' },
    { value: 'out', label: 'Sin stock' },
];

export function NewSaleClient() {
    const router = useRouter();
    const searchInputRef = useRef<HTMLInputElement | null>(null);
    const [search, setSearch] = useState('');
    const [stockFilter, setStockFilter] = useState<StockFilter>('in');
    const [cart, setCart] = useState<CartItem[]>([]);
    const [selectedCustomer, setSelectedCustomer] = useState<CustomerSummary | null>(null);
    const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('cash');
    const [discount, setDiscount] = useState('');
    const [notes, setNotes] = useState('');
    const [feedback, setFeedback] = useState('');
    const [feedbackCode, setFeedbackCode] = useState<string | null>(null);
    const [itemErrors, setItemErrors] = useState<Record<string, string>>({});
    const [toast, setToast] = useState<ToastState | null>(null);
    const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const settingsQuery = useCommercialSettingsQuery();
    const settings = settingsQuery.data;
    const requiresCustomer = settings?.require_customer_for_sales ?? true;
    const allowSellWithoutStock = settings?.allow_sell_without_stock ?? false;
    const allowNegativePricing = settings?.allow_negative_price_or_discount ?? false;
    const warnLowStock = settings?.warn_on_low_stock_threshold_enabled ?? true;
    const lowStockThreshold = warnLowStock
        ? settings?.low_stock_threshold_default ?? DEFAULT_LOW_STOCK_THRESHOLD
        : DEFAULT_LOW_STOCK_THRESHOLD;
    const notesEnabled = settings?.enable_sales_notes ?? true;
    const enforceCashSession = settings?.block_sales_if_no_open_cash_session ?? false;

    useEffect(() => {
        return () => {
            if (toastTimeoutRef.current) {
                clearTimeout(toastTimeoutRef.current);
            }
        };
    }, []);

    const showToast = (message: string, tone: ToastState['tone'] = 'warning') => {
        if (toastTimeoutRef.current) {
            clearTimeout(toastTimeoutRef.current);
        }
        setToast({ message, tone });
        toastTimeoutRef.current = setTimeout(() => setToast(null), 2600);
    };

    const clearItemError = (productId: string) => {
        setItemErrors((prev) => {
            if (!prev[productId]) {
                return prev;
            }
            const next = { ...prev };
            delete next[productId];
            return next;
        });
    };

    const trimmedSearch = search.trim();
    const shouldSearchProducts = trimmedSearch.length >= 2;
    const canOperateWithoutCustomer = !requiresCustomer;
    const canFetchProducts = (canOperateWithoutCustomer || Boolean(selectedCustomer)) && shouldSearchProducts;
    const productSearchDisabled = requiresCustomer && !selectedCustomer;

    const stockMetaConfig = useMemo(
        () => ({ warnLowStock, defaultThreshold: lowStockThreshold }),
        [warnLowStock, lowStockThreshold]
    );

    const productsQuery = useProducts(trimmedSearch, false, { enabled: canFetchProducts });
    const rawProducts = canFetchProducts ? productsQuery.data ?? [] : [];

    const filteredProducts = useMemo(() => {
        return rawProducts.filter((product) => {
            const meta = getStockMeta(product, stockMetaConfig);
            if (stockFilter === 'all') {
                return true;
            }
            if (stockFilter === 'in') {
                return meta.status !== 'out';
            }
            return meta.status === stockFilter;
        });
    }, [rawProducts, stockFilter, stockMetaConfig]);

    const products = filteredProducts.slice(0, 40);

    const createSale = useCreateSale();
    const cashSummaryQuery = useCashSummary();
    const activeSession = cashSummaryQuery.data?.session ?? null;
    const activeSessionId = activeSession?.id ?? null;

    const subtotal = useMemo(() => {
        return cart.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);
    }, [cart]);

    const numericDiscount = Number(discount) || 0;
    const parsedDiscount = allowNegativePricing ? numericDiscount : Math.max(0, numericDiscount);
    const computedTotal = subtotal - parsedDiscount;
    const total = allowNegativePricing ? computedTotal : Math.max(computedTotal, 0);

    const addProductToCart = (product: Product) => {
        const stockMeta = getStockMeta(product, stockMetaConfig);
        if (stockMeta.status === 'out' && !allowSellWithoutStock) {
            showToast('No hay stock disponible para este producto.', 'warning');
            return;
        }
        setCart((prev) => {
            const existing = prev.find((item) => item.product.id === product.id);
            if (existing) {
                return prev.map((item) =>
                    item.product.id === product.id ? { ...item, quantity: Number((item.quantity + 1).toFixed(2)) } : item
                );
            }
            return [...prev, { product, quantity: 1, unitPrice: Number(product.price) }];
        });
        clearItemError(product.id);
    };

    const updateQuantity = (productId: string, value: string) => {
        const numeric = Math.max(0, Number(value));
        setCart((prev) =>
            prev
                .map((item) => (item.product.id === productId ? { ...item, quantity: numeric } : item))
                .filter((item) => item.quantity > 0)
        );
        clearItemError(productId);
    };

    const updateUnitPrice = (productId: string, value: string) => {
        const numeric = Number(value);
        const sanitized = allowNegativePricing ? numeric : Math.max(0, numeric);
        setCart((prev) => prev.map((item) => (item.product.id === productId ? { ...item, unitPrice: sanitized } : item)));
        clearItemError(productId);
    };

    const removeFromCart = (productId: string) => {
        setCart((prev) => prev.filter((item) => item.product.id !== productId));
        clearItemError(productId);
    };

    const handleSubmit = async () => {
        if (requiresCustomer && !selectedCustomer) {
            setFeedback('Seleccioná un cliente antes de confirmar la venta.');
            setFeedbackCode('CUSTOMER_REQUIRED');
            showToast('Seleccioná un cliente para continuar.', 'warning');
            return;
        }
        if (!cart.length) {
            setFeedback('Agregá al menos un producto a la venta.');
            setFeedbackCode('NO_ITEMS');
            return;
        }
        setFeedback('');
        setFeedbackCode(null);
        setItemErrors({});

        const payload: SalePayload = {
            payment_method: paymentMethod,
            discount: parsedDiscount,
            notes: notesEnabled ? notes : undefined,
            items: cart.map((item) => ({
                product_id: item.product.id,
                quantity: item.quantity,
                unit_price: item.unitPrice,
            })),
            cash_session_id: activeSessionId ?? undefined,
        };

        if (selectedCustomer) {
            payload.customer_id = selectedCustomer.id;
        } else {
            payload.customer_id = null;
        }

        try {
            const sale = await createSale.mutateAsync(payload);
            showToast('Venta registrada', 'success');
            router.push(`/app/gestion/ventas/${sale.id}`);
        } catch (error) {
            handleSaleError(error);
        }
    };

    const handleSaleError = (error: unknown) => {
        if (error instanceof ApiError) {
            if (error.status === 403) {
                setFeedback('Tu rol no tiene permiso para registrar ventas.');
                setFeedbackCode('FORBIDDEN');
                showToast('No tenés permisos para registrar ventas.', 'error');
                return;
            }
            const payload = error.payload as BackendErrorPayload | undefined;
            const structured = payload?.error;
            if (structured?.code === 'OUT_OF_STOCK') {
                const message = structured.message ?? 'No hay stock suficiente para vender este producto.';
                if (structured.product_id) {
                    const productId = structured.product_id;
                    setItemErrors((prev) => ({ ...prev, [productId]: message }));
                }
                setFeedback(message);
                setFeedbackCode('OUT_OF_STOCK');
                showToast(message, 'error');
                return;
            }
            if (structured?.code === 'CASH_SESSION_REQUIRED') {
                const message = structured.message ?? 'Necesitás abrir una sesión de caja para registrar ventas.';
                setFeedback(message);
                setFeedbackCode('CASH_SESSION_REQUIRED');
                showToast(message, 'warning');
                return;
            }
            if (structured?.code === 'CUSTOMER_REQUIRED') {
                const message = structured.message ?? 'Seleccioná un cliente antes de confirmar la venta.';
                setFeedback(message);
                setFeedbackCode('CUSTOMER_REQUIRED');
                showToast(message, 'warning');
                return;
            }

            if (error.status === 400 && error.payload) {
                const payloadDetail = error.payload as { items?: string[]; discount?: string[]; detail?: string };
                const detailMessage = payloadDetail.items?.[0] ?? payloadDetail.discount?.[0] ?? payloadDetail.detail;
                if (detailMessage) {
                    setFeedback(detailMessage);
                    setFeedbackCode('VALIDATION_ERROR');
                    showToast(detailMessage, 'warning');
                    return;
                }
            }
        }

        setFeedback('No pudimos registrar la venta, intentá nuevamente.');
        setFeedbackCode('UNKNOWN_ERROR');
        showToast('No pudimos registrar la venta.', 'error');
    };

    const focusSearchInput = () => {
        searchInputRef.current?.focus();
    };

    const isSaving = createSale.isPending;

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3 text-sm text-slate-500">
                <Link href="/app/gestion/ventas" className="font-semibold text-slate-600 hover:text-slate-900">
                    ← Volver al listado
                </Link>
                <span>/</span>
                <p>Nueva venta</p>
            </div>
            <SaleCustomerPicker value={selectedCustomer} onChange={setSelectedCustomer} />
            <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
                <section className="space-y-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div>
                            <h2 className="text-xl font-semibold text-slate-900">Seleccioná productos</h2>
                            <p className="text-sm text-slate-500">
                                Primero elegí un cliente y después buscá por nombre o SKU.
                            </p>
                        </div>
                    </div>
                    {requiresCustomer && !selectedCustomer ? (
                        <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
                            Elegí una opción de cliente para habilitar la búsqueda de productos.
                        </div>
                    ) : (
                        <>
                            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                                <input
                                    ref={searchInputRef}
                                    type="search"
                                    value={search}
                                    onChange={(event) => setSearch(event.target.value)}
                                    placeholder="Buscar por nombre o SKU"
                                    disabled={productSearchDisabled}
                                    className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm disabled:cursor-not-allowed disabled:bg-slate-50 focus:border-slate-900 focus:outline-none"
                                    aria-label="Buscar productos"
                                />
                                <div className="flex flex-wrap gap-2">
                                    {stockFilterOptions.map((option) => (
                                        <button
                                            key={option.value}
                                            type="button"
                                            onClick={() => setStockFilter(option.value)}
                                            disabled={productSearchDisabled}
                                            aria-pressed={stockFilter === option.value}
                                            className={`rounded-full px-4 py-1 text-xs font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 ${stockFilter === option.value
                                                ? 'bg-slate-900 text-white'
                                                : 'border border-slate-200 text-slate-600 hover:border-slate-900'
                                                } disabled:cursor-not-allowed disabled:opacity-50`}
                                        >
                                            {option.label}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            {!shouldSearchProducts ? (
                                <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-sm text-slate-500">
                                    <p>
                                        {productSearchDisabled
                                            ? 'Mostramos resultados cuando selecciones un cliente y escribas al menos 2 caracteres.'
                                            : 'Mostramos resultados cuando ingreses al menos 2 caracteres.'}
                                    </p>
                                    <button
                                        type="button"
                                        onClick={focusSearchInput}
                                        className="mt-3 inline-flex items-center justify-center rounded-full border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900"
                                    >
                                        Buscar por nombre o SKU
                                    </button>
                                </div>
                            ) : (
                                <div className="rounded-2xl border border-slate-100">
                                    {productsQuery.isLoading ? (
                                        <p className="p-4 text-sm text-slate-500">Buscando productos...</p>
                                    ) : productsQuery.isError ? (
                                        <p className="p-4 text-sm text-rose-600">No pudimos cargar los productos. Intentá nuevamente.</p>
                                    ) : products.length === 0 ? (
                                        <p className="p-4 text-sm text-slate-500">No encontramos productos con esos filtros.</p>
                                    ) : (
                                        <ul className="divide-y divide-slate-100">
                                            {products.map((product) => {
                                                const stockMeta = getStockMeta(product, stockMetaConfig);
                                                return (
                                                    <li key={product.id} className="flex flex-wrap items-center justify-between gap-4 px-4 py-3">
                                                        <div className="min-w-0 flex-1">
                                                            <p className="font-medium text-slate-900">{product.name}</p>
                                                            <p className="text-xs text-slate-400">SKU {product.sku || '—'}</p>
                                                            <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                                                                <StockBadge status={stockMeta.status} />
                                                                <span>Stock: {stockMeta.quantity}</span>
                                                            </div>
                                                        </div>
                                                        <div className="flex flex-col items-end gap-2 sm:flex-row sm:items-center">
                                                            <p className="text-sm font-semibold text-slate-600">{formatCurrency(Number(product.price))}</p>
                                                            <button
                                                                type="button"
                                                                onClick={() => addProductToCart(product)}
                                                                disabled={stockMeta.status === 'out'}
                                                                aria-disabled={stockMeta.status === 'out'}
                                                                className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 transition hover:border-slate-900 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
                                                            >
                                                                {stockMeta.status === 'out' ? 'Sin stock' : 'Agregar'}
                                                            </button>
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
                </section>
                <section className="space-y-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-semibold text-slate-900">Detalle</h2>
                        {cart.length ? <p className="text-sm text-slate-500">{cart.length} productos</p> : null}
                    </div>
                    {requiresCustomer && !selectedCustomer ? (
                        <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700">
                            Seleccioná un cliente para registrar la venta.
                        </p>
                    ) : null}
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-xs text-slate-600">
                        {cashSummaryQuery.isLoading ? (
                            <span>Buscando sesión de caja activa...</span>
                        ) : cashSummaryQuery.isError ? (
                            <span>No pudimos comprobar la sesión de caja. La venta se registrará igual.</span>
                        ) : activeSession ? (
                            <span>
                                La venta se vinculará a la caja abierta por {activeSession.opened_by_name || 'tu equipo'}.
                            </span>
                        ) : enforceCashSession ? (
                            <span className="flex flex-col gap-2 text-amber-700 sm:flex-row sm:items-center">
                                <span>Necesitás abrir una sesión de caja antes de registrar ventas.</span>
                                <Link
                                    href="/app/operacion/caja"
                                    className="inline-flex items-center rounded-full border border-amber-300 px-4 py-1 text-xs font-semibold"
                                >
                                    Abrir caja
                                </Link>
                            </span>
                        ) : (
                            <span>
                                No hay una sesión de caja abierta. Podés abrirla desde Operación &gt; Caja para vincular las
                                ventas.
                            </span>
                        )}
                    </div>
                    {cart.length === 0 ? (
                        <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
                            Todavía no agregaste productos.
                        </p>
                    ) : (
                        <div className="space-y-3">
                            {cart.map((item) => {
                                const availableQty = getAvailableQuantity(item.product);
                                const willGoNegative = item.quantity > availableQty;
                                const itemError = itemErrors[item.product.id];
                                return (
                                    <div key={item.product.id} className="rounded-2xl border border-slate-100 p-3">
                                        <div className="flex items-center justify-between gap-3">
                                            <div>
                                                <p className="font-medium text-slate-900">{item.product.name}</p>
                                                <p className="text-xs text-slate-400">SKU {item.product.sku || '—'}</p>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => removeFromCart(item.product.id)}
                                                className="text-xs font-semibold text-rose-600 hover:text-rose-700"
                                            >
                                                Quitar
                                            </button>
                                        </div>
                                        <div className="mt-3 grid gap-3 sm:grid-cols-3">
                                            <label className="text-xs font-semibold text-slate-500">
                                                Cantidad
                                                <input
                                                    type="number"
                                                    min="0"
                                                    step="0.5"
                                                    value={item.quantity}
                                                    onChange={(event) => updateQuantity(item.product.id, event.target.value)}
                                                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                                />
                                            </label>
                                            <label className="text-xs font-semibold text-slate-500">
                                                Precio unitario
                                                <input
                                                    type="number"
                                                    min="0"
                                                    step="0.5"
                                                    value={item.unitPrice}
                                                    onChange={(event) => updateUnitPrice(item.product.id, event.target.value)}
                                                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                                />
                                            </label>
                                            <div className="text-right text-sm font-semibold text-slate-900">
                                                Total
                                                <p className="text-base">{formatCurrency(item.quantity * item.unitPrice)}</p>
                                            </div>
                                        </div>
                                        {allowSellWithoutStock && willGoNegative && (
                                            <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
                                                Este producto quedará con stock negativo (stock actual: {availableQty}).
                                            </p>
                                        )}
                                        {itemError && (
                                            <p className="mt-2 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                                                {itemError}
                                            </p>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                    <div className="space-y-3 border-t border-slate-100 pt-4">
                        <label className="text-xs font-semibold text-slate-500">
                            Medio de pago
                            <select
                                value={paymentMethod}
                                onChange={(event) => setPaymentMethod(event.target.value as PaymentMethod)}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                            >
                                {paymentOptions.map((option) => (
                                    <option key={option.value} value={option.value}>
                                        {option.label}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className="text-xs font-semibold text-slate-500">
                            Descuento
                            <input
                                type="number"
                                min={allowNegativePricing ? undefined : 0}
                                step="50"
                                value={discount}
                                onChange={(event) => setDiscount(event.target.value)}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                        {notesEnabled ? (
                            <label className="text-xs font-semibold text-slate-500">
                                Notas
                                <textarea
                                    value={notes}
                                    onChange={(event) => setNotes(event.target.value)}
                                    rows={3}
                                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                    placeholder="Comentario interno, cliente, etc."
                                />
                            </label>
                        ) : (
                            <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-xs text-slate-500">
                                Las notas están deshabilitadas desde Configuración.
                            </div>
                        )}
                        <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
                            <div className="flex items-center justify-between">
                                <span>Subtotal</span>
                                <span className="font-semibold text-slate-900">{formatCurrency(subtotal)}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <span>Descuento</span>
                                <span className="font-semibold text-slate-900">- {formatCurrency(parsedDiscount)}</span>
                            </div>
                            <div className="mt-2 flex items-center justify-between text-base font-semibold text-slate-900">
                                <span>Total</span>
                                <span>{formatCurrency(total)}</span>
                            </div>
                        </div>
                        {feedback && (
                            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                                <p>{feedback}</p>
                                {feedbackCode === 'CASH_SESSION_REQUIRED' && (
                                    <Link
                                        href="/app/operacion/caja"
                                        className="mt-2 inline-flex items-center rounded-full border border-rose-200 px-4 py-1 text-xs font-semibold text-rose-700 hover:border-rose-400"
                                    >
                                        Abrir caja
                                    </Link>
                                )}
                            </div>
                        )}
                        <button
                            type="button"
                            onClick={handleSubmit}
                            disabled={isSaving || !selectedCustomer || cart.length === 0}
                            className="w-full rounded-full bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                            {isSaving ? 'Registrando venta...' : 'Confirmar venta'}
                        </button>
                    </div>
                </section>
            </div>
            {toast && <ToastBubble message={toast.message} tone={toast.tone} />}
        </div>
    );
}

function formatCurrency(value: number) {
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        maximumFractionDigits: 2,
    }).format(Number.isNaN(value) ? 0 : value);
}

function toNumber(value: string | number | null | undefined) {
    if (typeof value === 'number') {
        return value;
    }
    if (typeof value === 'string') {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }
    return 0;
}

function getAvailableQuantity(product: Product) {
    return Math.max(0, toNumber(product.stock_quantity));
}

function getStockMeta(
    product: Product,
    config?: { warnLowStock: boolean; defaultThreshold: number }
): { quantity: number; status: StockStatus } {
    const quantity = getAvailableQuantity(product);
    if (quantity === 0) {
        return { quantity: 0, status: 'out' };
    }
    const productThreshold = Math.max(0, toNumber(product.stock_min));
    const baseThreshold = Math.max(productThreshold, config?.defaultThreshold ?? DEFAULT_LOW_STOCK_THRESHOLD);
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

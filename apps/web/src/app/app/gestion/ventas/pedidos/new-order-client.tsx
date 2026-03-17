"use client";

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';

import { ToastBubble } from '@/components/app/toast';
import { SaleCustomerPicker } from '../sale-customer-picker';

import { useCommercialSettingsQuery, useCreateOrder, useProducts } from '@/features/gestion/hooks';
import type { Product, CreateOrderPayload } from '@/features/gestion/types';
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

const stockFilterOptions: { value: StockFilter; label: string }[] = [
    { value: 'all', label: 'Todos' },
    { value: 'in', label: 'Con stock' },
    { value: 'low', label: 'Bajo stock' },
    { value: 'out', label: 'Sin stock' },
];

function formatCurrency(value: string | number) {
    const numeric = typeof value === 'number' ? value : Number(value);
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
    }).format(Number.isNaN(numeric) ? 0 : numeric);
}

function StockBadge({ status }: { status: StockStatus }) {
    if (status === 'out') {
        return <span className="inline-flex items-center rounded-md bg-rose-50 px-2 py-1 text-xs font-medium text-rose-700 ring-1 ring-inset ring-rose-600/10">Sin stock</span>;
    }
    if (status === 'low') {
        return <span className="inline-flex items-center rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-600/10">Bajo stock</span>;
    }
    return <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/10">En stock</span>;
}

function getStockMeta(product: Product, config: { warnLowStock: boolean; defaultThreshold: number }): { status: StockStatus; quantity: number } {
    const quantity = Number(product.stock_quantity) || 0;
    if (quantity <= 0) {
        return { status: 'out', quantity: 0 };
    }
    if (config.warnLowStock && quantity <= config.defaultThreshold) {
        return { status: 'low', quantity };
    }
    return { status: 'ok', quantity };
}

function getAvailableQuantity(product: Product): number {
    return Number(product.stock_quantity) || 0;
}

export function NewOrderClient() {
    const router = useRouter();
    const searchInputRef = useRef<HTMLInputElement | null>(null);
    const [search, setSearch] = useState('');
    const [stockFilter, setStockFilter] = useState<StockFilter>('in');
    const [cart, setCart] = useState<CartItem[]>([]);
    const [selectedCustomer, setSelectedCustomer] = useState<CustomerSummary | null>(null);
    const [notes, setNotes] = useState('');
    const [deliveryDate, setDeliveryDate] = useState('');
    const [feedback, setFeedback] = useState('');
    const [feedbackCode, setFeedbackCode] = useState<string | null>(null);
    const [itemErrors, setItemErrors] = useState<Record<string, string>>({});
    const [toast, setToast] = useState<ToastState | null>(null);
    const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const settingsQuery = useCommercialSettingsQuery();
    const settings = settingsQuery.data;
    // Orders typically REQUIRE a customer
    const requiresCustomer = true; 
    const allowSellWithoutStock = settings?.allow_sell_without_stock ?? false;
    const warnLowStock = settings?.warn_on_low_stock_threshold_enabled ?? true;
    const lowStockThreshold = warnLowStock
        ? settings?.low_stock_threshold_default ?? DEFAULT_LOW_STOCK_THRESHOLD
        : DEFAULT_LOW_STOCK_THRESHOLD;
    const notesEnabled = settings?.enable_sales_notes ?? true;

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

    const productsQuery = useProducts(trimmedSearch, false, undefined, { enabled: canFetchProducts });
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

    const createOrder = useCreateOrder();

    const subtotal = useMemo(() => {
        return cart.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);
    }, [cart]);

    // No global discount for orders in this version
    const total = subtotal;

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
        const numeric = Math.max(0, Number(value));
        setCart((prev) => prev.map((item) => (item.product.id === productId ? { ...item, unitPrice: numeric } : item)));
        clearItemError(productId);
    };

    const removeFromCart = (productId: string) => {
        setCart((prev) => prev.filter((item) => item.product.id !== productId));
        clearItemError(productId);
    };

    const handleSubmit = async () => {
        if (requiresCustomer && !selectedCustomer) {
            setFeedback('Seleccioná un cliente antes de confirmar el pedido.');
            setFeedbackCode('CUSTOMER_REQUIRED');
            showToast('Seleccioná un cliente para continuar.', 'warning');
            return;
        }
        if (!cart.length) {
            setFeedback('Agregá al menos un producto al pedido.');
            setFeedbackCode('NO_ITEMS');
            return;
        }
        setFeedback('');
        setFeedbackCode(null);
        setItemErrors({});

        const payload: CreateOrderPayload = {
            customer: selectedCustomer.id,
            items: cart.map((item) => ({
                product_id: item.product.id,
                quantity: item.quantity,
                unit_price: item.unitPrice,
            })),
            notes: notesEnabled ? notes : undefined,
            estimated_delivery_date: deliveryDate || undefined,
        };

        try {
            const order = await createOrder.mutateAsync(payload);
            showToast('Pedido creado', 'success');
            router.push(`/app/gestion/ventas/pedidos/${order.id}`);
        } catch (error) {
            handleOrderError(error);
        }
    };

    const handleOrderError = (error: unknown) => {
        if (error instanceof ApiError) {
            if (error.status === 403) {
                setFeedback('Tu rol no tiene permiso para crear pedidos.');
                setFeedbackCode('FORBIDDEN');
                showToast('No tenés permisos para crear pedidos.', 'error');
                return;
            }
            const payload = error.payload as BackendErrorPayload | undefined;
            const structured = payload?.error;
            if (structured?.code === 'OUT_OF_STOCK') {
                const message = structured.message ?? 'No hay stock suficiente para este producto.';
                if (structured.product_id) {
                    const productId = structured.product_id;
                    setItemErrors((prev) => ({ ...prev, [productId]: message }));
                }
                setFeedback(message);
                setFeedbackCode('OUT_OF_STOCK');
                showToast(message, 'error');
                return;
            }
        }

        setFeedback('No pudimos crear el pedido, intentá nuevamente.');
        setFeedbackCode('UNKNOWN_ERROR');
        showToast('No pudimos crear el pedido.', 'error');
    };

    const focusSearchInput = () => {
        searchInputRef.current?.focus();
    };

    const isSaving = createOrder.isPending;

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-3 text-sm text-slate-500">
                <Link href="/app/gestion/ventas/pedidos" className="font-semibold text-slate-600 hover:text-slate-900">
                    ← Volver a pedidos
                </Link>
                <span>/</span>
                <p>Nuevo pedido</p>
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
                            Elegí un cliente para habilitar la búsqueda de productos.
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
                                                    <li
                                                        key={product.id}
                                                        role="button"
                                                        tabIndex={0}
                                                        aria-label={`Agregar ${product.name} al carrito`}
                                                        onClick={() => addProductToCart(product)}
                                                        onKeyDown={(e) => {
                                                            if (e.key === 'Enter' || e.key === ' ') {
                                                                e.preventDefault();
                                                                addProductToCart(product);
                                                            }
                                                        }}
                                                        className="flex cursor-pointer flex-wrap items-center justify-between gap-4 px-4 py-3 transition hover:bg-slate-50 active:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-slate-900"
                                                    >
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
                                                                onClick={(e) => { e.stopPropagation(); addProductToCart(product); }}
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
                            Seleccioná un cliente para crear el pedido.
                        </p>
                    ) : null}
                    
                    {cart.length === 0 ? (
                        <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
                            El carrito está vacío.
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
                                                    onFocus={(e) => e.target.select()}
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
                                                    onFocus={(e) => e.target.select()}
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
                            Fecha de Entrega (Estimada)
                            <input
                                type="date"
                                value={deliveryDate}
                                onChange={(event) => setDeliveryDate(event.target.value)}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                        {notesEnabled ? (
                            <label className="text-xs font-semibold text-slate-500">
                                Notas / Observaciones
                                <textarea
                                    value={notes}
                                    onChange={(event) => setNotes(event.target.value)}
                                    rows={3}
                                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                    placeholder="Instrucciones para la entrega, etc."
                                />
                            </label>
                        ) : null}
                        
                        <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
                            <div className="mt-2 flex items-center justify-between text-base font-semibold text-slate-900">
                                <span>Total Estimado</span>
                                <span>{formatCurrency(total)}</span>
                            </div>
                            <p className="mt-1 text-xs text-slate-400">
                                El total final puede variar si modificás el pedido más adelante.
                            </p>
                        </div>

                        {feedback && (
                            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                                <p>{feedback}</p>
                            </div>
                        )}
                        <button
                            type="button"
                            onClick={handleSubmit}
                            disabled={isSaving}
                            className="flex w-full items-center justify-center rounded-xl bg-slate-900 px-4 py-3 font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {isSaving ? 'Creando pedido...' : 'Crear pedido'}
                        </button>
                    </div>
                </section>
            </div>
            {toast ? <ToastBubble message={toast.message} tone={toast.tone} /> : null}
        </div>
    );
}
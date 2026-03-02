"use client";

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, useMemo, useRef, useEffect } from 'react';

import { SaleCustomerPicker } from '../../sale-customer-picker';
import { useCreateQuote, useProducts, useBusinessBillingProfileQuery, useDocumentSeriesQuery } from '@/features/gestion/hooks';
import type { Product, QuotePayload } from '@/features/gestion/types';
import type { CustomerSummary } from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';
import { formatCurrencySmart, formatNumberSmart } from '@/lib/format';

type CartItem = {
    product: Product | null;
    name: string;
    quantity: number;
    unitPrice: number;
    discount: number;
};

export function NewQuoteClient() {
    const router = useRouter();
    const [search, setSearch] = useState('');
    const [cart, setCart] = useState<CartItem[]>([]);
    const [selectedCustomer, setSelectedCustomer] = useState<CustomerSummary | null>(null);
    const [customerName, setCustomerName] = useState('');
    const [customerEmail, setCustomerEmail] = useState('');
    const [customerPhone, setCustomerPhone] = useState('');
    const [validUntil, setValidUntil] = useState('');
    const [notes, setNotes] = useState('');
    const [terms, setTerms] = useState('');
    const [selectedSeriesId, setSelectedSeriesId] = useState('');
    const [feedback, setFeedback] = useState('');
    const searchInputRef = useRef<HTMLInputElement>(null);
    const [highlightedId, setHighlightedId] = useState<number | null>(null);

    const billingProfileQuery = useBusinessBillingProfileQuery();
    const documentSeriesQuery = useDocumentSeriesQuery();
    const trimmedSearch = search.trim();
    const shouldSearch = trimmedSearch.length >= 2;
    const productsQuery = useProducts(trimmedSearch, false, undefined, { enabled: shouldSearch });
    const products = shouldSearch ? (productsQuery.data ?? []).slice(0, 20) : [];

    const createQuote = useCreateQuote();

    const billingProfile = billingProfileQuery.data;
    const isProfileComplete = billingProfile?.is_complete ?? false;
    const allSeries = documentSeriesQuery.data ?? [];
    const quoteSeries = allSeries.filter(s => s.document_type === 'quote' && s.is_active);
    const defaultQuoteSeries = useMemo(
        () => quoteSeries.find((serie) => serie.is_default)?.id ?? quoteSeries[0]?.id ?? '',
        [quoteSeries],
    );

    // Auto-select default series
    useEffect(() => {
        if (defaultQuoteSeries && !selectedSeriesId) {
            setSelectedSeriesId(defaultQuoteSeries);
        }
    }, [defaultQuoteSeries, selectedSeriesId]);

    const subtotal = useMemo(() => {
        return cart.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);
    }, [cart]);

    const discountTotal = useMemo(() => {
        return cart.reduce((sum, item) => sum + item.discount, 0);
    }, [cart]);

    const total = subtotal - discountTotal;

    const addToCart = (product: Product) => {
        setCart((prev) => {
            const existing = prev.find((item) => item.product?.id === product.id);
            if (existing) {
                return prev.map((item) =>
                    item.product?.id === product.id
                        ? { ...item, quantity: item.quantity + 1 }
                        : item
                );
            }
            return [
                ...prev,
                {
                    product,
                    name: product.name,
                    quantity: 1,
                    unitPrice: Number(product.price),
                    discount: 0,
                },
            ];
        });
        // Highlight the row briefly and refocus the search — do NOT clear search so the list stays open
        setHighlightedId(product.id);
        requestAnimationFrame(() => {
            searchInputRef.current?.focus();
        });
        setTimeout(() => setHighlightedId(null), 500);
    };

    const addManualItem = () => {
        setCart((prev) => [
            ...prev,
            {
                product: null,
                name: '',
                quantity: 1,
                unitPrice: 0,
                discount: 0,
            },
        ]);
    };

    const updateCartItem = (index: number, updates: Partial<CartItem>) => {
        setCart((prev) =>
            prev.map((item, i) => (i === index ? { ...item, ...updates } : item))
        );
    };

    const removeFromCart = (index: number) => {
        setCart((prev) => prev.filter((_, i) => i !== index));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFeedback('');

        if (!isProfileComplete) {
            setFeedback('Tu perfil fiscal está incompleto. Completá los datos antes de crear presupuestos.');
            return;
        }

        if (cart.length === 0) {
            setFeedback('Agregá al menos un ítem al presupuesto.');
            return;
        }

        if (!selectedCustomer && !customerName.trim()) {
            setFeedback('Ingresá un cliente o nombre para el presupuesto.');
            return;
        }

        if (!selectedSeriesId) {
            setFeedback('Seleccioná una serie para el presupuesto.');
            return;
        }

        const payload: QuotePayload = {
            customer_id: selectedCustomer?.id ?? null,
            customer_name: customerName.trim() || undefined,
            customer_email: customerEmail.trim() || undefined,
            customer_phone: customerPhone.trim() || undefined,
            valid_until: validUntil || undefined,
            notes: notes.trim() || undefined,
            terms: terms.trim() || undefined,
            document_series_id: selectedSeriesId || undefined,
            items: cart.map((item) => ({
                product_id: item.product?.id ?? null,
                name: item.name.trim() || item.product?.name || 'Ítem',
                quantity: item.quantity,
                unit_price: item.unitPrice,
                discount: item.discount,
            })),
        };

        try {
            const result = await createQuote.mutateAsync(payload);
            router.push(`/app/gestion/ventas/presupuestos/${result.id}` as any);
        } catch (error) {
            if (error instanceof ApiError) {
                setFeedback(error.message || 'Error al crear el presupuesto.');
            } else {
                setFeedback('Error inesperado al crear el presupuesto.');
            }
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-4">
            <header className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <h2 className="text-2xl font-semibold text-slate-900">Nuevo presupuesto</h2>
                <p className="text-sm text-slate-500">Creá una cotización para enviar al cliente.</p>
            </header>

            {feedback && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    {feedback}
                    {feedback.includes('incompleto') && (
                        <Link href={("/app/gestion/configuracion/negocio" as any)} className="mt-2 block font-semibold underline hover:text-rose-800">
                            Completar datos del negocio →
                        </Link>
                    )}
                </div>
            )}

            {!isProfileComplete && (
                <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                    <p className="font-semibold">⚠️ Perfil fiscal incompleto</p>
                    <p className="mt-1">Completá los datos de tu negocio para crear presupuestos.</p>
                    <Link href={("/app/gestion/configuracion/negocio" as any)} className="mt-2 inline-block font-semibold underline hover:text-amber-800">
                        Ir a configuración →
                    </Link>
                </div>
            )}

            {/* Emisor (read-only) */}
            {billingProfile && isProfileComplete && (
                <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                    <h3 className="mb-3 text-lg font-semibold text-slate-900">Emisor</h3>
                    <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-3">
                        <div className="space-y-1 text-sm text-emerald-900">
                            <p><span className="font-medium">Razón social:</span> {billingProfile.legal_name}</p>
                            <p><span className="font-medium">CUIT:</span> {billingProfile.tax_id}</p>
                            {billingProfile.commercial_address && (
                                <p><span className="font-medium">Dirección:</span> {billingProfile.commercial_address}</p>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Serie */}
            {isProfileComplete && (
                <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                    <h3 className="mb-3 text-lg font-semibold text-slate-900">Serie del presupuesto</h3>
                    <label className="block text-sm font-semibold text-slate-700">
                        Serie <span className="text-rose-600" aria-hidden="true">*</span>
                        <select
                            value={selectedSeriesId}
                            onChange={(e) => setSelectedSeriesId(e.target.value)}
                            className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                            required
                        >
                            <option value="">Seleccionar serie</option>
                            {quoteSeries.map((serie) => (
                                <option key={serie.id} value={serie.id}>
                                    {serie.document_type.toUpperCase()} {serie.letter}
                                    {serie.prefix ? ` - ${serie.prefix}` : ''}
                                    {' '}(PV {String(serie.point_of_sale).padStart(4, '0')} - Próx: #{String(serie.next_number).padStart(8, '0')})
                                    {serie.is_default ? ' ⭐' : ''}
                                </option>
                            ))}
                        </select>
                    </label>
                    {quoteSeries.length === 0 && (
                        <p className="mt-2 text-sm text-amber-700">
                            No hay series de presupuesto configuradas.{' '}
                            <Link href={("/app/gestion/configuracion/negocio" as any)} className="font-semibold underline">
                                Crear una serie
                            </Link>
                        </p>
                    )}
                </div>
            )}

            {/* Cliente */}
            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="mb-3 text-lg font-semibold text-slate-900">Cliente</h3>
                <div className="space-y-3">
                    <SaleCustomerPicker
                        value={selectedCustomer}
                        onChange={setSelectedCustomer}
                    />
                    {!selectedCustomer && (
                        <>
                            <input
                                type="text"
                                value={customerName}
                                onChange={(e) => setCustomerName(e.target.value)}
                                placeholder="Nombre del cliente"
                                className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                            <input
                                type="email"
                                value={customerEmail}
                                onChange={(e) => setCustomerEmail(e.target.value)}
                                placeholder="Email (opcional)"
                                className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                            <input
                                type="tel"
                                value={customerPhone}
                                onChange={(e) => setCustomerPhone(e.target.value)}
                                placeholder="Teléfono (opcional)"
                                className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </>
                    )}
                </div>
            </div>

            <div className="grid items-start gap-6 lg:grid-cols-[2fr_1fr]">

            {/* Productos */}
            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="mb-3 text-lg font-semibold text-slate-900">Productos / Servicios</h3>
                
                <div className="mb-4 space-y-2">
                    <div className="relative">
                        <input
                            ref={searchInputRef}
                            type="search"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Buscar productos por nombre, SKU o código de barras…"
                            autoComplete="off"
                            aria-label="Buscar productos"
                            aria-autocomplete="list"
                            aria-expanded={shouldSearch && products.length > 0}
                            className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                        {search.length > 0 && (
                            <button
                                type="button"
                                onMouseDown={(e) => e.preventDefault()}
                                onClick={() => { setSearch(''); searchInputRef.current?.focus(); }}
                                aria-label="Limpiar búsqueda"
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                            >
                                ✕
                            </button>
                        )}
                    </div>
                    {shouldSearch && productsQuery.isLoading && (
                        <p className="text-sm text-slate-500">Buscando…</p>
                    )}
                    {shouldSearch && !productsQuery.isLoading && products.length === 0 && (
                        <p className="text-sm text-slate-400">Sin resultados para &ldquo;{search}&rdquo;</p>
                    )}
                    {shouldSearch && !productsQuery.isLoading && products.length > 0 && (
                        <div
                            role="listbox"
                            aria-label="Resultados de productos"
                            className="max-h-60 overflow-y-auto rounded-2xl border border-slate-200 bg-white shadow-sm"
                        >
                            {products.map((product) => (
                                <button
                                    key={product.id}
                                    type="button"
                                    role="option"
                                    aria-selected={cart.some((i) => i.product?.id === product.id)}
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => addToCart(product)}
                                    className="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left transition-colors hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline-none"
                                >
                                    <div className="min-w-0 flex-1">
                                        <p className="truncate text-sm font-medium text-slate-900">{product.name}</p>
                                        <p className="text-xs text-slate-400">
                                            {product.sku || product.barcode || 'Sin código'}
                                        </p>
                                    </div>
                                    <div className="flex shrink-0 items-center gap-2">
                                        {cart.some((i) => i.product?.id === product.id) && (
                                            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                                                ✓ en lista
                                            </span>
                                        )}
                                        <span className="text-sm font-semibold text-slate-900">
                                            {formatCurrencySmart(Number(product.price))}
                                        </span>
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}
                </div>

            </div>

            {/* Detalles */}
            <div className="flex flex-col rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="mb-3 text-lg font-semibold text-slate-900">Detalles</h3>
                <div className="flex flex-1 flex-col">
                    <div className="space-y-3">
                        <div>
                            <label className="mb-1 block text-sm font-medium text-slate-700">
                                Válido hasta (opcional)
                            </label>
                            <input
                                type="date"
                                value={validUntil}
                                onChange={(e) => setValidUntil(e.target.value)}
                                className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </div>
                        <div>
                            <label className="mb-1 block text-sm font-medium text-slate-700">
                                Notas (opcional)
                            </label>
                            <textarea
                                value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                                placeholder="Notas internas o para el cliente"
                                rows={3}
                                className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </div>
                    </div>

                    {/* Ítems agregados */}
                    <div className="mt-4">
                        <div className="mb-2 flex items-center justify-between">
                            <p className="text-sm font-semibold text-slate-700">
                                Ítems del presupuesto
                                {cart.length > 0 && <span className="ml-1.5 font-normal text-slate-400">{cart.length} {cart.length === 1 ? 'producto' : 'productos'}</span>}
                            </p>
                            <button
                                type="button"
                                onClick={addManualItem}
                                className="text-xs font-semibold text-blue-600 hover:text-blue-800"
                            >
                                + Agregar manual
                            </button>
                        </div>

                        {cart.length === 0 ? (
                            <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
                                Buscá productos a la izquierda para agregarlos al presupuesto.
                            </p>
                        ) : (
                            <div className="space-y-3">
                                {cart.map((item, index) => {
                                    const rowSubtotal = item.quantity * item.unitPrice - item.discount;
                                    const isHighlighted = item.product?.id != null && item.product.id === highlightedId;
                                    return (
                                        <div
                                            key={index}
                                            className={[
                                                'rounded-2xl border border-slate-100 p-3 transition-colors duration-300',
                                                isHighlighted ? 'bg-emerald-50' : '',
                                            ].join(' ')}
                                        >
                                            <div className="flex items-start justify-between gap-3">
                                                <div>
                                                    {item.product === null ? (
                                                        <input
                                                            type="text"
                                                            value={item.name}
                                                            onChange={(e) => updateCartItem(index, { name: e.target.value })}
                                                            placeholder="Nombre del producto"
                                                            aria-label="Nombre del ítem"
                                                            className="rounded-xl border border-slate-200 px-3 py-1 text-sm font-medium text-slate-900 focus:border-slate-400 focus:outline-none"
                                                        />
                                                    ) : (
                                                        <>
                                                            <p className="font-medium text-slate-900">{item.name}</p>
                                                            {(item.product.sku || item.product.barcode) && (
                                                                <p className="text-xs text-slate-400">SKU {item.product.sku || item.product.barcode}</p>
                                                            )}
                                                        </>
                                                    )}
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => removeFromCart(index)}
                                                    aria-label="Quitar ítem"
                                                    className="shrink-0 text-xs font-semibold text-rose-600 hover:text-rose-700"
                                                >
                                                    Quitar
                                                </button>
                                            </div>
                                            <div className="mt-3 grid gap-3 sm:grid-cols-4">
                                                <label className="text-xs font-semibold text-slate-500">
                                                    Cantidad
                                                    <input
                                                        type="number"
                                                        min="1"
                                                        step="1"
                                                        value={item.quantity}
                                                        onChange={(e) => updateCartItem(index, { quantity: Math.max(1, Number(e.target.value) || 1) })}
                                                        onBlur={(e) => { if (!e.target.value || Number(e.target.value) < 1) updateCartItem(index, { quantity: 1 }); }}
                                                        onFocus={(e) => e.target.select()}
                                                        aria-label="Cantidad"
                                                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                                    />
                                                </label>
                                                <label className="text-xs font-semibold text-slate-500">
                                                    Precio unitario
                                                    <input
                                                        type="number"
                                                        min="0"
                                                        step="0.01"
                                                        value={item.unitPrice}
                                                        onChange={(e) => updateCartItem(index, { unitPrice: Math.max(0, Number(e.target.value)) })}
                                                        onFocus={(e) => e.target.select()}
                                                        aria-label="Precio unitario"
                                                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                                    />
                                                </label>
                                                <label className="text-xs font-semibold text-slate-500">
                                                    Descuento ($)
                                                    <input
                                                        type="number"
                                                        min="0"
                                                        step="0.01"
                                                        value={item.discount}
                                                        onChange={(e) => updateCartItem(index, { discount: Math.max(0, Number(e.target.value)) })}
                                                        onFocus={(e) => e.target.select()}
                                                        placeholder="0"
                                                        aria-label="Descuento"
                                                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                                    />
                                                </label>
                                                <div className="text-right text-xs font-semibold text-slate-500">
                                                    Total
                                                    <p className="mt-1 text-base text-slate-900">{formatCurrencySmart(rowSubtotal)}</p>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {/* Totales */}
                    <div className="mt-auto space-y-1 border-t border-slate-100 pt-3">
                        <div className="flex justify-between text-sm">
                            <span className="text-slate-500">Subtotal:</span>
                            <span className="font-semibold text-slate-900">{formatCurrencySmart(subtotal)}</span>
                        </div>
                        {discountTotal > 0 && (
                            <div className="flex justify-between text-sm">
                                <span className="text-slate-500">Descuentos:</span>
                                <span className="font-semibold text-rose-600">-{formatCurrencySmart(discountTotal)}</span>
                            </div>
                        )}
                        <div className="flex justify-between border-t border-slate-200 pt-2">
                            <span className="text-base font-semibold text-slate-900">Total:</span>
                            <span className="text-base font-semibold text-slate-900">{formatCurrencySmart(total)}</span>
                        </div>
                    </div>

                    {/* Acciones */}
                    <div className="flex gap-2 pt-1">
                        <Link
                            href={"/app/gestion/ventas/presupuestos" as any}
                            className="inline-flex flex-1 items-center justify-center rounded-full border border-slate-300 bg-white px-5 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                        >
                            Cancelar
                        </Link>
                        <button
                            type="submit"
                            disabled={createQuote.isPending || !isProfileComplete}
                            className="inline-flex flex-1 items-center justify-center rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                        >
                            {createQuote.isPending ? 'Guardando...' : 'Guardar presupuesto'}
                        </button>
                    </div>
                </div>
            </div>
            </div>

            {/* Términos */}
            <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <h3 className="mb-3 text-lg font-semibold text-slate-900">Términos y condiciones (opcional)</h3>
                <textarea
                    value={terms}
                    onChange={(e) => setTerms(e.target.value)}
                    placeholder="Ej: Presupuesto válido por 15 días. No incluye instalación."
                    rows={3}
                    className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                />
            </div>
        </form>
    );
}

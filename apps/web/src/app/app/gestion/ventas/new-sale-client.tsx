"use client";

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';

import { CustomerPicker } from './customer-picker';

import { useCreateSale, useProducts } from '@/features/gestion/hooks';
import type { PaymentMethod, Product, SalePayload } from '@/features/gestion/types';
import type { CustomerSummary } from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';

function formatCurrency(value: number) {
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: 'ARS',
        maximumFractionDigits: 2,
    }).format(Number.isNaN(value) ? 0 : value);
}

type CartItem = {
    product: Product;
    quantity: number;
    unitPrice: number;
};

const paymentOptions: { value: PaymentMethod; label: string }[] = [
    { value: 'cash', label: 'Efectivo' },
    { value: 'card', label: 'Tarjeta' },
    { value: 'transfer', label: 'Transferencia' },
    { value: 'other', label: 'Otro' },
];

export function NewSaleClient() {
    const router = useRouter();
    const [search, setSearch] = useState('');
    const [cart, setCart] = useState<CartItem[]>([]);
    const [selectedCustomer, setSelectedCustomer] = useState<CustomerSummary | null>(null);
    const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('cash');
    const [discount, setDiscount] = useState('');
    const [notes, setNotes] = useState('');
    const [feedback, setFeedback] = useState('');

    const productsQuery = useProducts(search, false);
    const createSale = useCreateSale();

    const subtotal = useMemo(() => {
        return cart.reduce((sum, item) => sum + item.quantity * item.unitPrice, 0);
    }, [cart]);

    const parsedDiscount = Math.max(0, Number(discount) || 0);
    const total = Math.max(subtotal - parsedDiscount, 0);

    const addProductToCart = (product: Product) => {
        setCart((prev) => {
            const existing = prev.find((item) => item.product.id === product.id);
            if (existing) {
                return prev.map((item) =>
                    item.product.id === product.id ? { ...item, quantity: Number((item.quantity + 1).toFixed(2)) } : item
                );
            }
            return [...prev, { product, quantity: 1, unitPrice: Number(product.price) }];
        });
    };

    const updateQuantity = (productId: string, value: string) => {
        const numeric = Math.max(0, Number(value));
        setCart((prev) =>
            prev
                .map((item) => (item.product.id === productId ? { ...item, quantity: numeric } : item))
                .filter((item) => item.quantity > 0)
        );
    };

    const updateUnitPrice = (productId: string, value: string) => {
        const numeric = Math.max(0, Number(value));
        setCart((prev) => prev.map((item) => (item.product.id === productId ? { ...item, unitPrice: numeric } : item)));
    };

    const removeFromCart = (productId: string) => {
        setCart((prev) => prev.filter((item) => item.product.id !== productId));
    };

    const handleSubmit = async () => {
        if (!cart.length) {
            setFeedback('Agregá al menos un producto a la venta.');
            return;
        }
        setFeedback('');

        const payload: SalePayload = {
            customer_id: selectedCustomer?.id ?? null,
            payment_method: paymentMethod,
            discount: parsedDiscount,
            notes,
            items: cart.map((item) => ({
                product_id: item.product.id,
                quantity: item.quantity,
                unit_price: item.unitPrice,
            })),
        };

        try {
            const sale = await createSale.mutateAsync(payload);
            router.push(`/app/gestion/ventas/${sale.id}`);
        } catch (error) {
            if (error instanceof ApiError) {
                if (error.status === 403) {
                    setFeedback('Tu rol no tiene permiso para registrar ventas.');
                    return;
                }
                if (error.status === 400 && error.payload) {
                    const payloadDetail = error.payload as { items?: string[]; discount?: string[]; detail?: string };
                    const detailMessage = payloadDetail.items?.[0] ?? payloadDetail.discount?.[0] ?? payloadDetail.detail;
                    setFeedback(detailMessage ?? 'Revisá los datos de la venta.');
                    return;
                }
            }
            setFeedback('No pudimos registrar la venta, intentá nuevamente.');
        }
    };

    const products = productsQuery.data ?? [];
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
            <CustomerPicker value={selectedCustomer} onChange={setSelectedCustomer} />
            <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
                <section className="space-y-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex items-center justify-between">
                        <div>
                            <h2 className="text-xl font-semibold text-slate-900">Seleccioná productos</h2>
                            <p className="text-sm text-slate-500">Buscá por nombre o SKU y agregá al carrito.</p>
                        </div>
                    </div>
                    <input
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Buscar productos"
                        className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    />
                    <div className="max-h-80 overflow-y-auto rounded-2xl border border-slate-100">
                        {productsQuery.isLoading && <p className="p-4 text-sm text-slate-500">Buscando productos...</p>}
                        {!productsQuery.isLoading && products.length === 0 && (
                            <p className="p-4 text-sm text-slate-500">No encontramos productos que coincidan.</p>
                        )}
                        <ul className="divide-y divide-slate-100">
                            {products.map((product) => (
                                <li key={product.id} className="flex items-center justify-between px-4 py-3">
                                    <div>
                                        <p className="font-medium text-slate-900">{product.name}</p>
                                        <p className="text-xs text-slate-400">SKU {product.sku || '—'}</p>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <p className="text-sm font-semibold text-slate-600">{formatCurrency(Number(product.price))}</p>
                                        <button
                                            type="button"
                                            onClick={() => addProductToCart(product)}
                                            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                                        >
                                            Agregar
                                        </button>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    </div>
                </section>
                <section className="space-y-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-semibold text-slate-900">Detalle</h2>
                        {cart.length ? <p className="text-sm text-slate-500">{cart.length} productos</p> : null}
                    </div>
                    {cart.length === 0 ? (
                        <p className="rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-500">
                            Todavía no agregaste productos.
                        </p>
                    ) : (
                        <div className="space-y-3">
                            {cart.map((item) => (
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
                                </div>
                            ))}
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
                                min="0"
                                step="50"
                                value={discount}
                                onChange={(event) => setDiscount(event.target.value)}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
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
                        {feedback && <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">{feedback}</p>}
                        <button
                            type="button"
                            onClick={handleSubmit}
                            disabled={isSaving}
                            className="w-full rounded-full bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                            {isSaving ? 'Registrando venta...' : 'Confirmar venta'}
                        </button>
                    </div>
                </section>
            </div>
        </div>
    );
}

"use client";

import { useDeferredValue, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import {
    Plus, Trash2, Loader2, ShoppingCart, AlertCircle, ChevronDown
} from 'lucide-react';

import { createReplenishment } from '@/lib/api/replenishment';
import { listAccounts } from '@/lib/api/treasury';
import { useProducts } from '@/features/gestion/hooks';
import { todayDateString } from '@/lib/dates';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface LineItem {
    key: number;
    product_id: string;
    product_name: string;
    quantity: string;
    unit_cost: string;
}

let key = 0;
const newLine = (): LineItem => ({ key: ++key, product_id: '', product_name: '', quantity: '', unit_cost: '' });

function lineTotal(item: LineItem): number {
    const q = parseFloat(item.quantity);
    const c = parseFloat(item.unit_cost);
    if (!isNaN(q) && !isNaN(c)) return q * c;
    return 0;
}

function formatCurrency(n: number) {
    return n.toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function ReponerClient() {
    const router = useRouter();

    const [accountId, setAccountId] = useState('');
    const [supplierName, setSupplierName] = useState('');
    const [invoiceNumber, setInvoiceNumber] = useState('');
    const [occurredAt, setOccurredAt] = useState(() => todayDateString());
    const [notes, setNotes] = useState('');
    const [items, setItems] = useState<LineItem[]>([newLine()]);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [globalError, setGlobalError] = useState('');

    // Product search state per row
    const [rowSearch, setRowSearch] = useState<Record<number, string>>({});

    const accountsQuery = useQuery({ queryKey: ['treasury', 'accounts'], queryFn: listAccounts });
    const accounts = accountsQuery.data ?? [];

    const deferredSearch = useDeferredValue('');
    const productsQuery = useProducts(deferredSearch, true);
    const allProducts = useMemo(() => productsQuery.data ?? [], [productsQuery.data]);

    const mutation = useMutation({
        mutationFn: createReplenishment,
        onSuccess: (data) => {
            router.push(`/app/gestion/stock/compras/${data.id}`);
        },
        onError: (err: any) => {
            setGlobalError(err?.message ?? 'Error al guardar la reposición.');
        },
    });

    // --- helpers ---
    function setLine(key: number, patch: Partial<LineItem>) {
        setItems((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));
    }
    function removeLine(key: number) {
        setItems((prev) => prev.length > 1 ? prev.filter((l) => l.key !== key) : prev);
    }

    const filteredProducts = (search: string) => {
        const term = search.trim().toLowerCase();
        if (!term) return allProducts.slice(0, 30);
        return allProducts.filter(
            (p) => p.name.toLowerCase().includes(term) || (p.sku ?? '').toLowerCase().includes(term)
        ).slice(0, 30);
    };

    const grandTotal = items.reduce((acc, l) => acc + lineTotal(l), 0);

    function validate() {
        const errs: Record<string, string> = {};
        if (!accountId) errs.accountId = 'Seleccioná una cuenta.';
        if (!supplierName.trim()) errs.supplierName = 'El proveedor es requerido.';
        if (!occurredAt) errs.occurredAt = 'La fecha es requerida.';
        items.forEach((l, i) => {
            if (!l.product_id) errs[`item_${i}_product`] = 'Seleccioná un producto.';
            const q = parseFloat(l.quantity);
            if (isNaN(q) || q <= 0) errs[`item_${i}_qty`] = 'Cantidad inválida.';
            const c = parseFloat(l.unit_cost);
            if (isNaN(c) || c < 0) errs[`item_${i}_cost`] = 'Costo inválido.';
        });
        // Duplicate check
        const ids = items.map((l) => l.product_id).filter(Boolean);
        const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
        if (dupes.length > 0) errs.duplicates = 'Hay productos duplicados.';
        return errs;
    }

    function handleSubmit() {
        setGlobalError('');
        const errs = validate();
        setErrors(errs);
        if (Object.keys(errs).length > 0) return;

        mutation.mutate({
            account_id: accountId,
            supplier_name: supplierName.trim(),
            invoice_number: invoiceNumber.trim() || undefined,
            occurred_at: occurredAt,
            notes: notes.trim() || undefined,
            items: items.map((l) => ({
                product_id: l.product_id,
                quantity: parseFloat(l.quantity),
                unit_cost: parseFloat(l.unit_cost),
            })),
        });
    }

    return (
        <div className="max-w-3xl space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3">
                <div className="p-3 rounded-2xl bg-orange-100 text-orange-600">
                    <ShoppingCart className="h-6 w-6" />
                </div>
                <div>
                    <h1 className="text-xl font-bold text-slate-900">Nueva Reposición de Stock</h1>
                    <p className="text-sm text-slate-500">Registrá compras a proveedor con impacto en stock y finanzas</p>
                </div>
            </div>

            {/* Form card */}
            <div className="bg-white rounded-3xl border border-slate-200 shadow-sm p-6 space-y-5">
                {/* Row 1: Account + Date */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                            Cuenta de pago <span className="text-rose-500">*</span>
                        </label>
                        <select
                            value={accountId}
                            onChange={(e) => setAccountId(e.target.value)}
                            className={cn(
                                'w-full rounded-xl border text-sm px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-orange-400',
                                errors.accountId ? 'border-rose-400' : 'border-slate-300'
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
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                            Fecha de compra <span className="text-rose-500">*</span>
                        </label>
                        <input
                            type="date"
                            value={occurredAt}
                            onChange={(e) => setOccurredAt(e.target.value)}
                            className={cn(
                                'w-full rounded-xl border text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400',
                                errors.occurredAt ? 'border-rose-400' : 'border-slate-300'
                            )}
                        />
                        {errors.occurredAt && <p className="text-xs text-rose-600 mt-1">{errors.occurredAt}</p>}
                    </div>
                </div>

                {/* Row 2: Supplier + Invoice */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                            Proveedor <span className="text-rose-500">*</span>
                        </label>
                        <input
                            type="text"
                            value={supplierName}
                            onChange={(e) => setSupplierName(e.target.value)}
                            placeholder="Nombre del proveedor"
                            className={cn(
                                'w-full rounded-xl border text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400',
                                errors.supplierName ? 'border-rose-400' : 'border-slate-300'
                            )}
                        />
                        {errors.supplierName && <p className="text-xs text-rose-600 mt-1">{errors.supplierName}</p>}
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                            N° Factura / Remito
                        </label>
                        <input
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
                    <label className="block text-sm font-medium text-slate-700 mb-1">Notas</label>
                    <textarea
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        rows={2}
                        placeholder="Observaciones opcionales..."
                        className="w-full rounded-xl border border-slate-300 text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none"
                    />
                </div>
            </div>

            {/* Items table */}
            <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
                    <h2 className="font-semibold text-slate-900">Productos a reponer</h2>
                    <button
                        type="button"
                        onClick={() => setItems((prev) => [...prev, newLine()])}
                        className="inline-flex items-center gap-1.5 text-sm text-orange-600 font-medium hover:text-orange-700"
                    >
                        <Plus className="h-4 w-4" />
                        Agregar fila
                    </button>
                </div>

                {errors.duplicates && (
                    <p className="px-6 py-2 text-xs text-rose-600 bg-rose-50">{errors.duplicates}</p>
                )}

                <div className="divide-y divide-slate-100">
                    {items.map((line, i) => {
                        const search = rowSearch[line.key] ?? '';
                        const suggestions = filteredProducts(search);
                        const total = lineTotal(line);
                        return (
                            <div key={line.key} className="px-6 py-4 space-y-3">
                                <div className="flex items-center justify-between">
                                    <span className="text-xs font-semibold text-slate-500">Línea {i + 1}</span>
                                    {items.length > 1 && (
                                        <button
                                            type="button"
                                            onClick={() => removeLine(line.key)}
                                            className="text-slate-400 hover:text-rose-600"
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </button>
                                    )}
                                </div>

                                {/* Product selector */}
                                <div>
                                    <label className="block text-xs font-medium text-slate-600 mb-1">Producto</label>
                                    {line.product_id ? (
                                        <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl px-3 py-2">
                                            <span className="text-sm font-medium text-slate-900">{line.product_name}</span>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setLine(line.key, { product_id: '', product_name: '' });
                                                    setRowSearch((s) => ({ ...s, [line.key]: '' }));
                                                }}
                                                className="text-xs text-slate-400 hover:text-slate-700"
                                            >
                                                Cambiar
                                            </button>
                                        </div>
                                    ) : (
                                        <div className="relative">
                                            <input
                                                type="text"
                                                value={search}
                                                onChange={(e) => setRowSearch((s) => ({ ...s, [line.key]: e.target.value }))}
                                                placeholder="Buscar producto por nombre o SKU..."
                                                className={cn(
                                                    'w-full rounded-xl border text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400',
                                                    errors[`item_${i}_product`] ? 'border-rose-400' : 'border-slate-300'
                                                )}
                                            />
                                            {suggestions.length > 0 && (
                                                <ul className="absolute z-10 top-full mt-1 w-full bg-white border border-slate-200 rounded-xl shadow-lg max-h-48 overflow-y-auto">
                                                    {suggestions.map((p: any) => (
                                                        <li
                                                            key={p.id}
                                                            onClick={() => {
                                                                setLine(line.key, { product_id: p.id, product_name: p.name });
                                                                setRowSearch((s) => ({ ...s, [line.key]: '' }));
                                                            }}
                                                            className="px-3 py-2 hover:bg-slate-50 cursor-pointer text-sm"
                                                        >
                                                            <span className="font-medium text-slate-900">{p.name}</span>
                                                            {p.sku && <span className="ml-2 text-slate-400 text-xs font-mono">{p.sku}</span>}
                                                        </li>
                                                    ))}
                                                </ul>
                                            )}
                                        </div>
                                    )}
                                    {errors[`item_${i}_product`] && (
                                        <p className="text-xs text-rose-600 mt-1">{errors[`item_${i}_product`]}</p>
                                    )}
                                </div>

                                {/* Qty + Cost + Total */}
                                <div className="grid grid-cols-3 gap-3">
                                    <div>
                                        <label className="block text-xs font-medium text-slate-600 mb-1">Cantidad</label>
                                        <input
                                            type="number"
                                            min="0.01"
                                            step="0.01"
                                            value={line.quantity}
                                            onChange={(e) => setLine(line.key, { quantity: e.target.value })}
                                            className={cn(
                                                'w-full rounded-xl border text-sm px-3 py-2 font-mono focus:outline-none focus:ring-2 focus:ring-orange-400',
                                                errors[`item_${i}_qty`] ? 'border-rose-400' : 'border-slate-300'
                                            )}
                                            placeholder="0"
                                        />
                                        {errors[`item_${i}_qty`] && (
                                            <p className="text-xs text-rose-600 mt-1">{errors[`item_${i}_qty`]}</p>
                                        )}
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-slate-600 mb-1">Costo unit.</label>
                                        <input
                                            type="number"
                                            min="0"
                                            step="0.01"
                                            value={line.unit_cost}
                                            onChange={(e) => setLine(line.key, { unit_cost: e.target.value })}
                                            className={cn(
                                                'w-full rounded-xl border text-sm px-3 py-2 font-mono focus:outline-none focus:ring-2 focus:ring-orange-400',
                                                errors[`item_${i}_cost`] ? 'border-rose-400' : 'border-slate-300'
                                            )}
                                            placeholder="0.00"
                                        />
                                        {errors[`item_${i}_cost`] && (
                                            <p className="text-xs text-rose-600 mt-1">{errors[`item_${i}_cost`]}</p>
                                        )}
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-slate-600 mb-1">Total línea</label>
                                        <div className="w-full rounded-xl bg-slate-50 border border-slate-200 text-sm px-3 py-2 font-mono font-semibold text-slate-700">
                                            ${formatCurrency(total)}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* Grand total */}
                <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-700">Total de la reposición</span>
                    <span className="text-lg font-bold font-mono text-orange-600">${formatCurrency(grandTotal)}</span>
                </div>
            </div>

            {/* Error */}
            {globalError && (
                <div className="flex items-center gap-2 p-4 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700">
                    <AlertCircle className="h-5 w-5 shrink-0" />
                    {globalError}
                </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-3 pb-8">
                <Button variant="outline" onClick={() => router.back()} disabled={mutation.isPending}>
                    Cancelar
                </Button>
                <Button
                    onClick={handleSubmit}
                    disabled={mutation.isPending}
                    className="bg-orange-500 hover:bg-orange-600 text-white"
                >
                    {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Registrar reposición
                </Button>
            </div>
        </div>
    );
}

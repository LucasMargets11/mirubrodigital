'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import { ToastBubble, type ToastTone } from '@/components/app/toast';
import { Drawer } from '@/components/ui/drawer';
import type { CashPaymentMethod } from '@/features/cash/types';
import { useCreateSaleFromOrder, useOrderCheckout, usePayOrder } from '@/features/orders/hooks';
import type { Order, PayOrderPayload } from '@/features/orders/types';
import { ApiError } from '@/lib/api/client';

const DEFAULT_METHOD: CashPaymentMethod = 'cash';

type PaymentRow = {
    id: string;
    method: CashPaymentMethod;
    amount: string;
    reference: string;
};

type OrderCheckoutDrawerProps = {
    order: Order | null;
    open: boolean;
    onClose: () => void;
    onPaid: (order: Order) => void;
};

function buildRow(method: CashPaymentMethod, amount = '', reference = ''): PaymentRow {
    const id = typeof crypto !== 'undefined' && crypto?.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
    return { id, method, amount, reference };
}

function formatCurrency(value: string | number | undefined) {
    const numeric = typeof value === 'string' ? Number(value) : Number(value ?? 0);
    if (Number.isNaN(numeric)) {
        return '$0';
    }
    return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 2 }).format(numeric);
}

function parseApiError(error: unknown) {
    if (error instanceof ApiError) {
        if (typeof error.payload === 'object' && error.payload && 'detail' in (error.payload as Record<string, unknown>)) {
            return String((error.payload as { detail?: string }).detail);
        }
        return error.message;
    }
    if (error instanceof Error) {
        return error.message;
    }
    return 'No pudimos completar la acción.';
}

export function OrderCheckoutDrawer({ order, open, onClose, onPaid }: OrderCheckoutDrawerProps) {
    const orderId = order?.id ?? null;
    const checkoutQuery = useOrderCheckout(orderId, { enabled: open && Boolean(orderId) });
    const createSaleMutation = useCreateSaleFromOrder();
    const payMutation = usePayOrder();
    const [rows, setRows] = useState<PaymentRow[]>([buildRow(DEFAULT_METHOD)]);
    const [toast, setToast] = useState<{ message: string; tone: ToastTone } | null>(null);
    const bootstrapRef = useRef<string | null>(null);
    const initializedRowsRef = useRef<string | null>(null);
    const firstAmountRef = useRef<HTMLInputElement | null>(null);

    const checkoutData = checkoutQuery.data;
    const summaryOrder = checkoutData?.order ?? order;
    const items = checkoutData?.order.items ?? order?.items ?? [];
    const totalBalance = Number(checkoutData?.totals.balance ?? order?.total_amount ?? 0);
    const paidTotal = checkoutData?.totals.paid_total ?? '0.00';
    const paymentOptions = checkoutData?.payment_methods ?? [
        { value: 'cash', label: 'Efectivo' },
        { value: 'debit', label: 'Débito' },
        { value: 'credit', label: 'Crédito' },
        { value: 'transfer', label: 'Transferencia' },
        { value: 'wallet', label: 'Billetera' },
    ];

    useEffect(() => {
        if (!open || !orderId) {
            return;
        }
        if (order?.sale_id) {
            return;
        }
        if (bootstrapRef.current === orderId) {
            return;
        }
        bootstrapRef.current = orderId;
        createSaleMutation.mutate({ orderId, payload: { payment_method: DEFAULT_METHOD } });
    }, [createSaleMutation, open, order?.sale_id, orderId]);

    useEffect(() => {
        if (!open || !orderId || !checkoutData) {
            return;
        }
        if (initializedRowsRef.current === orderId) {
            return;
        }
        initializedRowsRef.current = orderId;
        const defaultAmount = checkoutData.totals.balance ?? checkoutData.totals.sale_total;
        setRows([buildRow(DEFAULT_METHOD, defaultAmount, '')]);
    }, [checkoutData, open, orderId]);

    useEffect(() => {
        if (!open) {
            return;
        }
        const timer = setTimeout(() => {
            firstAmountRef.current?.focus();
        }, 10);
        return () => clearTimeout(timer);
    }, [open, checkoutData?.totals.balance]);

    const totals = useMemo(() => {
        const rawEntered = rows.reduce((acc, row) => acc + (Number(row.amount) || 0), 0);
        const remaining = Number((totalBalance - rawEntered).toFixed(2));
        return {
            entered: rawEntered,
            remaining,
            isExact: Math.abs(remaining) < 0.01,
        };
    }, [rows, totalBalance]);

    const isPaid = summaryOrder?.status === 'paid';
    const disableSubmit =
        !orderId ||
        !checkoutData ||
        isPaid ||
        rows.length === 0 ||
        rows.some((row) => !row.amount || Number(row.amount) <= 0) ||
        !totals.isExact ||
        payMutation.isPending;

    const handleRowChange = (rowId: string, next: Partial<PaymentRow>) => {
        setRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, ...next } : row)));
    };

    const handleAddRow = () => {
        setRows((prev) => [...prev, buildRow(DEFAULT_METHOD)]);
    };

    const handleRemoveRow = (rowId: string) => {
        setRows((prev) => (prev.length === 1 ? prev : prev.filter((row) => row.id !== rowId)));
    };

    const handleExactPayment = () => {
        setRows([buildRow(DEFAULT_METHOD, checkoutData?.totals.balance ?? String(totalBalance), '')]);
    };

    const handleSplitInTwo = () => {
        const half = Number((totalBalance / 2).toFixed(2));
        const remainder = Number((totalBalance - half).toFixed(2));
        setRows([
            buildRow('cash', String(half), ''),
            buildRow('credit', String(remainder), ''),
        ]);
    };

    const handleSubmit = async () => {
        if (!orderId) {
            return;
        }
        try {
            const payload = {
                payments: rows.map((row) => ({
                    method: row.method,
                    amount: Number(row.amount),
                    reference: row.reference,
                })),
            } satisfies PayOrderPayload;
            const updated = await payMutation.mutateAsync({ orderId, payload });
            onPaid(updated);
            setRows([buildRow(DEFAULT_METHOD)]);
            onClose();
        } catch (error) {
            setToast({ message: parseApiError(error), tone: 'error' });
        }
    };

    const handleClose = () => {
        setRows([buildRow(DEFAULT_METHOD)]);
        onClose();
    };

    const salePayments = checkoutData?.sale?.payments ?? [];

    return (
        <Drawer open={open} onClose={handleClose} title="Cobrar orden" widthClassName="max-w-2xl">
            {!order ? (
                <p className="text-sm text-slate-500">Seleccioná una orden activa para continuar.</p>
            ) : (
                <div className="space-y-6">
                    <section className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
                            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Orden</span>
                            <span className="text-base font-semibold text-slate-900">#{order.number}</span>
                            {summaryOrder?.table_name ? <span>Mesa {summaryOrder.table_name}</span> : null}
                            {isPaid ? (
                                <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">Pagada</span>
                            ) : null}
                        </div>
                        <div className="mt-4 grid gap-2 text-sm text-slate-700">
                            <div className="flex items-center justify-between">
                                <span>Total orden</span>
                                <span className="text-lg font-semibold text-slate-900">{formatCurrency(summaryOrder?.total_amount ?? checkoutData?.totals.sale_total)}</span>
                            </div>
                            <div className="flex items-center justify-between text-slate-500">
                                <span>Total pagado</span>
                                <span>{formatCurrency(paidTotal)}</span>
                            </div>
                        </div>
                    </section>

                    <section className="rounded-2xl border border-slate-100 p-4">
                        <header className="mb-3 flex items-center justify-between">
                            <div>
                                <p className="text-xs uppercase tracking-wide text-slate-400">Detalle</p>
                                <h3 className="text-sm font-semibold text-slate-900">Items consumidos</h3>
                            </div>
                            <span className="text-xs text-slate-400">{items.length} ítems</span>
                        </header>
                        <ul className="space-y-2 text-sm text-slate-700">
                            {items.map((item) => (
                                <li key={item.id} className="flex items-center justify-between">
                                    <span>
                                        {Number(item.quantity).toLocaleString('es-AR', { maximumFractionDigits: 2 })} × {item.name}
                                    </span>
                                    <span className="font-medium text-slate-900">{formatCurrency(item.total_price)}</span>
                                </li>
                            ))}
                        </ul>
                    </section>

                    {salePayments.length ? (
                        <section className="rounded-2xl border border-slate-100 p-4">
                            <p className="text-xs uppercase tracking-wide text-slate-400">Pagos registrados</p>
                            <ul className="mt-3 space-y-2 text-sm text-slate-700">
                                {salePayments.map((payment) => (
                                    <li key={payment.id} className="flex items-center justify-between">
                                        <span>
                                            {payment.method_label ?? payment.method}
                                            {payment.reference ? <span className="text-xs text-slate-400"> · {payment.reference}</span> : null}
                                        </span>
                                        <span className="font-medium text-slate-900">{formatCurrency(payment.amount)}</span>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    ) : null}

                    <section className="space-y-4 rounded-2xl border border-slate-200 p-4">
                        <header className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                                <p className="text-xs uppercase tracking-wide text-slate-400">Pagos</p>
                                <h3 className="text-base font-semibold text-slate-900">Registrar cobro</h3>
                            </div>
                            <div className="flex gap-2 text-xs">
                                <button
                                    type="button"
                                    onClick={handleExactPayment}
                                    className="rounded-full border border-slate-300 px-3 py-1 font-semibold text-slate-600 transition hover:border-slate-900 hover:text-slate-900"
                                >
                                    Pago exacto
                                </button>
                                <button
                                    type="button"
                                    onClick={handleSplitInTwo}
                                    className="rounded-full border border-slate-300 px-3 py-1 font-semibold text-slate-600 transition hover:border-slate-900 hover:text-slate-900"
                                >
                                    Dividir en 2
                                </button>
                            </div>
                        </header>
                        <div className="space-y-3">
                            {rows.map((row, index) => (
                                <div key={row.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                                    <div className="flex flex-wrap gap-3">
                                        <label className="flex flex-1 flex-col text-xs font-semibold text-slate-500">
                                            Método
                                            <select
                                                value={row.method}
                                                onChange={(event) => handleRowChange(row.id, { method: event.target.value as CashPaymentMethod })}
                                                className="mt-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
                                            >
                                                {paymentOptions.map((option) => (
                                                    <option key={option.value} value={option.value}>
                                                        {option.label}
                                                    </option>
                                                ))}
                                            </select>
                                        </label>
                                        <label className="flex flex-1 flex-col text-xs font-semibold text-slate-500">
                                            Monto
                                            <input
                                                ref={index === 0 ? firstAmountRef : undefined}
                                                type="number"
                                                step="0.01"
                                                min="0"
                                                value={row.amount}
                                                onChange={(event) => handleRowChange(row.id, { amount: event.target.value })}
                                                className="mt-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
                                                placeholder="0.00"
                                            />
                                        </label>
                                        <label className="flex flex-1 flex-col text-xs font-semibold text-slate-500">
                                            Referencia (opcional)
                                            <input
                                                type="text"
                                                value={row.reference}
                                                onChange={(event) => handleRowChange(row.id, { reference: event.target.value })}
                                                className="mt-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
                                                placeholder="Ticket, lote, etc."
                                            />
                                        </label>
                                        {rows.length > 1 ? (
                                            <button
                                                type="button"
                                                onClick={() => handleRemoveRow(row.id)}
                                                className="rounded-full border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-500 transition hover:border-rose-300 hover:text-rose-600"
                                            >
                                                Quitar
                                            </button>
                                        ) : null}
                                    </div>
                                </div>
                            ))}
                        </div>
                        <button
                            type="button"
                            onClick={handleAddRow}
                            className="rounded-full border border-dashed border-slate-300 px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-slate-900 hover:text-slate-900"
                        >
                            + Agregar pago
                        </button>
                    </section>

                    <section className="rounded-2xl border border-slate-100 bg-white p-4 text-sm text-slate-600">
                        <div className="flex items-center justify-between">
                            <span>Total ingresado</span>
                            <span className="text-base font-semibold text-slate-900">{formatCurrency(totals.entered)}</span>
                        </div>
                        <div className="mt-1 flex items-center justify-between">
                            <span>Saldo restante</span>
                            <span className={totals.isExact ? 'text-emerald-600 font-semibold' : 'text-rose-600 font-semibold'}>
                                {formatCurrency(totals.remaining)}
                            </span>
                        </div>
                        {isPaid ? (
                            <p className="mt-2 text-xs text-emerald-600">Esta orden ya figura como pagada.</p>
                        ) : null}
                    </section>

                    <div className="flex flex-wrap gap-3">
                        <button
                            type="button"
                            disabled={disableSubmit}
                            onClick={handleSubmit}
                            className="flex-1 rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                            {payMutation.isPending ? 'Confirmando…' : 'Confirmar cobro'}
                        </button>
                        <button
                            type="button"
                            onClick={handleClose}
                            className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-slate-900 hover:text-slate-900"
                        >
                            Cancelar
                        </button>
                    </div>
                </div>
            )}
            {toast && <ToastBubble message={toast.message} tone={toast.tone} />}
        </Drawer>
    );
}

"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';

import { Modal } from '@/components/ui/modal';
import { ApiError } from '@/lib/api/client';

import { useCreateCashPayment } from '../hooks';
import { formatCurrency, getSaleBalanceValue, paymentMethodOptions } from '../utils';
import type { CashPaymentMethod, SalesWithBalance } from '../types';

type PaymentInput = {
    id: string;
    method: CashPaymentMethod;
    amount: string;
    reference: string;
};

type CollectPaymentModalProps = {
    open: boolean;
    onClose: () => void;
    sale: SalesWithBalance | null;
    sessionId?: string;
    canManage: boolean;
};

const generateId = () =>
    typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2);

const createPaymentInput = (overrides?: Partial<Omit<PaymentInput, 'id'>>): PaymentInput => ({
    id: generateId(),
    method: overrides?.method ?? 'cash',
    amount: overrides?.amount ?? '0',
    reference: overrides?.reference ?? '',
});

export function CollectPaymentModal({ open, onClose, sale, sessionId, canManage }: CollectPaymentModalProps) {
    const mutation = useCreateCashPayment();
    const [payments, setPayments] = useState<PaymentInput[]>([]);
    const [error, setError] = useState('');
    const lastMethodRef = useRef<CashPaymentMethod>('cash');

    const saleBalance = sale ? Math.max(getSaleBalanceValue(sale), 0) : 0;

    const enteredTotal = useMemo(() => {
        return payments.reduce((sum, payment) => sum + Number(payment.amount || 0), 0);
    }, [payments]);

    const isZeroTotal = enteredTotal <= 0.009;
    const isOverBalance = enteredTotal - saleBalance > 0.009;
    const disableSubmit = mutation.isLoading || !canManage || isZeroTotal || isOverBalance;
    const inlineWarning = isOverBalance ? 'Los pagos superan el saldo pendiente.' : '';
    const remainingAfterPayments = Math.max(saleBalance - enteredTotal, 0);
    const canCollectAll = saleBalance > 0;

    useEffect(() => {
        if (!open) {
            setPayments([]);
            setError('');
            return;
        }

        if (!sale) {
            return;
        }

        const initialAmount = saleBalance > 0 ? saleBalance.toString() : '';
        setPayments([createPaymentInput({ method: lastMethodRef.current, amount: initialAmount })]);
        setError('');
    }, [open, sale, saleBalance]);

    if (!sale) {
        return null;
    }

    const handleChange = (id: string, key: keyof PaymentInput, value: string) => {
        setPayments((prev) => prev.map((entry) => (entry.id === id ? { ...entry, [key]: value } : entry)));
    };

    const handleRemove = (id: string) => {
        if (payments.length === 1) return;
        setPayments((prev) => prev.filter((entry) => entry.id !== id));
    };

    const handleAddRow = () => {
        setPayments((prev) => {
            const fallbackMethod = prev[prev.length - 1]?.method ?? lastMethodRef.current;
            return [...prev, createPaymentInput({ method: fallbackMethod, amount: '0' })];
        });
    };

    const handleCollectAll = () => {
        if (saleBalance <= 0) {
            return;
        }
        setPayments((prev) => {
            if (prev.length === 0) {
                return [createPaymentInput({ method: lastMethodRef.current, amount: saleBalance.toString() })];
            }
            return prev.map((entry, index) =>
                index === 0 ? { ...entry, amount: saleBalance.toString() } : { ...entry, amount: '0' }
            );
        });
    };

    const handleCompleteRemaining = (id: string) => {
        setPayments((prev) => {
            const index = prev.findIndex((entry) => entry.id === id);
            if (index === -1) {
                return prev;
            }
            const previousSum = prev.slice(0, index).reduce((sum, entry) => sum + Number(entry.amount || 0), 0);
            const remaining = Math.max(saleBalance - previousSum, 0);
            return prev.map((entry, idx) => (idx === index ? { ...entry, amount: remaining.toString() } : entry));
        });
    };

    const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError('');

        if (!canManage) {
            setError('No tenés permiso para registrar cobros.');
            return;
        }

        if (!sessionId) {
            setError('Necesitás abrir la caja antes de cobrar.');
            return;
        }

        const validEntries = payments.filter((payment) => Number(payment.amount) > 0);
        if (validEntries.length === 0 || isZeroTotal) {
            setError('Ingresá al menos un pago.');
            return;
        }

        if (isOverBalance) {
            setError('Los pagos superan el saldo pendiente.');
            return;
        }

        try {
            for (const entry of validEntries) {
                await mutation.mutateAsync({
                    sale_id: sale.id,
                    session_id: sessionId,
                    method: entry.method,
                    amount: Number(entry.amount),
                    reference: entry.reference,
                });
            }
            lastMethodRef.current = validEntries[0].method;
            onClose();
        } catch (err) {
            const apiError = err as ApiError;
            setError(apiError.message ?? 'No pudimos guardar los pagos.');
        }
    };

    return (
        <Modal open={open} title={`Cobrar venta #${sale.number}`} onClose={onClose}>
            <form className="space-y-4" onSubmit={handleSubmit}>
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div className="rounded-2xl bg-slate-50 p-4 text-sm">
                        <p className="text-slate-500">Total venta</p>
                        <p className="text-xl font-semibold text-slate-900">{formatCurrency(sale.total)}</p>
                        <div className="mt-2 flex flex-wrap gap-4 text-xs uppercase tracking-wide text-slate-500">
                            <span>Pagado {formatCurrency(sale.paid_total ?? '0')}</span>
                            <span>Saldo {formatCurrency(saleBalance)}</span>
                        </div>
                    </div>
                    {canCollectAll ? (
                        <button
                            type="button"
                            onClick={handleCollectAll}
                            className="rounded-full border border-emerald-200 px-4 py-2 text-sm font-semibold text-emerald-700 hover:border-emerald-500 hover:text-emerald-900"
                        >
                            Cobrar todo
                        </button>
                    ) : null}
                </div>
                {payments.map((payment, index) => {
                    const previousSum = payments.slice(0, index).reduce((sum, entry) => sum + Number(entry.amount || 0), 0);
                    const remainingForSplit = Math.max(saleBalance - previousSum, 0);

                    return (
                        <div key={payment.id} className="rounded-2xl border border-slate-100 p-4">
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Pago {index + 1}</p>
                            <div className="mt-3 grid gap-3 md:grid-cols-2">
                                <label className="block text-sm text-slate-600">
                                    Medio
                                    <select
                                        value={payment.method}
                                        onChange={(event) => handleChange(payment.id, 'method', event.target.value as CashPaymentMethod)}
                                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                                    >
                                        {paymentMethodOptions.map((option) => (
                                            <option key={option.value} value={option.value}>
                                                {option.label}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                                <label className="block text-sm text-slate-600">
                                    Monto
                                    <input
                                        type="number"
                                        min="0"
                                        step="0.01"
                                        value={payment.amount}
                                        onChange={(event) => handleChange(payment.id, 'amount', event.target.value)}
                                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                                    />
                                </label>
                                <label className="md:col-span-2 block text-sm text-slate-600">
                                    Referencia
                                    <input
                                        type="text"
                                        value={payment.reference}
                                        onChange={(event) => handleChange(payment.id, 'reference', event.target.value)}
                                        placeholder="# de comprobante, banco, etc."
                                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                                    />
                                </label>
                            </div>
                            {payments.length > 1 ? (
                                <button
                                    type="button"
                                    onClick={() => handleRemove(payment.id)}
                                    className="mt-3 text-xs font-semibold text-rose-600"
                                >
                                    Eliminar pago
                                </button>
                            ) : null}
                            {payments.length > 1 && index === payments.length - 1 ? (
                                <button
                                    type="button"
                                    onClick={() => handleCompleteRemaining(payment.id)}
                                    disabled={remainingForSplit <= 0}
                                    className="mt-2 text-xs font-semibold text-emerald-600 disabled:text-slate-400"
                                >
                                    Completar resto
                                </button>
                            ) : null}
                        </div>
                    );
                })}
                <button
                    type="button"
                    onClick={handleAddRow}
                    className="text-sm font-semibold text-slate-600 hover:text-slate-900"
                >
                    + Agregar pago
                </button>
                <div className="rounded-2xl bg-slate-50 p-4 text-sm">
                    <div className="flex items-center justify-between">
                        <span className="text-slate-500">Suma de pagos</span>
                        <span className="font-semibold text-slate-900">{formatCurrency(enteredTotal)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                        <span className="text-slate-500">Saldo luego de cobrar</span>
                        <span className="font-semibold text-slate-900">{formatCurrency(remainingAfterPayments)}</span>
                    </div>
                </div>
                {inlineWarning ? <p className="text-sm text-rose-600">{inlineWarning}</p> : null}
                {error ? <p className="text-sm text-rose-600">{error}</p> : null}
                <div className="flex items-center justify-end gap-2 pt-2">
                    <button
                        type="button"
                        onClick={onClose}
                        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                    >
                        Cancelar
                    </button>
                    <button
                        type="submit"
                        disabled={disableSubmit}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                    >
                        {mutation.isLoading ? 'Registrando...' : 'Registrar cobro'}
                    </button>
                </div>
            </form>
        </Modal>
    );
}

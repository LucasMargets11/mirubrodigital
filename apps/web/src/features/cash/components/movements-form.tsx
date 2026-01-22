"use client";

import { FormEvent, useState } from 'react';

import { ApiError } from '@/lib/api/client';

import { useCreateCashMovement } from '../hooks';
import {
    movementCategoryOptions,
    movementTypeOptions,
    paymentMethodOptions,
    formatCurrency,
} from '../utils';

import type { CashMovementCategory, CashMovementType, CashPaymentMethod } from '../types';

type MovementsFormProps = {
    sessionId?: string;
    canManage: boolean;
};

export function MovementsForm({ sessionId, canManage }: MovementsFormProps) {
    const mutation = useCreateCashMovement();
    const [movementType, setMovementType] = useState<CashMovementType>('out');
    const [category, setCategory] = useState<CashMovementCategory>('expense');
    const [method, setMethod] = useState<CashPaymentMethod>('cash');
    const [amount, setAmount] = useState('');
    const [note, setNote] = useState('');
    const [error, setError] = useState('');

    const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError('');

        if (!canManage) {
            setError('Sin permisos para registrar movimientos.');
            return;
        }

        if (!sessionId) {
            setError('Abrí una caja para registrar movimientos.');
            return;
        }

        const numericAmount = Number(amount);
        if (!numericAmount || numericAmount <= 0) {
            setError('Ingresá un monto válido.');
            return;
        }

        try {
            await mutation.mutateAsync({
                session_id: sessionId,
                movement_type: movementType,
                category,
                method,
                amount: numericAmount,
                note,
            });
            setAmount('');
            setNote('');
        } catch (err) {
            const apiError = err as ApiError;
            setError(apiError.message ?? 'No pudimos registrar el movimiento.');
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Movimientos</p>
                <h3 className="text-xl font-semibold text-slate-900">Registrar ingreso/egreso</h3>
            </header>
            {!sessionId ? (
                <p className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700">
                    Abrí una sesión de caja para habilitar los movimientos.
                </p>
            ) : null}
            <div className="grid gap-4 md:grid-cols-2">
                <label className="block text-sm text-slate-600">
                    Tipo
                    <select
                        value={movementType}
                        onChange={(event) => setMovementType(event.target.value as CashMovementType)}
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                    >
                        {movementTypeOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="block text-sm text-slate-600">
                    Categoría
                    <select
                        value={category}
                        onChange={(event) => setCategory(event.target.value as CashMovementCategory)}
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                    >
                        {movementCategoryOptions.map((option) => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="block text-sm text-slate-600">
                    Medio de pago
                    <select
                        value={method}
                        onChange={(event) => setMethod(event.target.value as CashPaymentMethod)}
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
                        value={amount}
                        onChange={(event) => setAmount(event.target.value)}
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                    />
                    <span className="text-xs text-slate-400">{amount ? formatCurrency(amount) : 'Ingresa el valor exacto.'}</span>
                </label>
            </div>
            <label className="block text-sm text-slate-600">
                Nota
                <textarea
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                    rows={3}
                />
            </label>
            {error ? <p className="text-sm text-rose-600">{error}</p> : null}
            <div className="flex items-center justify-end">
                <button
                    type="submit"
                    disabled={mutation.isLoading || !canManage}
                    className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                >
                    {mutation.isLoading ? 'Guardando...' : 'Registrar movimiento'}
                </button>
            </div>
        </form>
    );
}

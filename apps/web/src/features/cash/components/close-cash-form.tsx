"use client";

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { ApiError } from '@/lib/api/client';

import { useCloseCashSession } from '../hooks';
import { formatCurrency } from '../utils';
import type { CashSession } from '../types';

type CloseCashFormProps = {
    session: CashSession | null | undefined;
    canManage: boolean;
};

export function CloseCashForm({ session, canManage }: CloseCashFormProps) {
    const router = useRouter();
    const mutation = useCloseCashSession();
    const [countedCash, setCountedCash] = useState('');
    const [note, setNote] = useState('');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    useEffect(() => {
        setError('');
        setSuccess('');
    }, [session?.id]);

    if (!session) {
        return (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
                Necesitás tener una caja abierta para registrar el cierre.
            </div>
        );
    }

    const totals = session.totals;
    const expectedCash = Number(totals?.cash_expected_total ?? session.expected_cash_total ?? '0');
    const totalCollected = Number(totals?.payments_total ?? '0');
    const countedValue = Number(countedCash || 0);
    const difference = countedValue - expectedCash;

    const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError('');
        setSuccess('');

        if (!canManage) {
            setError('Tu rol no puede cerrar la caja.');
            return;
        }

        if (!session) {
            setError('No encontramos la sesión a cerrar.');
            return;
        }

        if (countedValue < 0) {
            setError('Ingresá un monto mayor o igual a cero.');
            return;
        }

        try {
            await mutation.mutateAsync({
                sessionId: session.id,
                payload: {
                    closing_cash_counted: countedValue,
                    note,
                },
            });
            setSuccess('Caja cerrada correctamente.');
            setCountedCash('');
            setNote('');
            router.push('/app/operacion/caja');
        } catch (err) {
            const apiError = err as ApiError;
            setError(apiError.message ?? 'No pudimos cerrar la caja.');
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Cierre</p>
                <h3 className="text-xl font-semibold text-slate-900">Arqueo y cierre de caja</h3>
            </header>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Efectivo esperado</p>
                    <p className="text-2xl font-semibold text-slate-900">{formatCurrency(expectedCash)}</p>
                    <p className="text-xs text-slate-500">Saldo inicial + cobros en efectivo + movimientos.</p>
                </div>
                <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Total cobrado</p>
                    <p className="text-2xl font-semibold text-slate-900">{formatCurrency(totalCollected)}</p>
                    <p className="text-xs text-slate-500">Incluye todos los medios registrados.</p>
                </div>
                <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Contado</p>
                    <p className="text-2xl font-semibold text-slate-900">{formatCurrency(countedValue)}</p>
                    <p className="text-xs text-slate-500">Ingresá el efectivo real.</p>
                </div>
                <div className="rounded-2xl bg-slate-50 p-4">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Diferencia</p>
                    <p className={`text-2xl font-semibold ${difference === 0 ? 'text-slate-900' : difference > 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                        {formatCurrency(difference)}
                    </p>
                    <p className="text-xs text-slate-500">Se registrará en el cierre.</p>
                </div>
            </div>
            <label className="block text-sm text-slate-600">
                Efectivo contado
                <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={countedCash}
                    onChange={(event) => setCountedCash(event.target.value)}
                    className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                    required
                />
            </label>
            <label className="block text-sm text-slate-600">
                Nota
                <textarea
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    placeholder="Explicá diferencias, retiros, etc."
                    className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                    rows={4}
                />
            </label>
            {error ? <p className="text-sm text-rose-600">{error}</p> : null}
            {success ? <p className="text-sm text-emerald-600">{success}</p> : null}
            <div className="flex items-center justify-end">
                <button
                    type="submit"
                    disabled={mutation.isLoading || !canManage}
                    className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                >
                    {mutation.isLoading ? 'Cerrando...' : 'Cerrar caja'}
                </button>
            </div>
        </form>
    );
}

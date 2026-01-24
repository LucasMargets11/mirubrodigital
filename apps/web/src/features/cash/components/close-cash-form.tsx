"use client";

import { FormEvent, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

import { ApiError } from '@/lib/api/client';

import { useCloseCashSession } from '../hooks';
import { formatCurrency, toNumber } from '../utils';
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
    const [collectPending, setCollectPending] = useState(false);
    const timeoutRef = useRef<NodeJS.Timeout | null>(null);

    const pendingCount = session?.totals?.pending_sales_count ?? 0;
    const pendingTotal = session?.totals?.pending_sales_total ?? '0';
    const hasPending = pendingCount > 0;

    useEffect(() => {
        setError('');
        setSuccess('');
        if (!session) {
            setCollectPending(false);
            return;
        }
        setCollectPending(pendingCount > 0);
    }, [session?.id, pendingCount]);

    useEffect(() => {
        return () => {
            if (timeoutRef.current) {
                clearTimeout(timeoutRef.current);
            }
        };
    }, []);

    if (!session) {
        return (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
                Necesitás tener una caja abierta para registrar el cierre.
            </div>
        );
    }

    const totals = session.totals;
    const expectedCash = toNumber(totals?.cash_expected_total ?? session.expected_cash_total ?? '0');
    const totalCollected = toNumber(totals?.payments_total ?? '0');
    const countedValue = toNumber(countedCash || 0);
    const pendingTotalValue = toNumber(pendingTotal);
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
            const response = await mutation.mutateAsync({
                sessionId: session.id,
                payload: {
                    closing_cash_counted: countedValue,
                    note,
                    collect_pending_sales: Boolean(collectPending && hasPending),
                },
            });
            const summary = response.collection_summary;
            const successMessage = summary && summary.collected_count > 0
                ? `Cierre realizado. Se cobraron ${summary.collected_count} ventas (${formatCurrency(summary.total_collected)}).`
                : 'Cierre realizado.';
            setSuccess(successMessage);
            setError(summary && summary.errors.length ? summary.errors.join(' · ') : '');
            setCountedCash('');
            setNote('');
            if (timeoutRef.current) {
                clearTimeout(timeoutRef.current);
            }
            timeoutRef.current = setTimeout(() => {
                router.push('/app/operacion/caja');
            }, 1200);
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
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                <label className="flex items-start gap-3">
                    <input
                        type="checkbox"
                        className="mt-1 h-5 w-5 rounded border-slate-300"
                        checked={collectPending && hasPending}
                        disabled={!canManage || !hasPending || mutation.isLoading}
                        onChange={(event) => setCollectPending(event.target.checked)}
                    />
                    <div>
                        <p className="font-semibold">Cobrar ventas pendientes al cerrar</p>
                        <p className="text-xs text-slate-500">
                            {hasPending ? `Pendientes: ${pendingCount} ventas — ${formatCurrency(pendingTotalValue)}` : 'No hay ventas pendientes en esta sesión.'}
                        </p>
                    </div>
                </label>
            </div>
            {error ? (
                <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">{error}</p>
            ) : null}
            {success ? (
                <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">{success}</p>
            ) : null}
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

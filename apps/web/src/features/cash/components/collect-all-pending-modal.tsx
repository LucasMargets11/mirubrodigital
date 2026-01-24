"use client";

import { useState } from 'react';

import { Modal } from '@/components/ui/modal';
import { ApiError } from '@/lib/api/client';

import { useCollectPendingSales } from '../hooks';
import { formatCurrency } from '../utils';
import type { CashSession, CollectPendingSalesResponse } from '../types';

type CollectAllPendingModalProps = {
    open: boolean;
    onClose: () => void;
    session: CashSession | null | undefined;
    canCollect: boolean;
};

export function CollectAllPendingModal({ open, onClose, session, canCollect }: CollectAllPendingModalProps) {
    const mutation = useCollectPendingSales();
    const [error, setError] = useState('');
    const [result, setResult] = useState<CollectPendingSalesResponse | null>(null);

    const pendingCount = session?.totals?.pending_sales_count ?? 0;
    const pendingTotal = session?.totals?.pending_sales_total ?? '0';
    const hasPending = pendingCount > 0;

    const handleClose = () => {
        setResult(null);
        setError('');
        onClose();
    };

    const handleConfirm = async () => {
        if (!session) {
            return;
        }
        setError('');
        try {
            const response = await mutation.mutateAsync(session.id);
            setResult(response);
        } catch (err) {
            const apiError = err as ApiError;
            setError(apiError.message ?? 'No pudimos registrar los cobros masivos.');
        }
    };

    return (
        <Modal open={open} title="Cobrar ventas pendientes" onClose={handleClose}>
            {result ? (
                <div className="space-y-3 text-sm">
                    <p className="text-slate-600">
                        Registramos {result.result.collected_count} cobros por {formatCurrency(result.result.total_collected)}.
                    </p>
                    {result.result.skipped_count > 0 ? (
                        <p className="text-amber-700">
                            {result.result.skipped_count} ventas ya estaban saldadas y no se modificaron.
                        </p>
                    ) : null}
                    {result.result.errors.length > 0 ? (
                        <ul className="list-disc space-y-1 pl-5 text-rose-600">
                            {result.result.errors.map((item) => (
                                <li key={item}>{item}</li>
                            ))}
                        </ul>
                    ) : null}
                    <button
                        type="button"
                        onClick={handleClose}
                        className="mt-2 w-full rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                    >
                        Listo
                    </button>
                </div>
            ) : (
                <div className="space-y-4 text-sm">
                    <p className="text-slate-600">
                        Vamos a registrar un pago en efectivo por cada venta con saldo. Lo verás en Movimientos y en el cierre de caja.
                    </p>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Detalle estimado</p>
                        <p className="text-lg font-semibold text-slate-900">
                            {pendingCount} ventas · {formatCurrency(pendingTotal)}
                        </p>
                    </div>
                    {!canCollect ? (
                        <p className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-rose-600">
                            Necesitás permisos para gestionar la caja.
                        </p>
                    ) : null}
                    {!hasPending ? (
                        <p className="text-slate-500">No hay ventas con saldo pendiente en este turno.</p>
                    ) : null}
                    {error ? <p className="text-rose-600">{error}</p> : null}
                    <div className="flex items-center justify-end gap-2">
                        <button
                            type="button"
                            onClick={handleClose}
                            className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                        >
                            Cancelar
                        </button>
                        <button
                            type="button"
                            onClick={handleConfirm}
                            disabled={!canCollect || !hasPending || mutation.isLoading}
                            className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                        >
                            {mutation.isLoading ? 'Registrando...' : 'Confirmar'}
                        </button>
                    </div>
                </div>
            )}
        </Modal>
    );
}

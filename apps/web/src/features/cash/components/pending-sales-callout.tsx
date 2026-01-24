"use client";

import { formatCurrency } from '../utils';

interface PendingSalesCalloutProps {
    pendingCount: number;
    pendingTotal: string;
    canCollect: boolean;
    onCollectAll: () => void;
}

export function PendingSalesCallout({ pendingCount, pendingTotal, canCollect, onCollectAll }: PendingSalesCalloutProps) {
    return (
        <div className="flex flex-col gap-4 rounded-3xl border border-amber-200 bg-gradient-to-r from-amber-50 to-white p-5 shadow-sm md:flex-row md:items-center md:justify-between">
            <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-amber-600">Ventas con saldo</p>
                <p className="text-xl font-semibold text-amber-900">
                    {pendingCount} pendientes · {formatCurrency(pendingTotal)}
                </p>
                <p className="text-sm text-amber-800">
                    Registraremos un cobro en efectivo por cada venta o podés activar la opción automática durante el cierre.
                </p>
            </div>
            <button
                type="button"
                onClick={onCollectAll}
                disabled={!canCollect}
                className="inline-flex items-center justify-center rounded-full border border-amber-700 px-5 py-2 text-sm font-semibold text-amber-900 transition hover:bg-amber-700 hover:text-white disabled:cursor-not-allowed disabled:border-amber-200 disabled:text-amber-300"
            >
                Cobrar todas las pendientes
            </button>
        </div>
    );
}

"use client";

import Link from 'next/link';

import { formatCurrency, formatDateTime } from '../utils';
import type { CashSession } from '../types';

type CashSessionBannerProps = {
    session: CashSession | null | undefined;
    loading?: boolean;
    canManage: boolean;
    onOpenRequest: () => void;
};

export function CashSessionBanner({ session, loading, canManage, onOpenRequest }: CashSessionBannerProps) {
    if (loading) {
        return (
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <p className="text-sm text-slate-500">Buscando estado de la caja...</p>
            </div>
        );
    }

    if (!session) {
        return (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-6 text-center shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Caja</p>
                <h2 className="text-2xl font-semibold text-slate-900">Caja cerrada</h2>
                <p className="mt-2 text-sm text-slate-500">Abrí una sesión para registrar cobros y movimientos.</p>
                <button
                    type="button"
                    onClick={onOpenRequest}
                    disabled={!canManage}
                    className="mt-4 inline-flex items-center justify-center rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                >
                    Abrir caja
                </button>
            </div>
        );
    }

    return (
        <div className="flex flex-col gap-4 rounded-3xl border border-slate-200 bg-gradient-to-r from-emerald-50 to-slate-50 p-6 shadow-sm md:flex-row md:items-center md:justify-between">
            <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-600">Caja abierta</p>
                <h2 className="text-2xl font-semibold text-slate-900">
                    {session.register?.name ?? 'Caja principal'} · {formatCurrency(session.opening_cash_amount)}
                </h2>
                <p className="text-sm text-slate-600">
                    Apertura {formatDateTime(session.opened_at)}
                    {session.opened_by ? ` · ${session.opened_by.name}` : ''}
                </p>
            </div>
            <div className="flex flex-col gap-2 md:items-end">
                <p className="text-sm font-semibold text-slate-700">Saldo esperado</p>
                <p className="text-3xl font-bold text-slate-900">{formatCurrency(session.totals?.cash_expected_total)}</p>
                <Link
                    href="/app/operacion/caja/cierre"
                    className="inline-flex items-center justify-center rounded-full border border-slate-900 px-5 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-900 hover:text-white"
                >
                    Ir a cierre
                </Link>
            </div>
        </div>
    );
}

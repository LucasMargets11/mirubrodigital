"use client";

import { useQuery } from '@tanstack/react-query';
import { Loader2, Package, ExternalLink, ArrowUpRight, ShoppingCart } from 'lucide-react';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';
import Link from 'next/link';

import { listExpenses, Expense } from '@/lib/api/treasury';
import { Currency } from '../components/currency';
import { EmptyState } from '../components/empty-state';
import { cn } from '@/lib/utils';

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
    paid: { label: 'Pagado', cls: 'bg-emerald-100 text-emerald-700' },
    pending: { label: 'Pendiente', cls: 'bg-amber-100 text-amber-700' },
    cancelled: { label: 'Anulado', cls: 'bg-red-100 text-red-600 line-through' },
};

function ReplenishmentExpenseCard({ expense }: { expense: Expense }) {
    const statusInfo = STATUS_LABELS[expense.status] ?? { label: expense.status, cls: 'bg-slate-100 text-slate-600' };
    const details = expense.source_details;
    const isCancelled = expense.status === 'cancelled';

    return (
        <div className={cn(
            'bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-shadow',
            isCancelled && 'opacity-60',
        )}>
            {/* Header row */}
            <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-1 text-xs font-medium bg-violet-100 text-violet-700 px-2 py-1 rounded-full">
                        <Package className="h-3 w-3" />
                        Generado automáticamente
                    </span>
                </div>
                <span className={cn('text-xs font-semibold px-2 py-1 rounded-full', statusInfo.cls)}>
                    {statusInfo.label}
                </span>
            </div>

            {/* Supplier / description */}
            <div className="mb-1">
                <p className="font-semibold text-slate-800 text-sm leading-snug">
                    {details?.supplier_name ?? expense.name}
                </p>
                {details?.invoice_number && (
                    <p className="text-xs text-slate-400 mt-0.5">Factura: {details.invoice_number}</p>
                )}
            </div>

            {/* Category + date */}
            <div className="flex gap-2 mb-3 text-xs text-slate-500">
                <span className="bg-slate-100 px-2 py-0.5 rounded-md">
                    {expense.category_name ?? 'Restablecimiento de stock'}
                </span>
                <span>
                    {format(new Date(expense.due_date), "d MMM yyyy", { locale: es })}
                </span>
            </div>

            {/* Amount */}
            <p className="text-2xl font-bold font-mono text-slate-900 mb-4">
                <Currency amount={expense.amount} />
            </p>

            {/* Action links */}
            {details && (
                <div className="flex flex-wrap gap-2 pt-3 border-t border-slate-100">
                    <ReplenishmentLink sourceId={details.id} />
                    {expense.payment_transaction && (
                        <MovimientoLink transactionId={expense.payment_transaction} />
                    )}
                </div>
            )}
        </div>
    );
}

function ReplenishmentLink({ sourceId }: { sourceId: string }) {
    return (
        <Link
            href={`/app/gestion/stock/compras/${sourceId}`}
            className="inline-flex items-center gap-1 text-xs font-medium text-violet-600 hover:text-violet-800 hover:underline"
        >
            <ShoppingCart className="h-3 w-3" />
            Ver reposición
            <ExternalLink className="h-3 w-3" />
        </Link>
    );
}

function MovimientoLink({ transactionId }: { transactionId: number }) {
    return (
        <Link
            href={`/app/gestion/finanzas/movimientos?transaction=${transactionId}`}
            className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800 hover:underline"
        >
            <ArrowUpRight className="h-3 w-3" />
            Ver movimiento
            <ExternalLink className="h-3 w-3" />
        </Link>
    );
}

export function ReplenishmentExpensesClient() {
    const { data, isLoading } = useQuery({
        queryKey: ['treasury', 'expenses', 'replenishments'],
        queryFn: () => listExpenses({ source_type: 'stock_replenishment', limit: 200 }),
    });

    if (isLoading) {
        return (
            <div className="flex justify-center p-12">
                <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
            </div>
        );
    }

    const expenses = data?.results ?? [];

    if (expenses.length === 0) {
        return (
            <EmptyState
                title="Sin reposiciones de stock registradas"
                description="Cuando confirmes una reposición de mercadería, aparecerá aquí automáticamente como gasto clasificado."
            />
        );
    }

    // Group totals
    const posted = expenses.filter((e) => e.status !== 'cancelled');
    const totalAmount = posted.reduce((sum, e) => sum + parseFloat(e.amount), 0);

    return (
        <div className="space-y-6">
            {/* Summary banner */}
            <div className="bg-violet-50 border border-violet-200 rounded-2xl p-4 flex flex-col sm:flex-row gap-3 justify-between items-start sm:items-center">
                <div>
                    <p className="text-xs text-violet-500 font-medium uppercase tracking-wide">Total en reposiciones</p>
                    <p className="text-2xl font-bold text-violet-800 font-mono">
                        <Currency amount={String(totalAmount.toFixed(2))} />
                    </p>
                </div>
                <p className="text-xs text-violet-500">
                    {posted.length} reposición{posted.length !== 1 ? 'es' : ''} activa{posted.length !== 1 ? 's' : ''}
                </p>
            </div>

            {/* ℹ Note about double-count */}
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 text-xs text-blue-700">
                <strong>Sin doble impacto:</strong> Estos gastos están vinculados al movimiento financiero ya registrado. El saldo de tus cuentas refleja únicamente los movimientos, no se genera un egreso duplicado.
            </div>

            {/* Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {expenses.map((expense) => (
                    <ReplenishmentExpenseCard key={expense.id} expense={expense} />
                ))}
            </div>
        </div>
    );
}

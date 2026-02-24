"use client";

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';
import {
    ShoppingCart, ArrowLeft, Loader2, CheckCircle2, Ban,
    ReceiptText, Package, ExternalLink, AlertTriangle
} from 'lucide-react';
import Link from 'next/link';

import { getReplenishment, voidReplenishment } from '@/lib/api/replenishment';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

function formatCurrency(value: string | number) {
    return Number(value).toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export function ReplenishmentDetailClient({ id, canManage }: { id: string; canManage: boolean }) {
    const queryClient = useQueryClient();
    const [voidOpen, setVoidOpen] = useState(false);
    const [voidReason, setVoidReason] = useState('');
    const [voidError, setVoidError] = useState('');

    const { data: repl, isLoading, error } = useQuery({
        queryKey: ['replenishments', id],
        queryFn: () => getReplenishment(id),
    });

    const voidMutation = useMutation({
        mutationFn: (reason: string) => voidReplenishment(id, reason),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['replenishments'] });
            setVoidOpen(false);
            setVoidReason('');
        },
        onError: (err: any) => {
            setVoidError(err?.message ?? 'Error al anular');
        },
    });

    if (isLoading) {
        return (
            <div className="flex justify-center items-center py-16">
                <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
            </div>
        );
    }

    if (error || !repl) {
        return (
            <div className="text-center py-16 text-slate-500">
                No se pudo cargar la reposición.
            </div>
        );
    }

    const isVoided = repl.status === 'voided';
    const inItems = repl.items.filter((i) => i.movement_type === 'IN');

    return (
        <div className="space-y-6 max-w-3xl">
            {/* Back */}
            <Link
                href="/app/gestion/stock/compras"
                className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 transition-colors"
            >
                <ArrowLeft className="h-4 w-4" />
                Volver a Compras
            </Link>

            {/* Header card */}
            <div className={cn('bg-white rounded-3xl border border-slate-200 p-6 shadow-sm', isVoided && 'opacity-70')}>
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-4">
                        <div className={cn('p-3 rounded-2xl', isVoided ? 'bg-slate-100 text-slate-400' : 'bg-orange-100 text-orange-600')}>
                            <ShoppingCart className="h-6 w-6" />
                        </div>
                        <div>
                            <div className="flex items-center gap-2 flex-wrap">
                                <h1 className="text-xl font-bold text-slate-900">{repl.supplier_name}</h1>
                                {isVoided ? (
                                    <span className="px-3 py-1 text-xs font-semibold rounded-full bg-slate-200 text-slate-500">
                                        Anulado
                                    </span>
                                ) : (
                                    <span className="px-3 py-1 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-700">
                                        Confirmado
                                    </span>
                                )}
                            </div>
                            <p className="text-sm text-slate-500 mt-1">
                                {format(new Date(repl.occurred_at), "d 'de' MMMM yyyy, HH:mm", { locale: es })}
                                {repl.invoice_number && (
                                    <span className="ml-2 font-mono bg-slate-100 px-2 py-0.5 rounded text-xs">{repl.invoice_number}</span>
                                )}
                            </p>
                        </div>
                    </div>
                    <div className="text-right">
                        <div className={cn('text-2xl font-bold font-mono', isVoided ? 'text-slate-400 line-through' : 'text-orange-600')}>
                            ${formatCurrency(repl.total_amount)}
                        </div>
                        {repl.account_name && (
                            <p className="text-sm text-slate-500 mt-1">{repl.account_name}</p>
                        )}
                    </div>
                </div>

                {repl.notes && (
                    <p className="mt-4 text-sm text-slate-600 bg-slate-50 rounded-xl px-4 py-3 border border-slate-100">
                        {repl.notes}
                    </p>
                )}

                {/* Void action */}
                {canManage && !isVoided && (
                    <div className="mt-4 pt-4 border-t border-slate-100 flex justify-end">
                        <Button
                            variant="outline"
                            onClick={() => setVoidOpen(true)}
                            className="text-rose-600 border-rose-200 hover:bg-rose-50"
                        >
                            <Ban className="mr-2 h-4 w-4" />
                            Anular reposición
                        </Button>
                    </div>
                )}
            </div>

            {/* Items */}
            <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2">
                    <Package className="h-5 w-5 text-slate-500" />
                    <h2 className="font-semibold text-slate-900">Productos</h2>
                    <span className="text-sm text-slate-500">({inItems.length})</span>
                </div>
                <table className="w-full text-sm">
                    <thead className="bg-slate-50">
                        <tr className="text-left text-slate-500 text-xs uppercase tracking-wide">
                            <th className="px-6 py-3">Producto</th>
                            <th className="px-4 py-3 text-right">Cantidad</th>
                            <th className="px-4 py-3 text-right">Costo unit.</th>
                            <th className="px-6 py-3 text-right">Total línea</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {inItems.map((item) => (
                            <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                                <td className="px-6 py-3">
                                    <div className="font-medium text-slate-900">{item.product_name}</div>
                                    {item.product_sku && (
                                        <div className="text-xs text-slate-400 font-mono">{item.product_sku}</div>
                                    )}
                                </td>
                                <td className="px-4 py-3 text-right font-mono">{item.quantity}</td>
                                <td className="px-4 py-3 text-right font-mono">
                                    {item.unit_cost ? `$${formatCurrency(item.unit_cost)}` : '—'}
                                </td>
                                <td className="px-6 py-3 text-right font-mono font-semibold text-slate-900">
                                    {item.line_total ? `$${formatCurrency(item.line_total)}` : '—'}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                    <tfoot>
                        <tr className="bg-slate-50">
                            <td colSpan={3} className="px-6 py-3 text-right text-sm font-semibold text-slate-700">
                                Total
                            </td>
                            <td className="px-6 py-3 text-right font-bold font-mono text-orange-600">
                                ${formatCurrency(repl.total_amount)}
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>

            {/* Impact section */}
            <div className="bg-white rounded-3xl border border-slate-200 shadow-sm p-6 space-y-4">
                <div className="flex items-center gap-2">
                    <ReceiptText className="h-5 w-5 text-slate-500" />
                    <h2 className="font-semibold text-slate-900">Impacto financiero</h2>
                </div>

                {repl.transaction ? (
                    <div className="flex items-center justify-between p-4 bg-rose-50 rounded-2xl border border-rose-100">
                        <div>
                            <p className="text-sm font-medium text-rose-800">Transacción OUT generada</p>
                            <p className="text-xs text-rose-600 mt-0.5">
                                ${formatCurrency(repl.transaction.amount)} · {repl.transaction.account_name}
                                {' · '}
                                <span className={cn(
                                    'font-semibold',
                                    repl.transaction.status === 'voided' ? 'line-through text-slate-400' : 'text-rose-700'
                                )}>
                                    {repl.transaction.status === 'voided' ? 'Anulado' : 'Confirmado'}
                                </span>
                            </p>
                        </div>
                        <Link
                            href={`/app/gestion/finanzas/movimientos?search=${repl.supplier_name}`}
                            className="inline-flex items-center gap-1 text-sm text-rose-600 hover:text-rose-800 font-medium"
                        >
                            Ver en finanzas
                            <ExternalLink className="h-3.5 w-3.5" />
                        </Link>
                    </div>
                ) : (
                    <p className="text-sm text-slate-500">No hay transacción asociada.</p>
                )}

                {/* Stock movements summary */}
                <div>
                    <p className="text-sm text-slate-600 font-medium mb-2">
                        Movimientos de stock generados ({inItems.length} entradas IN)
                    </p>
                    <div className="flex flex-wrap gap-2">
                        {inItems.map((item) => (
                            <span
                                key={item.id}
                                className="text-xs bg-emerald-50 border border-emerald-200 text-emerald-700 px-2 py-1 rounded-lg font-medium"
                            >
                                +{item.quantity} {item.product_name}
                            </span>
                        ))}
                        {repl.items.filter((i) => i.movement_type === 'OUT').map((item) => (
                            <span
                                key={item.id}
                                className="text-xs bg-slate-100 border border-slate-200 text-slate-500 px-2 py-1 rounded-lg line-through"
                            >
                                −{item.quantity} {item.product_name} (reversa)
                            </span>
                        ))}
                    </div>
                </div>
            </div>

            {/* Void Modal */}
            <Modal open={voidOpen} onClose={() => setVoidOpen(false)} title="Anular reposición">
                <div className="space-y-4">
                    <div className="flex items-start gap-3 p-4 bg-rose-50 border border-rose-200 rounded-xl">
                        <AlertTriangle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
                        <div>
                            <p className="text-sm font-semibold text-rose-800">Esta acción revertirá el stock y la transacción</p>
                            <p className="text-sm text-rose-700 mt-1">
                                Se crearán movimientos OUT compensatorios y la transacción financiera quedará anulada.
                                El stock neto volverá a su valor anterior.
                            </p>
                        </div>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                            Motivo de anulación <span className="text-rose-500">*</span>
                        </label>
                        <input
                            type="text"
                            value={voidReason}
                            onChange={(e) => setVoidReason(e.target.value)}
                            className="w-full rounded-lg border border-slate-300 text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-rose-500"
                            placeholder="Ej. Error de carga, proveedor equivocado..."
                        />
                        {voidError && <p className="text-xs text-rose-600 mt-1">{voidError}</p>}
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
                        <Button variant="outline" onClick={() => setVoidOpen(false)}>
                            Cancelar
                        </Button>
                        <Button
                            onClick={() => {
                                setVoidError('');
                                if (!voidReason.trim()) {
                                    setVoidError('El motivo es requerido.');
                                    return;
                                }
                                voidMutation.mutate(voidReason.trim());
                            }}
                            disabled={voidMutation.isPending}
                            className="bg-rose-600 hover:bg-rose-700 text-white"
                        >
                            {voidMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Confirmar anulación
                        </Button>
                    </div>
                </div>
            </Modal>
        </div>
    );
}

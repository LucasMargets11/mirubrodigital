"use client";

import Link from 'next/link';
import { useMemo } from 'react';

import { useRecentInventoryMovements, useRecentQuotes, useRecentSales } from '@/features/gestion/hooks';
import { formatCurrency, formatNumber } from '@/lib/format';
import { cn } from '@/lib/utils';

type RecentActivityProps = {
    canViewStock: boolean;
    inventoryEnabled: boolean;
    canViewSales: boolean;
    salesEnabled: boolean;
    canViewQuotes: boolean;
    quotesEnabled: boolean;
};

type ActivityEvent = {
    id: string;
    kind: 'sale' | 'movement' | 'quote';
    title: string;
    description: string;
    timestamp: string;
    href?: string;
    icon: string;
    amountLabel?: string;
};

export function RecentActivity({ canViewSales, salesEnabled, canViewStock, inventoryEnabled, canViewQuotes, quotesEnabled }: RecentActivityProps) {
    const salesAllowed = canViewSales && salesEnabled;
    const stockAllowed = canViewStock && inventoryEnabled;
    const quotesAllowed = canViewQuotes && quotesEnabled;

    const salesQuery = useRecentSales(5, salesAllowed);
    const movementsQuery = useRecentInventoryMovements(5, stockAllowed);
    const quotesQuery = useRecentQuotes(5, quotesAllowed);

    const events = useMemo<ActivityEvent[]>(() => {
        const saleEvents: ActivityEvent[] = (salesQuery.data ?? []).map((sale) => ({
            id: sale.id,
            kind: 'sale',
            title: `Venta #${sale.number}`,
            description: sale.customer_name ?? 'Sin cliente',
            timestamp: sale.created_at,
            href: `/app/gestion/ventas/${sale.id}`,
            icon: '🛒',
            amountLabel: formatCurrency(sale.total),
        }));

        const movementEvents: ActivityEvent[] = (movementsQuery.data ?? []).map((movement) => ({
            id: movement.id,
            kind: 'movement',
            title: `${movement.movement_type === 'IN' ? 'Ingreso' : movement.movement_type === 'OUT' ? 'Egreso' : 'Ajuste'} · ${movement.product.name}`,
            description: `${formatNumber(movement.quantity)} uds`,
            timestamp: movement.created_at,
            href: '/app/gestion/stock',
            icon: movement.movement_type === 'IN' ? '⬆️' : movement.movement_type === 'OUT' ? '⬇️' : '🛠️',
        }));

        const quoteEvents: ActivityEvent[] = (quotesQuery.data ?? []).map((quote) => ({
            id: quote.id,
            kind: 'quote',
            title: `Presupuesto #${quote.number}`,
            description: quote.customer_name ?? quote.customer_email ?? 'Sin cliente',
            timestamp: quote.created_at,
            href: `/app/gestion/ventas/presupuestos/${quote.id}`,
            icon: '📄',
            amountLabel: formatCurrency(quote.total),
        }));

        return [...saleEvents, ...movementEvents, ...quoteEvents]
            .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
            .slice(0, 10);
    }, [movementsQuery.data, salesQuery.data, quotesQuery.data]);

    const enabled = salesAllowed || stockAllowed || quotesAllowed;

    return (
        <section className="space-y-4 rounded-3xl border border-slate-100 bg-white p-5 shadow-sm">
            <header className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                <div>
                    <h2 className="text-lg font-semibold text-slate-900">Actividad reciente</h2>
                    <p className="text-sm text-slate-500">Últimas ventas, movimientos y presupuestos.</p>
                </div>
                <div className="flex flex-wrap gap-3 text-sm font-semibold text-slate-600">
                    {salesAllowed ? <Link href="/app/gestion/ventas">Ventas →</Link> : null}
                    {stockAllowed ? <Link href="/app/gestion/stock">Movimientos →</Link> : null}
                    {quotesAllowed ? <Link href="/app/gestion/ventas/presupuestos">Presupuestos →</Link> : null}
                </div>
            </header>

            {!enabled ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                    No tenés permisos para ver actividad. Pedí acceso a inventario, ventas o presupuestos.
                </div>
            ) : (
                <div className="space-y-4">
                    {salesQuery.isLoading || movementsQuery.isLoading || quotesQuery.isLoading ? (
                        <TimelineSkeleton />
                    ) : null}
                    {!salesQuery.isLoading && !movementsQuery.isLoading && !quotesQuery.isLoading && events.length === 0 ? (
                        <p className="text-sm text-slate-500">Aún no hay actividad registrada.</p>
                    ) : null}
                    {events.map((event) => (
                        <ActivityRow key={event.id} event={event} />
                    ))}
                </div>
            )}
        </section>
    );
}

function ActivityRow({ event }: { event: ActivityEvent }) {
    return (
        <div className="flex gap-3">
            <div className="flex flex-col items-center">
                <span className="text-lg">{event.icon}</span>
                <span className="mt-1 h-full w-px bg-slate-200" aria-hidden="true" />
            </div>
            <div className="flex-1 rounded-2xl border border-slate-100 bg-slate-50/60 p-3">
                <div className="flex items-center justify-between gap-3">
                    <div>
                        <p className="text-sm font-semibold text-slate-900">{event.title}</p>
                        <p className="text-xs text-slate-500">{event.description}</p>
                    </div>
                    {event.amountLabel ? <span className="text-xs font-semibold text-emerald-600">{event.amountLabel}</span> : null}
                </div>
                <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                    <span>{formatRelativeTime(event.timestamp)}</span>
                    {event.href ? (
                        <Link href={event.href} className="font-semibold text-slate-600 hover:text-slate-900">
                            Ver detalle →
                        </Link>
                    ) : null}
                </div>
            </div>
        </div>
    );
}

function TimelineSkeleton() {
    return (
        <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, idx) => (
                <div key={idx} className="flex gap-3">
                    <div className="flex flex-col items-center">
                        <div className="size-4 rounded-full bg-slate-200" />
                        <span className="mt-1 h-full w-px bg-slate-200" />
                    </div>
                    <div className="flex-1 rounded-2xl border border-slate-100 p-3">
                        <div className="mb-2 h-3 w-1/3 rounded-full bg-slate-200" />
                        <div className="h-2 w-1/2 rounded-full bg-slate-100" />
                    </div>
                </div>
            ))}
        </div>
    );
}

function formatRelativeTime(timestamp: string) {
    const now = Date.now();
    const value = new Date(timestamp).getTime();
    const diffMs = value - now;
    const diffMinutes = Math.round(diffMs / (1000 * 60));
    const formatter = new Intl.RelativeTimeFormat('es', { numeric: 'auto' });

    if (Math.abs(diffMinutes) < 60) {
        return formatter.format(diffMinutes, 'minute');
    }
    const diffHours = Math.round(diffMinutes / 60);
    if (Math.abs(diffHours) < 24) {
        return formatter.format(diffHours, 'hour');
    }
    const diffDays = Math.round(diffHours / 24);
    return formatter.format(diffDays, 'day');
}

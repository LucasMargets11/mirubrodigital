"use client";

import { useMemo, useState } from 'react';

import { TablesMap } from '@/components/tables/tables-map';
import type { RestaurantTableNode, RestaurantTableState, TablesGridDimensions } from '@/features/tables/types';
import { cn } from '@/lib/utils';

const STATUS_LABELS: Record<RestaurantTableState, { label: string; dot: string; description: string }> = {
    FREE: { label: 'Libre', dot: 'bg-emerald-400', description: 'Disponible para asignar' },
    OCCUPIED: { label: 'Ocupada', dot: 'bg-rose-400', description: 'Tiene una orden activa' },
    PAUSED: { label: 'Pausada', dot: 'bg-amber-400', description: 'Bloqueada temporalmente' },
    DISABLED: { label: 'Deshabilitada', dot: 'bg-slate-400', description: 'Oculta en el mapa' },
};

export type TableMapEmbedProps = {
    tables: RestaurantTableNode[];
    selectedTableId?: string | null;
    loading?: boolean;
    error?: string | null;
    layout?: TablesGridDimensions;
    onSelectTable?: (tableId: string, snapshot?: RestaurantTableNode) => void;
};

export function TableMapEmbed({ tables, selectedTableId, loading, error, layout, onSelectTable }: TableMapEmbedProps) {
    const [filter, setFilter] = useState<'all' | 'free'>('all');
    const [searchTerm, setSearchTerm] = useState('');

    const totals = useMemo(() => {
        const base = { FREE: 0, OCCUPIED: 0, PAUSED: 0, DISABLED: 0 } as Record<RestaurantTableState, number>;
        tables.forEach((table) => {
            const status = table.state ?? (table.is_enabled ? 'FREE' : 'DISABLED');
            base[status] = (base[status] ?? 0) + 1;
        });
        return base;
    }, [tables]);

    const highlightedTableId = useMemo(() => {
        const term = searchTerm.trim().toLowerCase();
        if (!term) {
            return null;
        }
        const found = tables.find((table) => table.code.toLowerCase().includes(term));
        return found?.id ?? null;
    }, [tables, searchTerm]);

    const visibleStatuses = filter === 'free' ? (['FREE'] as RestaurantTableState[]) : undefined;

    const handleSelect = (tableId: string) => {
        const snapshot = tables.find((table) => table.id === tableId);
        onSelectTable?.(tableId, snapshot);
    };

    const renderContent = () => {
        if (loading) {
            return (
                <div className="space-y-2">
                    {Array.from({ length: 4 }).map((_, index) => (
                        <div key={`skeleton-${index}`} className="h-20 animate-pulse rounded-xl bg-slate-100" />
                    ))}
                </div>
            );
        }
        if (error) {
            return <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>;
        }
        const placed = tables.filter((table) => table.position);
        if (tables.length === 0) {
            return (
                <div className="space-y-3 rounded-2xl border border-dashed border-slate-200 bg-white/70 px-4 py-6 text-sm text-slate-600">
                    <p className="font-semibold text-slate-900">Todavía no cargaste mesas en este salón.</p>
                    <p>
                        Creá al menos una mesa desde <a href="/app/resto/settings/tables" className="font-semibold text-slate-900 underline-offset-2 hover:underline">Configuración &gt; Restaurante &gt; Mesas</a> para habilitar el mapa.
                    </p>
                </div>
            );
        }
        if (placed.length === 0) {
            return (
                <p className="rounded-xl border border-dashed border-slate-200 px-3 py-2 text-sm text-slate-500">
                    Las mesas no tienen posición asignada. Ajustalas en Configuración &gt; Mesas para verlas aquí.
                </p>
            );
        }
        return (
            <div className="relative min-h-[520px] rounded-2xl border border-slate-100 bg-slate-100/70">
                <div className="h-full w-full overflow-auto rounded-2xl bg-gradient-to-br from-white via-slate-50 to-slate-100 p-4">
                    <TablesMap
                        tables={tables}
                        layout={layout}
                        selectedTableId={selectedTableId ?? undefined}
                        onSelectTable={handleSelect}
                        className="min-h-[520px] min-w-[720px]"
                        visibleStates={visibleStatuses}
                        highlightedTableId={highlightedTableId}
                    />
                </div>
            </div>
        );
    };

    return (
        <div className="space-y-4 rounded-3xl border border-slate-200 bg-white/90 p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Mapa del salón</p>
                    <h3 className="text-xl font-semibold text-slate-900">Mesas</h3>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                    {(Object.keys(STATUS_LABELS) as TableStatus[]).map((key) => {
                        const meta = STATUS_LABELS[key];
                        return (
                            <span key={key} className="inline-flex items-center gap-1 rounded-full bg-slate-50 px-3 py-1 text-slate-600">
                                <span className={`h-2 w-2 rounded-full ${meta.dot}`} aria-hidden />
                                {meta.label}: {totals[key] ?? 0}
                            </span>
                        );
                    })}
                </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center rounded-full border border-slate-200 bg-white p-0.5 text-xs font-semibold text-slate-600">
                    {['all', 'free'].map((value) => (
                        <button
                            key={value}
                            type="button"
                            onClick={() => setFilter(value as 'all' | 'free')}
                            className={cn(
                                'rounded-full px-3 py-1 transition',
                                filter === value ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:text-slate-900'
                            )}
                        >
                            {value === 'all' ? 'Todas' : 'Solo libres'}
                        </button>
                    ))}
                </div>
                <div className="relative flex-1">
                    <input
                        type="search"
                        value={searchTerm}
                        onChange={(event) => setSearchTerm(event.target.value)}
                        placeholder="Buscar mesa (ej. M12)"
                        className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    />
                    {searchTerm ? (
                        <button
                            type="button"
                            onClick={() => setSearchTerm('')}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold uppercase text-slate-400"
                        >
                            Limpiar
                        </button>
                    ) : null}
                </div>
            </div>
            {renderContent()}
        </div>
    );
}

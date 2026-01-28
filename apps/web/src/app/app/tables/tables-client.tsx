"use client";

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import { TablesMap } from '@/components/tables/tables-map';
import { useRestaurantTablesMapState } from '@/features/tables/hooks';
import type { RestaurantTableNode, RestaurantTableState } from '@/features/tables/types';

const STATUS_META: Record<RestaurantTableState, { label: string; badge: string }> = {
    FREE: { label: 'Libre', badge: 'bg-emerald-50 text-emerald-700' },
    OCCUPIED: { label: 'Ocupada', badge: 'bg-rose-50 text-rose-700' },
    PAUSED: { label: 'Pausada', badge: 'bg-amber-50 text-amber-700' },
    DISABLED: { label: 'Deshabilitada', badge: 'bg-slate-100 text-slate-500' },
};

export function TablesClient() {
    const router = useRouter();
    const [selectedTableId, setSelectedTableId] = useState<string | null>(null);
    const mapStateQuery = useRestaurantTablesMapState();
    const tables = mapStateQuery.data?.tables ?? [];
    const layout = mapStateQuery.data?.layout;

    useEffect(() => {
        if (!tables.length) {
            setSelectedTableId(null);
            return;
        }
        setSelectedTableId((current) => {
            if (current && tables.some((table) => table.id === current)) {
                return current;
            }
            return tables[0]?.id ?? null;
        });
    }, [tables]);

    const selectedTable: RestaurantTableNode | null = useMemo(() => {
        if (!selectedTableId) {
            return null;
        }
        return tables.find((table) => table.id === selectedTableId) ?? null;
    }, [selectedTableId, tables]);

    const statusSummary = useMemo(() => {
        return tables.reduce(
            (acc, table) => {
                acc[table.state] = (acc[table.state] ?? 0) + 1;
                return acc;
            },
            { FREE: 0, OCCUPIED: 0, PAUSED: 0, DISABLED: 0 } as Record<RestaurantTableState, number>
        );
    }, [tables]);

    const handleSelectTable = (tableId: string) => {
        setSelectedTableId(tableId);
    };

    const handlePrimaryAction = () => {
        if (!selectedTable) {
            return;
        }
        if (selectedTable.state === 'FREE') {
            router.push(`/app/orders/new?tableId=${selectedTable.id}`);
            return;
        }
        if (selectedTable.state === 'OCCUPIED' && selectedTable.active_order) {
            router.push(`/app/orders/${selectedTable.active_order.id}`);
        }
    };

    return (
        <section className="space-y-6">
            <header className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                    <p className="text-xs uppercase tracking-wide text-slate-400">Servicio Restaurante</p>
                    <h1 className="text-3xl font-semibold text-slate-900">Mapa de mesas</h1>
                    <p className="text-sm text-slate-500">
                        Visualizá disponibilidad en tiempo real y crea nuevas órdenes directamente desde el plano.
                    </p>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                    {(Object.keys(STATUS_META) as RestaurantTableState[]).map((status) => (
                        <span key={status} className={`flex items-center gap-2 rounded-full px-3 py-1 ${STATUS_META[status].badge}`}>
                            {STATUS_META[status].label}
                            <span className="text-slate-400">{statusSummary[status] ?? 0}</span>
                        </span>
                    ))}
                </div>
            </header>
            <div className="grid gap-6 lg:grid-cols-[1fr,320px]">
                <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                    {mapStateQuery.isLoading ? (
                        <div className="space-y-4">
                            {Array.from({ length: 3 }).map((_, index) => (
                                <div key={`skeleton-${index}`} className="h-32 animate-pulse rounded-2xl bg-slate-100" />
                            ))}
                        </div>
                    ) : mapStateQuery.isError ? (
                        <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                            No pudimos cargar el mapa. Reintentá en unos segundos.
                        </p>
                    ) : tables.length === 0 ? (
                        <div className="space-y-3 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
                            <p className="font-semibold text-slate-900">Todavía no cargaste mesas en este salón.</p>
                            <p>
                                Configurá mesas en <a href="/app/resto/settings/tables" className="font-semibold text-slate-900 underline-offset-2 hover:underline">Configuración &gt; Mesas</a> para verlas acá.
                            </p>
                        </div>
                    ) : (
                        <TablesMap
                            tables={tables}
                            layout={layout}
                            selectedTableId={selectedTableId}
                            onSelectTable={handleSelectTable}
                            className="min-h-[560px]"
                        />
                    )}
                </div>
                <aside className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                    {selectedTable ? (
                        <div className="space-y-3">
                            <p className="text-xs uppercase tracking-wide text-slate-400">Mesa seleccionada</p>
                            <h2 className="text-2xl font-semibold text-slate-900">{selectedTable.name}</h2>
                            <dl className="space-y-1 text-sm text-slate-600">
                                <div className="flex items-center justify-between">
                                    <dt className="text-slate-500">Código</dt>
                                    <dd className="font-medium text-slate-900">{selectedTable.code}</dd>
                                </div>
                                <div className="flex items-center justify-between">
                                    <dt className="text-slate-500">Capacidad</dt>
                                    <dd className="font-medium text-slate-900">{selectedTable.capacity ?? '—'}</dd>
                                </div>
                                <div className="flex items-center justify-between">
                                    <dt className="text-slate-500">Estado</dt>
                                    <dd className="font-medium text-slate-900">{STATUS_META[selectedTable.state].label}</dd>
                                </div>
                            </dl>
                            {selectedTable.state === 'DISABLED' ? (
                                <p className="text-xs text-rose-500">Mesa deshabilitada. Activala desde la configuración.</p>
                            ) : null}
                            {selectedTable.state === 'PAUSED' ? (
                                <p className="text-xs text-amber-600">Mesa pausada temporalmente.</p>
                            ) : null}
                            {selectedTable.state === 'OCCUPIED' && selectedTable.active_order ? (
                                <div className="space-y-1 rounded-2xl bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                                    <p>Orden #{selectedTable.active_order.number}</p>
                                    <p className="text-[11px] uppercase tracking-wide text-emerald-600">{selectedTable.active_order.status_label}</p>
                                </div>
                            ) : null}
                            {selectedTable.state === 'FREE' ? (
                                <button
                                    type="button"
                                    onClick={handlePrimaryAction}
                                    className="mt-2 w-full rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                                >
                                    Crear pedido en esta mesa
                                </button>
                            ) : null}
                            {selectedTable.state === 'OCCUPIED' && selectedTable.active_order ? (
                                <button
                                    type="button"
                                    onClick={handlePrimaryAction}
                                    className="mt-2 w-full rounded-full border border-slate-900 px-4 py-2 text-sm font-semibold text-slate-900"
                                >
                                    Ver pedido
                                </button>
                            ) : null}
                        </div>
                    ) : (
                        <p className="text-sm text-slate-500">Seleccioná una mesa del mapa para ver acciones rápidas.</p>
                    )}
                </aside>
            </div>
        </section>
    );
}

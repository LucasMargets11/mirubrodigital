"use client";

import { useCallback, useMemo, useState } from 'react';

import { TablesEditor } from '@/components/tables/tables-editor';
import { useSaveTableConfiguration, useTableConfiguration } from '@/features/tables/hooks';
import type { TableConfiguration } from '@/features/tables/types';

export function TablesSettingsClient() {
    const configurationQuery = useTableConfiguration();
    const saveConfiguration = useSaveTableConfiguration();

    const [previewState, setPreviewState] = useState<TableConfiguration | null>(null);
    const configuration = configurationQuery.data;

    const liveSummary = useMemo(() => {
        const snapshot = previewState ?? configuration;
        if (!snapshot) {
            return { total: 0, enabled: 0 };
        }
        const enabled = snapshot.tables.filter((table) => table.is_enabled).length;
        return {
            total: snapshot.tables.length,
            enabled,
        };
    }, [configuration, previewState]);

    const handleChange = useCallback((payload: TableConfiguration) => {
        setPreviewState(payload);
    }, []);

    const handleSave = useCallback(
        async (payload: TableConfiguration) => {
            await saveConfiguration.mutateAsync(payload);
            setPreviewState(null);
        },
        [saveConfiguration]
    );

    return (
        <section className="space-y-6">
            <header className="space-y-2">
                <p className="text-xs uppercase tracking-wide text-slate-400">Restaurante inteligente</p>
                <h1 className="text-3xl font-semibold text-slate-900">Configurar mapa de mesas</h1>
                <p className="text-sm text-slate-500">
                    Arrastrá las mesas sobre la grilla, renombrá sectores y guardá el layout para sincronizarlo con pedidos y cocina en la próxima fase.
                </p>
                <div className="flex flex-wrap gap-3 text-xs text-slate-500">
                    <span className="rounded-full bg-slate-100 px-3 py-1">Activas: {liveSummary.enabled}</span>
                    <span className="rounded-full bg-slate-100 px-3 py-1">Totales: {liveSummary.total}</span>
                </div>
            </header>
            {configurationQuery.isLoading && !configuration ? (
                <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
                    Cargando configuración de mesas...
                </div>
            ) : null}
            {configurationQuery.isError && !configuration ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
                    No pudimos cargar la configuración actual.
                    <button
                        type="button"
                        onClick={() => configurationQuery.refetch()}
                        className="ml-3 rounded-full border border-rose-500 px-3 py-1 text-xs font-semibold text-rose-600"
                    >
                        Reintentar
                    </button>
                </div>
            ) : null}
            {!configurationQuery.isLoading && !configurationQuery.isError && !configuration ? (
                <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
                    No encontramos mesas configuradas todavía.
                </div>
            ) : null}
            {configuration ? (
                <TablesEditor
                    initialTables={configuration.tables}
                    initialLayout={configuration.layout}
                    onChange={handleChange}
                    onSave={handleSave}
                    saving={saveConfiguration.isPending}
                />
            ) : null}
        </section>
    );
}

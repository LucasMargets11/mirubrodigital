"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';

import type { Table, TablePlacement, TablesLayout } from '@/features/tables/types';

const MAX_TABLES = 40;
const SNAP_OFFSET_RATIO = 0.5; // Snap once we cross half a cell

type TablesEditorProps = {
    initialTables: Table[];
    initialLayout: TablesLayout;
    onChange?: (state: { tables: Table[]; layout: TablesLayout }) => void;
    onSave?: (state: { tables: Table[]; layout: TablesLayout }) => Promise<void>;
    saving?: boolean;
};

type DragState = {
    tableId: string;
};

function clamp(value: number, min: number, max: number) {
    return Math.min(Math.max(value, min), max);
}

function ensurePlacements(tables: Table[], layout: TablesLayout): TablesLayout {
    const placements = [...layout.placements];
    const existing = new Set(placements.map((placement) => placement.tableId));
    let nextLayout = { ...layout, placements };
    tables.forEach((table) => {
        if (!existing.has(table.id)) {
            const nextPlacement = findNextAvailableCell(nextLayout);
            nextLayout = {
                ...nextLayout,
                placements: [...nextLayout.placements, { tableId: table.id, ...nextPlacement }],
            };
        }
    });
    return nextLayout;
}

function findNextAvailableCell(layout: TablesLayout) {
    const occupied = new Set(layout.placements.map((placement) => `${placement.x}:${placement.y}`));
    for (let y = 1; y <= layout.gridRows; y += 1) {
        for (let x = 1; x <= layout.gridCols; x += 1) {
            const key = `${x}:${y}`;
            if (!occupied.has(key)) {
                return { x, y, w: 1, h: 1 } satisfies TablePlacement;
            }
        }
    }
    return { x: 1, y: 1, w: 1, h: 1 } satisfies TablePlacement;
}

export function TablesEditor({ initialTables, initialLayout, onChange, onSave, saving = false }: TablesEditorProps) {
    const normalizedTables = useMemo(() => initialTables.slice(0, MAX_TABLES), [initialTables]);
    const normalizedLayout = useMemo(
        () => ensurePlacements(normalizedTables, initialLayout),
        [initialLayout, normalizedTables]
    );

    const [tables, setTables] = useState<Table[]>(normalizedTables);
    const [layout, setLayout] = useState<TablesLayout>(normalizedLayout);
    const [selectedTableId, setSelectedTableId] = useState<string | null>(normalizedTables[0]?.id ?? null);
    const [dragging, setDragging] = useState<DragState | null>(null);
    const [statusMessage, setStatusMessage] = useState<string | null>(null);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [showCollisionWarning, setShowCollisionWarning] = useState(false);
    const [dirty, setDirty] = useState(false);
    const gridRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        setTables(normalizedTables);
        setLayout(normalizedLayout);
        setSelectedTableId((previous) => {
            if (previous && normalizedTables.some((table) => table.id === previous)) {
                return previous;
            }
            return normalizedTables[0]?.id ?? null;
        });
        setDirty(false);
        setStatusMessage(null);
        setSaveError(null);
    }, [normalizedTables, normalizedLayout]);

    useEffect(() => {
        onChange?.({ tables, layout });
    }, [layout, onChange, tables]);

    const placements = useMemo(() => ensurePlacements(tables, layout).placements, [layout, tables]);

    useEffect(() => {
        const duplicates = new Set<string>();
        const seen = new Set<string>();
        placements.forEach((placement) => {
            const key = `${placement.x}:${placement.y}`;
            if (seen.has(key)) {
                duplicates.add(key);
            } else {
                seen.add(key);
            }
        });
        setShowCollisionWarning(duplicates.size > 0);
    }, [placements]);

    useEffect(() => {
        if (!dragging) {
            return undefined;
        }
        const handlePointerMove = (event: PointerEvent) => {
            if (!gridRef.current) {
                return;
            }
            event.preventDefault();
            const rect = gridRef.current.getBoundingClientRect();
            const cellWidth = rect.width / layout.gridCols;
            const cellHeight = rect.height / layout.gridRows;
            const relativeX = event.clientX - rect.left;
            const relativeY = event.clientY - rect.top;
            const column = clamp(
                Math.floor((relativeX + cellWidth * SNAP_OFFSET_RATIO) / cellWidth) + 1,
                1,
                layout.gridCols
            );
            const row = clamp(
                Math.floor((relativeY + cellHeight * SNAP_OFFSET_RATIO) / cellHeight) + 1,
                1,
                layout.gridRows
            );
            setLayout((prev) => ({
                ...prev,
                placements: prev.placements.map((placement) =>
                    placement.tableId === dragging.tableId
                        ? { ...placement, x: column, y: row }
                        : placement
                ),
            }));
            setDirty(true);
        };

        const handlePointerUp = () => {
            setDragging(null);
            document.body.style.removeProperty('user-select');
        };

        window.addEventListener('pointermove', handlePointerMove);
        window.addEventListener('pointerup', handlePointerUp, { once: true });
        document.body.style.userSelect = 'none';

        return () => {
            window.removeEventListener('pointermove', handlePointerMove);
            window.removeEventListener('pointerup', handlePointerUp);
            document.body.style.removeProperty('user-select');
        };
    }, [dragging, layout.gridCols, layout.gridRows]);

    const handlePointerDown = (tableId: string) => (event: ReactPointerEvent<HTMLButtonElement>) => {
        event.preventDefault();
        setDragging({ tableId });
        setSelectedTableId(tableId);
    };

    const handleTableFieldChange = (tableId: string, field: keyof Table, value: string | boolean) => {
        setTables((prev) =>
            prev.map((table) =>
                table.id === tableId
                    ? {
                        ...table,
                        [field]: field === 'capacity' ? Number(value) || undefined : value,
                    }
                    : table
            )
        );
        setDirty(true);
    };

    const handleAddTable = () => {
        if (tables.length >= MAX_TABLES) {
            setStatusMessage('Llegaste al máximo de mesas para esta fase.');
            return;
        }
        const nextIndex = tables.length + 1;
        const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `table-${Date.now()}`;
        const newTable: Table = {
            id,
            code: `M${nextIndex}`,
            name: `Mesa ${nextIndex}`,
            capacity: 4,
            is_enabled: true,
        };
        setTables((prev) => [...prev, newTable]);
        setLayout((prev) => ({
            ...prev,
            placements: [...prev.placements, { tableId: id, ...findNextAvailableCell(prev) }],
        }));
        setSelectedTableId(id);
        setStatusMessage(null);
        setDirty(true);
    };

    const handleReset = () => {
        setTables(normalizedTables);
        setLayout(normalizedLayout);
        setSelectedTableId(normalizedTables[0]?.id ?? null);
        setStatusMessage('Restauramos el layout original.');
        setSaveError(null);
        setDirty(false);
    };

    const handleDeleteTable = () => {
        if (!selectedTableId) {
            return;
        }
        setTables((prev) => {
            const next = prev.filter((table) => table.id !== selectedTableId);
            setSelectedTableId((current) => {
                if (current && next.some((table) => table.id === current)) {
                    return current;
                }
                return next[0]?.id ?? null;
            });
            return next;
        });
        setLayout((prev) => ({
            ...prev,
            placements: prev.placements.filter((placement) => placement.tableId !== selectedTableId),
        }));
        setDirty(true);
    };

    const handleSave = useCallback(async () => {
        if (!onSave || !dirty) {
            return;
        }
        setSaveError(null);
        setStatusMessage(null);
        try {
            await onSave({ tables, layout });
            setStatusMessage('Cambios guardados.');
            setDirty(false);
        } catch (error) {
            const message =
                (error as { message?: string })?.message ?? 'No pudimos guardar el layout. Intentá nuevamente.';
            setSaveError(message);
        }
    }, [dirty, layout, onSave, tables]);

    useEffect(() => {
        if (!onSave) {
            return undefined;
        }
        const handler = (event: KeyboardEvent) => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
                event.preventDefault();
                void handleSave();
            }
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [handleSave, onSave]);

    const selectedTable = tables.find((table) => table.id === selectedTableId) ?? tables[0];

    return (
        <div className="grid gap-4 lg:grid-cols-[280px,1fr]">
            <aside className="space-y-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs uppercase tracking-wide text-slate-400">Mesas</p>
                        <p className="text-lg font-semibold text-slate-900">{tables.length} / {MAX_TABLES}</p>
                    </div>
                    <button
                        type="button"
                        onClick={handleAddTable}
                        className="rounded-full border border-slate-900 px-2.5 py-1 text-[11px] font-semibold text-slate-900 disabled:opacity-60"
                        disabled={tables.length >= MAX_TABLES}
                    >
                        Crear mesa
                    </button>
                </div>
                <div className="space-y-1.5">
                    {tables.map((table) => (
                        <button
                            key={table.id}
                            type="button"
                            onClick={() => setSelectedTableId(table.id)}
                            className={`w-full rounded-xl border px-3 py-2 text-left text-xs transition ${selectedTableId === table.id ? 'border-slate-900 bg-slate-900/5' : 'border-slate-200 bg-white'}`}
                        >
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-sm font-semibold text-slate-900">{table.code}</p>
                                    <p className="text-[11px] text-slate-500">{table.name}</p>
                                </div>
                                <span className={`text-[10px] font-semibold ${table.is_enabled ? 'text-emerald-600' : 'text-slate-400'}`}>
                                    {table.is_enabled ? 'Activa' : 'Pausada'}
                                </span>
                            </div>
                        </button>
                    ))}
                    {tables.length === 0 ? (
                        <p className="rounded-xl border border-dashed border-slate-200 px-3 py-4 text-center text-[11px] text-slate-500">
                            Todavía no hay mesas. Creá la primera para empezar.
                        </p>
                    ) : null}
                </div>
                {selectedTable ? (
                    <div className="space-y-2.5 rounded-xl bg-slate-50 p-3 text-xs">
                        <div className="flex items-center justify-between">
                            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Detalles</p>
                            <button
                                type="button"
                                onClick={handleDeleteTable}
                                className="text-[11px] font-semibold text-rose-600 hover:text-rose-700"
                            >
                                Eliminar mesa
                            </button>
                        </div>
                        <label className="block text-xs font-semibold text-slate-500">
                            Nombre
                            <input
                                type="text"
                                value={selectedTable.name}
                                onChange={(event) => handleTableFieldChange(selectedTable.id, 'name', event.target.value)}
                                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                        <label className="block text-xs font-semibold text-slate-500">
                            Código
                            <input
                                type="text"
                                value={selectedTable.code}
                                onChange={(event) => handleTableFieldChange(selectedTable.id, 'code', event.target.value)}
                                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                        <label className="block text-xs font-semibold text-slate-500">
                            Capacidad
                            <input
                                type="number"
                                min="1"
                                value={selectedTable.capacity ?? ''}
                                onChange={(event) => handleTableFieldChange(selectedTable.id, 'capacity', event.target.value)}
                                className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                        <label className="flex items-center gap-3 text-xs font-semibold text-slate-500">
                            <input
                                type="checkbox"
                                checked={selectedTable.is_enabled}
                                onChange={(event) => handleTableFieldChange(selectedTable.id, 'is_enabled', event.target.checked)}
                                className="h-4 w-4 rounded border-slate-300"
                            />
                            Mesa habilitada
                        </label>
                    </div>
                ) : null}
                <div className="space-y-2 text-xs">
                    <div className="flex flex-wrap gap-2">
                        <button
                            type="button"
                            onClick={handleSave}
                            className="flex items-center gap-2 rounded-full bg-slate-900 px-3 py-1.5 font-semibold text-white disabled:opacity-50"
                            disabled={!onSave || saving || !dirty}
                        >
                            {saving ? (
                                <span className="h-3 w-3 animate-spin rounded-full border border-white/40 border-t-white" />
                            ) : null}
                            {dirty ? 'Guardar cambios' : 'Sin cambios'}
                        </button>
                        <button
                            type="button"
                            onClick={handleReset}
                            className="rounded-full border border-slate-300 px-3 py-1.5 font-semibold text-slate-600"
                            disabled={saving}
                        >
                            Restaurar
                        </button>
                    </div>
                    {statusMessage ? <p className="text-[11px] text-emerald-600">{statusMessage}</p> : null}
                    {saveError ? <p className="text-[11px] text-rose-600">{saveError}</p> : null}
                    {!onSave ? (
                        <p className="text-[11px] text-slate-400">Guardado temporalmente. Configurá el hook para persistir.</p>
                    ) : null}
                </div>
            </aside>
            <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 via-white to-slate-100 p-3 shadow-inner">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                    <div>
                        <p className="text-[11px] uppercase tracking-wide text-slate-400">Mapa</p>
                        <p className="text-base font-semibold text-slate-900">Arrastrá para reubicar</p>
                    </div>
                    {showCollisionWarning ? (
                        <p className="rounded-full bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-700">
                            Se superponen mesas, ajustalas manualmente
                        </p>
                    ) : null}
                </div>
                <div
                    ref={gridRef}
                    className="grid min-h-[360px] gap-1.5 rounded-xl border border-dashed border-slate-300 bg-slate-50/80 p-1.5"
                    style={{
                        gridTemplateColumns: `repeat(${layout.gridCols}, minmax(0, 1fr))`,
                        gridTemplateRows: `repeat(${layout.gridRows}, minmax(40px, 1fr))`,
                        backgroundImage:
                            'linear-gradient(to right, rgba(148,163,184,0.15) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.15) 1px, transparent 1px)',
                        backgroundSize: '32px 32px',
                    }}
                >
                    {placements.length === 0 ? (
                        <div className="flex items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white/70 text-xs text-slate-400">
                            Agregá mesas para comenzar.
                        </div>
                    ) : null}
                    {placements.map((placement) => {
                        const table = tables.find((item) => item.id === placement.tableId);
                        const disabled = !table?.is_enabled;
                        return (
                            <button
                                key={placement.tableId}
                                type="button"
                                onPointerDown={handlePointerDown(placement.tableId)}
                                style={{
                                    gridColumn: `${placement.x} / span ${placement.w ?? 1}`,
                                    gridRow: `${placement.y} / span ${placement.h ?? 1}`,
                                }}
                                className={`flex flex-col justify-between rounded-xl border px-2.5 py-1.5 text-left text-xs font-semibold transition ${selectedTableId === placement.tableId
                                    ? 'border-slate-900 bg-white'
                                    : 'border-slate-200 bg-white'
                                    } ${disabled ? 'opacity-60 grayscale' : 'cursor-grab active:cursor-grabbing'}`}
                            >
                                <span className="text-[11px] text-slate-400">{table?.name}</span>
                                <p className="text-lg text-slate-900">{table?.code}</p>
                                <p className="text-[11px] text-slate-500">Capacidad {table?.capacity ?? '—'}</p>
                            </button>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

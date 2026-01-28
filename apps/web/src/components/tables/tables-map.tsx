"use client";

import { useMemo } from 'react';

import type { RestaurantTableNode, RestaurantTableState, TablesGridDimensions } from '@/features/tables/types';
import { cn } from '@/lib/utils';

import { TableTileCompact } from './table-tile-compact';

export type TablesMapProps = {
    tables: RestaurantTableNode[];
    selectedTableId?: string | null;
    onSelectTable?: (tableId: string) => void;
    className?: string;
    interactive?: boolean;
    visibleStates?: RestaurantTableState[];
    highlightedTableId?: string | null;
    layout?: TablesGridDimensions | null;
};

export function TablesMap({
    tables,
    selectedTableId,
    onSelectTable,
    className = '',
    interactive = true,
    visibleStates,
    highlightedTableId,
    layout,
}: TablesMapProps) {
    const stateFilter = useMemo(() => new Set<RestaurantTableState>(visibleStates ?? []), [visibleStates]);
    const applyFilter = stateFilter.size > 0;

    const placed = useMemo(
        () =>
            tables
                .filter((table) => Boolean(table.position))
                .sort((a, b) => {
                    const left = a.position?.z_index ?? 0;
                    const right = b.position?.z_index ?? 0;
                    return left - right;
                }),
        [tables]
    );

    const gridReady = Boolean(layout?.gridCols && layout?.gridRows);
    const gridPlacements = useMemo(
        () => placed.filter((table) => Boolean(table.position?.grid)),
        [placed]
    );
    const useGridLayout = gridReady && gridPlacements.length > 0;

    const handleClick = (table: RestaurantTableNode) => {
        if (!interactive) {
            return;
        }
        if (!table.position || table.state === 'DISABLED') {
            return;
        }
        onSelectTable?.(table.id);
    };

    const buildTooltip = (table: RestaurantTableNode) => {
        const tooltipParts: string[] = [];
        if (table.name) {
            tooltipParts.push(table.name);
        }
        if (table.capacity) {
            tooltipParts.push(`Capacidad: ${table.capacity}`);
        }
        if (table.active_order?.status_label) {
            tooltipParts.push(table.active_order.status_label);
        }
        if (table.is_paused) {
            tooltipParts.push('Pausada');
        }
        return tooltipParts.join(' • ');
    };

    const renderTile = (table: RestaurantTableNode) => (
        <TableTileCompact
            code={table.code}
            status={table.state}
            orderNumber={table.active_order?.number ?? null}
            orderCode={table.active_order?.id ?? null}
            selected={selectedTableId === table.id}
            highlight={highlightedTableId === table.id}
            disabled={!interactive || table.state === 'DISABLED'}
            onSelect={() => handleClick(table)}
            tooltip={buildTooltip(table)}
            style={{ width: '100%', height: '100%' }}
        />
    );

    const renderAbsoluteMap = () => (
        <div className="relative min-h-[520px] w-full overflow-hidden rounded-2xl border border-dashed border-slate-200 bg-white/70">
            <div
                className="absolute inset-0"
                style={{
                    backgroundImage:
                        'linear-gradient(to right, rgba(148,163,184,0.08) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.08) 1px, transparent 1px)',
                    backgroundSize: '60px 60px',
                }}
            />
            <div className="relative h-full w-full">
                {placed.map((table) => {
                    if (!table.position) {
                        return null;
                    }
                    if (applyFilter && !stateFilter.has(table.state)) {
                        return null;
                    }
                    const style = {
                        left: `${table.position.x}%`,
                        top: `${table.position.y}%`,
                        width: `${table.position.w}%`,
                        height: `${table.position.h}%`,
                        transform: table.position.rotation ? `rotate(${table.position.rotation}deg)` : undefined,
                        pointerEvents: interactive ? 'auto' : 'none',
                        zIndex: table.position.z_index ?? 0,
                    } as const;
                    return (
                        <div key={table.id} className="absolute" style={style}>
                            {renderTile(table)}
                        </div>
                    );
                })}
            </div>
        </div>
    );

    const renderGridMap = () => {
        if (!layout) {
            return renderAbsoluteMap();
        }
        const templateStyle = {
            gridTemplateColumns: `repeat(${layout.gridCols}, minmax(48px, 1fr))`,
            gridTemplateRows: `repeat(${layout.gridRows}, minmax(48px, 1fr))`,
        } as const;
        return (
            <div className="relative min-h-[520px] w-full overflow-auto rounded-2xl border border-dashed border-slate-200 bg-white/70 p-3">
                <div
                    className="absolute inset-0"
                    style={{
                        backgroundImage:
                            'linear-gradient(to right, rgba(148,163,184,0.08) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.08) 1px, transparent 1px)',
                        backgroundSize: '48px 48px',
                    }}
                />
                <div className="relative h-full w-full">
                    <div className="grid h-full w-full gap-2" style={templateStyle}>
                        {gridPlacements.map((table) => {
                            if (applyFilter && !stateFilter.has(table.state)) {
                                return null;
                            }
                            const grid = table.position?.grid;
                            if (!grid) {
                                return null;
                            }
                            return (
                                <div
                                    key={table.id}
                                    className="relative"
                                    style={{
                                        gridColumn: `${grid.x} / span ${grid.w ?? 1}`,
                                        gridRow: `${grid.y} / span ${grid.h ?? 1}`,
                                    }}
                                >
                                    {renderTile(table)}
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        );
    };

    return (
        <div className={cn('relative rounded-3xl border border-slate-200 bg-gradient-to-br from-slate-50 via-white to-slate-100 p-4 shadow-inner', className)}>
            {useGridLayout ? renderGridMap() : renderAbsoluteMap()}
        </div>
    );
}

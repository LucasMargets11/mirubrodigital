import type { Table, TablesLayout, TableStatusMap } from './types';

export const TABLES_LOCAL_STORAGE_KEY = 'resto_tables_layout_v1';

export const mockTables: Table[] = Array.from({ length: 20 }).map((_, index) => {
    const id = `table-${index + 1}`;
    return {
        id,
        code: `M${index + 1}`,
        name: `Mesa ${index + 1}`,
        capacity: 2 + (index % 4) * 2,
        is_enabled: index % 7 !== 0,
    } satisfies Table;
});

export const mockLayout: TablesLayout = {
    gridCols: 12,
    gridRows: 8,
    placements: mockTables.map((table, index) => ({
        tableId: table.id,
        x: (index % 6) * 2 + 1,
        y: Math.floor(index / 6) * 2 + 1,
        w: 1,
        h: 1,
        rotation: 0,
        tableCode: table.code,
    })),
};

export const mockStatuses: TableStatusMap = mockTables.reduce<TableStatusMap>((acc, table, index) => {
    if (!table.is_enabled) {
        acc[table.id] = { status: 'DISABLED' };
        return acc;
    }
    if (index % 5 === 0) {
        acc[table.id] = {
            status: 'OCCUPIED',
            orderId: `order-${100 + index}`,
            orderNumber: 100 + index,
            orderStatus: 'open',
            orderStatusLabel: 'Abierta',
        };
        return acc;
    }
    acc[table.id] = { status: 'FREE' };
    return acc;
}, {});

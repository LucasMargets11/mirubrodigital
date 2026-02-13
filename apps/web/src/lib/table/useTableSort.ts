/**
 * Hook para manejo de ordenamiento de tablas
 * Soporta persistencia en URL y ordenamiento client-side/server-side
 */
import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';

export type SortDirection = 'asc' | 'desc';

export interface SortConfig {
    sortKey: string;
    sortDir: SortDirection;
}

export interface UseTableSortOptions {
    /**
     * Clave inicial de ordenamiento
     */
    defaultSortKey?: string;
    /**
     * Dirección inicial
     */
    defaultSortDir?: SortDirection;
    /**
     * Si true, persiste en URL (query params)
     */
    persistInUrl?: boolean;
    /**
     * Callback cuando cambia el ordenamiento (para server-side)
     */
    onSortChange?: (sortKey: string, sortDir: SortDirection) => void;
}

export interface UseTableSortReturn {
    sortKey: string | null;
    sortDir: SortDirection;
    onToggleSort: (key: string) => void;
    getSortProps: (key: string) => {
        'aria-sort': 'ascending' | 'descending' | 'none';
        onClick: () => void;
        className: string;
    };
}

export function useTableSort(options: UseTableSortOptions = {}): UseTableSortReturn {
    const {
        defaultSortKey = null,
        defaultSortDir = 'asc',
        persistInUrl = true,
        onSortChange,
    } = options;

    const router = useRouter();
    const pathname = usePathname();
    const searchParams = useSearchParams();

    // Leer desde URL si está habilitado
    const currentSortKey = persistInUrl
        ? (searchParams.get('ordering')?.replace(/^-/, '') ?? defaultSortKey)
        : defaultSortKey;

    const currentSortDir: SortDirection = persistInUrl
        ? (searchParams.get('ordering')?.startsWith('-') ? 'desc' : 'asc')
        : defaultSortDir;

    const onToggleSort = useCallback(
        (key: string) => {
            let newDir: SortDirection = 'asc';

            if (currentSortKey === key) {
                // Alternar dirección
                newDir = currentSortDir === 'asc' ? 'desc' : 'asc';
            }

            if (persistInUrl) {
                const params = new URLSearchParams(searchParams.toString());
                const ordering = newDir === 'desc' ? `-${key}` : key;
                params.set('ordering', ordering);
                router.push(`${pathname}?${params.toString()}`, { scroll: false });
            }

            onSortChange?.(key, newDir);
        },
        [currentSortKey, currentSortDir, persistInUrl, searchParams, pathname, router, onSortChange]
    );

    const getSortProps = useCallback(
        (key: string) => {
            const isActive = currentSortKey === key;
            const ariaSort = isActive
                ? currentSortDir === 'asc'
                    ? ('ascending' as const)
                    : ('descending' as const)
                : ('none' as const);

            return {
                'aria-sort': ariaSort,
                onClick: () => onToggleSort(key),
                className: 'cursor-pointer select-none hover:bg-slate-50 transition-colors',
            };
        },
        [currentSortKey, currentSortDir, onToggleSort]
    );

    return {
        sortKey: currentSortKey,
        sortDir: currentSortDir,
        onToggleSort,
        getSortProps,
    };
}

/**
 * Cliente-side sorting para arrays
 */
export type SortType = 'string' | 'number' | 'date' | 'boolean';

export interface ColumnConfig<T> {
    accessor: keyof T | ((item: T) => any);
    sortType?: SortType;
    customComparator?: (a: T, b: T) => number;
}

export function sortArray<T>(
    array: T[],
    sortKey: string | null,
    sortDir: SortDirection,
    columns: Record<string, ColumnConfig<T>>
): T[] {
    if (!sortKey || !columns[sortKey]) return array;

    const column = columns[sortKey];
    const { accessor, sortType = 'string', customComparator } = column;

    const sorted = [...array].sort((a, b) => {
        if (customComparator) {
            return customComparator(a, b);
        }

        const aValue = typeof accessor === 'function' ? accessor(a) : a[accessor];
        const bValue = typeof accessor === 'function' ? accessor(b) : b[accessor];

        // Nulls last
        if (aValue == null && bValue == null) return 0;
        if (aValue == null) return 1;
        if (bValue == null) return -1;

        switch (sortType) {
            case 'number':
                return Number(aValue) - Number(bValue);
            case 'date':
                return new Date(aValue as any).getTime() - new Date(bValue as any).getTime();
            case 'boolean':
                return (aValue ? 1 : 0) - (bValue ? 1 : 0);
            case 'string':
            default:
                return String(aValue).localeCompare(String(bValue), 'es-AR', { sensitivity: 'base' });
        }
    });

    return sortDir === 'desc' ? sorted.reverse() : sorted;
}

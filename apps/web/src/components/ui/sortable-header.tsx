/**
 * Componente de header de tabla ordenable
 */
import { type ComponentProps } from 'react';

interface SortableHeaderProps extends ComponentProps<'th'> {
    label: string;
    sortKey?: string;
    activeSortKey?: string | null;
    sortDir?: 'asc' | 'desc';
    onToggleSort?: (key: string) => void;
}

export function SortableHeader({
    label,
    sortKey,
    activeSortKey,
    sortDir,
    onToggleSort,
    className = '',
    ...props
}: SortableHeaderProps) {
    const isSortable = sortKey && onToggleSort;
    const isActive = sortKey === activeSortKey;

    const handleClick = () => {
        if (isSortable) {
            onToggleSort(sortKey);
        }
    };

    return (
        <th
            className={`px-3 py-2 ${isSortable ? 'cursor-pointer select-none hover:bg-slate-50 transition-colors' : ''} ${className}`}
            onClick={handleClick}
            aria-sort={isActive ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
            {...props}
        >
            <div className="flex items-center gap-2">
                <span>{label}</span>
                {isSortable && (
                    <span className="inline-flex flex-col">
                        {isActive ? (
                            sortDir === 'asc' ? (
                                <svg className="h-4 w-4 text-slate-900" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                                </svg>
                            ) : (
                                <svg className="h-4 w-4 text-slate-900" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                </svg>
                            )
                        ) : (
                            <svg className="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
                            </svg>
                        )}
                    </span>
                )}
            </div>
        </th>
    );
}

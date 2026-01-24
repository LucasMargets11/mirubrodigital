"use client";

import { type SVGProps } from 'react';

import { cn } from '@/lib/utils';

const STOCK_STATUS_OPTIONS = [
    { value: '', label: 'Todos los estados' },
    { value: 'low', label: 'Stock bajo' },
    { value: 'out', label: 'Sin stock' },
    { value: 'ok', label: 'En orden' },
] as const;

type StockStatusSelectProps = {
    value: string;
    onValueChange: (value: string) => void;
    className?: string;
};

export function StockStatusSelect({ value, onValueChange, className }: StockStatusSelectProps) {
    return (
        <div className={cn('relative inline-flex w-full min-w-[10rem] items-center', className)}>
            <select
                aria-label="Estado de stock"
                value={value}
                onChange={(event) => onValueChange(event.target.value)}
                className={cn(
                    'peer h-10 w-full appearance-none rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition focus:outline-none focus:ring-2 focus:ring-slate-900/20 focus:ring-offset-2 focus:ring-offset-white hover:border-slate-900/40 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:focus:ring-white/30',
                    !value && 'text-slate-400',
                )}
            >
                {STOCK_STATUS_OPTIONS.map((option) => (
                    <option key={option.value || 'all'} value={option.value}>
                        {option.label}
                    </option>
                ))}
            </select>
            <ChevronDownIcon
                className="pointer-events-none absolute right-3 h-4 w-4 text-slate-400 transition duration-200 peer-focus:rotate-180"
                aria-hidden="true"
            />
        </div>
    );
}

function ChevronDownIcon(props: SVGProps<SVGSVGElement>) {
    return (
        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" {...props}>
            <path d="M5 7.5l5 5 5-5" />
        </svg>
    );
}

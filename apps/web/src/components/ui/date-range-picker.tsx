'use client';

import type { ChangeEvent } from 'react';

import { cn } from '@/lib/utils';

export type DateRange = {
    from?: Date;
    to?: Date;
};

export type DateRangePickerProps = {
    from?: Date;
    to?: Date;
    onSelect?: (range?: DateRange) => void;
    className?: string;
    labels?: {
        from?: string;
        to?: string;
    };
};

const formatInputValue = (value?: Date) => (value ? value.toISOString().split('T')[0] : '');

export function DateRangePicker({ from, to, onSelect, className, labels }: DateRangePickerProps) {
    const handleChange = (field: 'from' | 'to') => (event: ChangeEvent<HTMLInputElement>) => {
        const value = event.target.value;
        const nextDate = value ? new Date(value) : undefined;
        const nextRange: DateRange = {
            from: field === 'from' ? nextDate : from,
            to: field === 'to' ? nextDate : to,
        };
        if (!nextRange.from && !nextRange.to) {
            onSelect?.(undefined);
            return;
        }
        onSelect?.(nextRange);
    };

    return (
        <div className={cn('flex items-center gap-3 rounded-2xl border border-slate-200 bg-white/80 px-4 py-2 shadow-sm', className)}>
            <DateInput
                label={labels?.from ?? 'Desde'}
                value={formatInputValue(from)}
                onChange={handleChange('from')}
            />
            <span className="text-sm font-semibold text-slate-400">—</span>
            <DateInput
                label={labels?.to ?? 'Hasta'}
                value={formatInputValue(to)}
                onChange={handleChange('to')}
            />
        </div>
    );
}

type DateInputProps = {
    label: string;
    value: string;
    onChange: (event: ChangeEvent<HTMLInputElement>) => void;
};

function DateInput({ label, value, onChange }: DateInputProps) {
    return (
        <label className="flex flex-col text-xs font-semibold uppercase tracking-wide text-slate-500">
            {label}
            <input
                type="date"
                value={value}
                onChange={onChange}
                className="mt-1 rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 shadow-inner focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
        </label>
    );
}

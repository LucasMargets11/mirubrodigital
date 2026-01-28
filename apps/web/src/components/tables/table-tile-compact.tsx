"use client";

import type { CSSProperties } from 'react';

import { cn } from '@/lib/utils';

type TableTileCompactProps = {
    code: string;
    status: 'FREE' | 'OCCUPIED' | 'PAUSED' | 'DISABLED';
    selected?: boolean;
    highlight?: boolean;
    disabled?: boolean;
    orderNumber?: number | null;
    orderCode?: string | null;
    tooltip?: string;
    onSelect?: () => void;
    className?: string;
    style?: CSSProperties;
};

const STATUS_META: Record<string, { border: string; background: string; text: string; dot: string; label: string; shadow: string }> = {
    FREE: {
        border: 'border-emerald-200',
        background: 'bg-white',
        text: 'text-emerald-800',
        dot: 'bg-emerald-500',
        label: 'Libre',
        shadow: 'shadow-[0_4px_14px_rgba(16,185,129,0.15)]',
    },
    OCCUPIED: {
        border: 'border-rose-200',
        background: 'bg-rose-50',
        text: 'text-rose-800',
        dot: 'bg-rose-500',
        label: 'Ocupada',
        shadow: 'shadow-[0_4px_18px_rgba(244,63,94,0.20)]',
    },
    PAUSED: {
        border: 'border-amber-200',
        background: 'bg-amber-50',
        text: 'text-amber-800',
        dot: 'bg-amber-500',
        label: 'Pausada',
        shadow: 'shadow-[0_4px_18px_rgba(245,158,11,0.2)]',
    },
    DISABLED: {
        border: 'border-slate-200',
        background: 'bg-slate-100',
        text: 'text-slate-500',
        dot: 'bg-slate-400',
        label: 'Deshabilitada',
        shadow: 'shadow-none',
    },
};

export function TableTileCompact({
    code,
    status,
    selected = false,
    highlight = false,
    disabled = false,
    orderNumber,
    orderCode,
    tooltip,
    onSelect,
    className,
    style,
}: TableTileCompactProps) {
    const meta = STATUS_META[status] ?? STATUS_META.FREE;
    const badgeLabel = meta.label;
    const orderBadge = orderNumber ? `#${orderNumber}` : orderCode ? `#${orderCode.slice(0, 4)}` : null;

    return (
        <button
            type="button"
            title={tooltip}
            style={style}
            onClick={onSelect}
            disabled={disabled}
            className={cn(
                'flex h-full min-h-[48px] w-full min-w-[56px] flex-col items-center justify-center rounded-xl border px-2 text-center text-[11px] font-semibold uppercase tracking-wide transition',
                meta.border,
                meta.background,
                meta.text,
                meta.shadow,
                disabled ? 'cursor-not-allowed opacity-50' : 'hover:-translate-y-0.5 hover:shadow-lg',
                selected ? 'ring-2 ring-slate-900 ring-offset-2 ring-offset-white' : '',
                highlight && !selected ? 'ring-2 ring-amber-400 ring-offset-2 ring-offset-white' : '',
                className
            )}
        >
            <span className="text-sm font-bold tracking-tight text-slate-900">{code}</span>
            <span className="flex items-center gap-1 text-[10px] font-semibold normal-case text-slate-500">
                <span className={`h-2 w-2 rounded-full ${meta.dot}`} aria-hidden />
                {badgeLabel}
            </span>
            {orderBadge ? <span className="text-[10px] text-slate-400">{orderBadge}</span> : null}
        </button>
    );
}

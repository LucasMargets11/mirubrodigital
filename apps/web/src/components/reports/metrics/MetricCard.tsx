'use client';

import { MetricTone, formatDeltaLabel } from './utils';

type MetricCardProps = {
    title: string;
    value: string;
    deltaPct: number | null;
    subtitle?: string;
    tone: MetricTone;
    loading?: boolean;
};

type ArrowDirection = 'up' | 'down' | 'flat';

const toneStyles: Record<MetricTone, { text: string; badge: string }> = {
    positive: { text: 'text-emerald-600', badge: 'bg-emerald-50' },
    negative: { text: 'text-rose-600', badge: 'bg-rose-50' },
    neutral: { text: 'text-slate-500', badge: 'bg-slate-100' },
};

export function MetricCard({ title, value, deltaPct, subtitle = 'vs período anterior', tone, loading = false }: MetricCardProps) {
    const direction: ArrowDirection = deltaPct === null ? 'flat' : deltaPct > 0 ? 'up' : deltaPct < 0 ? 'down' : 'flat';
    const toneClass = toneStyles[tone] ?? toneStyles.neutral;

    return (
        <article className="rounded-3xl border border-slate-200 bg-white/90 p-4 shadow-sm">
            <p className="text-sm font-medium text-slate-500">{title}</p>
            <div className="mt-3 min-h-[2.8rem]">
                {loading ? (
                    <div className="h-7 w-32 animate-pulse rounded-full bg-slate-100" />
                ) : (
                    <p className="text-2xl font-semibold text-slate-900">{value}</p>
                )}
            </div>
            <div className="mt-3 flex items-center gap-2 text-sm">
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ${toneClass.badge} ${toneClass.text}`}>
                    <ArrowIcon direction={direction} />
                    {formatDeltaLabel(deltaPct)}
                </span>
                <span className="text-slate-500">{subtitle}</span>
            </div>
        </article>
    );
}

function ArrowIcon({ direction }: { direction: ArrowDirection }) {
    if (direction === 'flat') {
        return (
            <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden="true">
                <path d="M3 8h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
        );
    }
    const isUp = direction === 'up';
    return (
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden="true">
            <path
                d={isUp ? 'M8 4l4 6H4l4-6z' : 'M8 12l-4-6h8l-4 6z'}
                fill="currentColor"
            />
        </svg>
    );
}

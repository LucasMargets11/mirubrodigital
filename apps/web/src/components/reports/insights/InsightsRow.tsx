'use client';

import { MetricTone } from '../metrics/utils';

export type Insight = {
    id: string;
    text: string;
    tone: MetricTone;
};

type InsightsRowProps = {
    insights: Insight[];
    loading?: boolean;
};

const toneStyles: Record<MetricTone, { dot: string; text: string; bg: string }> = {
    positive: { dot: 'bg-emerald-500', text: 'text-emerald-700', bg: 'bg-emerald-50' },
    negative: { dot: 'bg-rose-500', text: 'text-rose-700', bg: 'bg-rose-50' },
    neutral: { dot: 'bg-slate-400', text: 'text-slate-700', bg: 'bg-slate-100' },
};

export function InsightsRow({ insights, loading = false }: InsightsRowProps) {
    if (!insights.length && !loading) {
        return null;
    }

    const items = loading ? placeholderInsights : insights;

    return (
        <div className="grid gap-3 md:grid-cols-2">
            {items.map((insight) => (
                <div
                    key={insight.id}
                    className={`flex items-start gap-3 rounded-3xl border border-slate-200 p-4 ${toneStyles[insight.tone].bg}`}
                >
                    <span className={`mt-1 h-3 w-3 rounded-full ${toneStyles[insight.tone].dot}`} />
                    <p className={`text-sm font-medium ${toneStyles[insight.tone].text}`}>
                        {loading ? <span className="block h-4 w-3/4 animate-pulse rounded bg-white/60" /> : insight.text}
                    </p>
                </div>
            ))}
        </div>
    );
}

const placeholderInsights: Insight[] = [
    { id: 'placeholder-1', text: '', tone: 'neutral' },
    { id: 'placeholder-2', text: '', tone: 'neutral' },
];

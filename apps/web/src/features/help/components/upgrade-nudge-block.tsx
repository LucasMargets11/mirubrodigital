'use client';

import type { UpgradeNudge } from '../types';

interface UpgradeNudgeBlockProps {
    nudge: UpgradeNudge;
    onNavigate?: (href: string) => void;
}

export function UpgradeNudgeBlock({ nudge, onNavigate }: UpgradeNudgeBlockProps) {
    return (
        <div className="rounded-xl border border-brand-100 bg-brand-50 px-5 py-4">
            <p className="text-[15px] font-semibold text-brand-800">{nudge.headline}</p>
            <p className="mt-1.5 text-sm leading-relaxed text-brand-700">{nudge.body}</p>
            <button
                type="button"
                onClick={() => onNavigate?.(nudge.ctaHref)}
                className="mt-3 text-sm font-medium text-brand-700 underline underline-offset-2 hover:text-brand-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            >
                {nudge.ctaLabel} →
            </button>
        </div>
    );
}

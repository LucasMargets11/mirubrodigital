'use client';

import type { TipItem, UpgradeNudge } from '../types';
import { UpgradeNudgeBlock } from './upgrade-nudge-block';

interface TipsTabProps {
    items: TipItem[];
    nudge: UpgradeNudge | null;
    onNavigate?: (href: string) => void;
}

export function TipsTab({ items, nudge, onNavigate }: TipsTabProps) {
    return (
        <div className="space-y-5">
            <div className="space-y-1">
                {items.map((item) => (
                    <div
                        key={item.id}
                        className="flex items-start gap-3.5 rounded-xl px-4 py-3"
                    >
                        <span className="mt-0.5 flex-shrink-0 text-base">💡</span>
                        <div className="min-w-0 flex-1">
                            <p className="text-sm leading-relaxed text-slate-700">{item.text}</p>
                            {item.ctaLabel && item.ctaHref && (
                                <button
                                    type="button"
                                    onClick={() => onNavigate?.(item.ctaHref!)}
                                    className="mt-1.5 text-sm font-medium text-brand-700 hover:text-brand-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                                >
                                    {item.ctaLabel}
                                </button>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            {nudge && <UpgradeNudgeBlock nudge={nudge} onNavigate={onNavigate} />}
        </div>
    );
}

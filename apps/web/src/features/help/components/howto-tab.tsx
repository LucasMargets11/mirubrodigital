'use client';

import type { HowToItem, UpgradeNudge } from '../types';
import { UpgradeNudgeBlock } from './upgrade-nudge-block';

interface HowToTabProps {
    items: HowToItem[];
    nudge: UpgradeNudge | null;
    onNavigate?: (href: string) => void;
}

export function HowToTab({ items, nudge, onNavigate }: HowToTabProps) {
    return (
        <div className="space-y-5">
            <div className="space-y-1.5">
                {items.map((item) => (
                    <button
                        key={item.id}
                        type="button"
                        onClick={() => onNavigate?.(item.href)}
                        className="flex w-full items-start gap-3.5 rounded-xl px-4 py-3.5 text-left transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                    >
                        <span className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700">
                            ?
                        </span>
                        <div className="min-w-0 flex-1">
                            <p className="text-[15px] font-medium leading-snug text-slate-900">{item.title}</p>
                            <p className="mt-1 text-sm leading-relaxed text-slate-500">{item.description}</p>
                        </div>
                        <span className="mt-1 flex-shrink-0 text-sm text-slate-400">→</span>
                    </button>
                ))}
            </div>

            {nudge && <UpgradeNudgeBlock nudge={nudge} onNavigate={onNavigate} />}
        </div>
    );
}

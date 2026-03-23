'use client';

import { useState, useId } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { FAQItem } from '../_data';

export function FAQAccordionItem({ question, answer }: FAQItem) {
    const [open, setOpen] = useState(false);
    const id = useId();
    const headingId = `${id}-heading`;
    const panelId = `${id}-panel`;

    return (
        <div className="border-b border-slate-200 last:border-b-0">
            <h3>
                <button
                    id={headingId}
                    type="button"
                    onClick={() => setOpen((prev) => !prev)}
                    aria-expanded={open}
                    aria-controls={panelId}
                    className="flex w-full items-center justify-between gap-4 py-4 text-left text-sm font-medium text-slate-900 transition-colors hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 sm:text-base"
                >
                    <span>{question}</span>
                    <ChevronDown
                        className={cn(
                            'h-4 w-4 shrink-0 text-slate-400 transition-transform duration-200',
                            open && 'rotate-180 text-brand-500',
                        )}
                    />
                </button>
            </h3>
            <div
                id={panelId}
                role="region"
                aria-labelledby={headingId}
                className={cn(
                    'grid transition-[grid-template-rows] duration-200',
                    open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
                )}
            >
                <div className="overflow-hidden">
                    <p className="pb-4 text-sm leading-relaxed text-slate-600">
                        {answer}
                    </p>
                </div>
            </div>
        </div>
    );
}

"use client";

import { cn } from '@/lib/utils';

export type SectionView = {
    key: string;
    label: string;
};

type SectionViewSwitcherProps = {
    views: SectionView[];
    activeKey: string;
    onChange: (key: string) => void;
    /** aria-label for the group */
    ariaLabel?: string;
    className?: string;
};

/**
 * Lightweight view switcher for internal section views.
 * Renders as a segmented control / pill group — visually distinct
 * from ModuleTabs and the sidebar. Used inside sections like
 * Gastos (Fijos / Puntuales / Reposiciones / Respaldo Impositivo).
 */
export function SectionViewSwitcher({
    views,
    activeKey,
    onChange,
    ariaLabel = 'Selector de vista',
    className,
}: SectionViewSwitcherProps) {
    return (
        <div
            role="tablist"
            aria-label={ariaLabel}
            className={cn(
                'inline-flex gap-1 rounded-lg bg-slate-100 p-1',
                className
            )}
        >
            {views.map((view) => {
                const isActive = view.key === activeKey;
                return (
                    <button
                        key={view.key}
                        type="button"
                        role="tab"
                        aria-selected={isActive}
                        tabIndex={isActive ? 0 : -1}
                        onClick={() => onChange(view.key)}
                        className={cn(
                            'rounded-md px-4 py-2 text-sm font-medium transition-all',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
                            isActive
                                ? 'bg-white text-slate-900 shadow-sm'
                                : 'text-slate-500 hover:text-slate-700'
                        )}
                    >
                        {view.label}
                    </button>
                );
            })}
        </div>
    );
}

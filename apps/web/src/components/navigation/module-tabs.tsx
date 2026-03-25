"use client";

import Link from 'next/link';
import type { Route } from 'next';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';

export type ModuleTab = {
    href: string;
    label: string;
    /** When true, only exact pathname match triggers active state */
    exact?: boolean;
};

type ModuleTabsProps = {
    tabs: ModuleTab[];
    /** aria-label for the <nav> element */
    ariaLabel?: string;
    className?: string;
};

/**
 * Secondary navigation for modules (Finanzas, Stock, Reportes, etc.).
 * Renders as underline-style tabs — visually lighter than the sidebar.
 * Only one level of tabs, driven by the current pathname.
 */
export function ModuleTabs({ tabs, ariaLabel = 'Navegación del módulo', className }: ModuleTabsProps) {
    const pathname = usePathname();

    if (!tabs.length) return null;

    return (
        <nav
            aria-label={ariaLabel}
            className={cn('border-b border-slate-200', className)}
            role="tablist"
        >
            <div className="flex gap-0 overflow-x-auto scrollbar-hide -mb-px">
                {tabs.map((tab) => {
                    const isActive = tab.exact
                        ? pathname === tab.href
                        : pathname?.startsWith(tab.href);

                    return (
                        <Link
                            key={tab.href}
                            href={tab.href as Route}
                            role="tab"
                            aria-selected={isActive ?? false}
                            aria-current={isActive ? 'page' : undefined}
                            tabIndex={isActive ? 0 : -1}
                            className={cn(
                                'relative whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 rounded-t-sm',
                                isActive
                                    ? 'border-slate-900 text-slate-900'
                                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                            )}
                        >
                            {tab.label}
                        </Link>
                    );
                })}
            </div>
        </nav>
    );
}

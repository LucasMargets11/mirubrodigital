"use client";

import { ReactNode } from 'react';
import Link from 'next/link';
import type { Route } from 'next';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export type BreadcrumbItem = {
    label: string;
    href?: string;
};

type AppPageHeaderProps = {
    title: string;
    description?: string;
    breadcrumbs?: BreadcrumbItem[];
    actions?: ReactNode;
    className?: string;
};

/**
 * Contextual header for app pages.
 * Renders breadcrumbs + title + optional description and action buttons.
 * Replaces the old top navbar — no global navigation here.
 */
export function AppPageHeader({
    title,
    description,
    breadcrumbs,
    actions,
    className,
}: AppPageHeaderProps) {
    return (
        <header className={cn('space-y-1', className)}>
            {/* Breadcrumbs */}
            {breadcrumbs && breadcrumbs.length > 0 && (
                <nav
                    aria-label="Navegación de contexto"
                    className="flex items-center gap-1.5 text-sm"
                >
                    {breadcrumbs.map((item, index) => {
                        const isLast = index === breadcrumbs.length - 1;
                        return (
                            <span key={index} className="flex items-center gap-1.5">
                                {index > 0 && (
                                    <ChevronRight
                                        className="h-3.5 w-3.5 text-slate-400 shrink-0"
                                        aria-hidden="true"
                                    />
                                )}
                                {!isLast && item.href ? (
                                    <Link
                                        href={item.href as Route}
                                        className="text-slate-500 hover:text-slate-700 transition-colors truncate max-w-[180px]"
                                    >
                                        {item.label}
                                    </Link>
                                ) : (
                                    <span
                                        className={cn(
                                            'truncate max-w-[200px]',
                                            isLast
                                                ? 'text-slate-700 font-medium'
                                                : 'text-slate-500'
                                        )}
                                        aria-current={isLast ? 'page' : undefined}
                                    >
                                        {item.label}
                                    </span>
                                )}
                            </span>
                        );
                    })}
                </nav>
            )}

            {/* Title row + actions */}
            <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                    <h1 className="text-2xl font-bold tracking-tight text-slate-900 truncate">
                        {title}
                    </h1>
                    {description && (
                        <p className="mt-0.5 text-sm text-slate-500 line-clamp-2">
                            {description}
                        </p>
                    )}
                </div>
                {actions && (
                    <div className="flex items-center gap-2 shrink-0">{actions}</div>
                )}
            </div>
        </header>
    );
}

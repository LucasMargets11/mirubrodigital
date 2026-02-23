"use client";

import { ReactNode } from 'react';
import Link from 'next/link';
import type { Route } from 'next';
import { ChevronRight } from 'lucide-react';

import { cn } from '@/lib/utils';
import { MobileMenuButton } from './mobile-menu-button';

type BreadcrumbItem = {
    label: string;
    href: Route;
};

type PageHeaderProps = {
    title: string;
    description?: string;
    breadcrumbs?: BreadcrumbItem[];
    actions?: ReactNode;
    showMobileMenu?: boolean;
    className?: string;
};

export function PageHeader({ 
    title, 
    description, 
    breadcrumbs, 
    actions, 
    showMobileMenu = true,
    className 
}: PageHeaderProps) {
    return (
        <div className={cn('space-y-3', className)}>
            {/* Breadcrumbs with mobile menu */}
            <div className="flex items-center justify-between gap-4">
                {breadcrumbs && breadcrumbs.length > 0 ? (
                    <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm flex-1 min-w-0">
                        {breadcrumbs.map((item, index) => {
                            const isLast = index === breadcrumbs.length - 1;
                            
                            return (
                                <div key={index} className="flex items-center gap-2">
                                    {index > 0 && (
                                        <ChevronRight className="h-4 w-4 text-slate-400" aria-hidden="true" />
                                    )}
                                    {!isLast ? (
                                        <Link
                                            href={item.href}
                                            className="text-slate-600 hover:text-slate-900 transition-colors"
                                        >
                                            {item.label}
                                        </Link>
                                    ) : (
                                        <span className="text-slate-900 font-medium">
                                            {item.label}
                                        </span>
                                    )}
                                </div>
                            );
                        })}
                    </nav>
                ) : (
                    <div className="flex-1" />
                )}
                {showMobileMenu && <MobileMenuButton />}
            </div>

            {/* Title & Actions */}
            <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                    <h1 className="text-2xl font-bold text-slate-900 truncate">
                        {title}
                    </h1>
                    {description && (
                        <p className="mt-1 text-sm text-slate-600">
                            {description}
                        </p>
                    )}
                </div>
                {actions && (
                    <div className="flex items-center gap-2 shrink-0">
                        {actions}
                    </div>
                )}
            </div>
        </div>
    );
}

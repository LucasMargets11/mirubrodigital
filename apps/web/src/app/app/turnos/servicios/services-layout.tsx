"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ReactNode } from 'react';

import { AppPageHeader } from '@/components/navigation/app-page-header';
import { cn } from '@/lib/utils';

type ServicesLayoutProps = {
    children: ReactNode;
};

export function ServicesLayout({ children }: ServicesLayoutProps) {
    const pathname = usePathname();
    const isCategoriesRoute = pathname?.includes('/categorias');

    return (
        <section className="space-y-4">
            <AppPageHeader
                title="Servicios"
                description={
                    isCategoriesRoute
                        ? 'Administrá las categorías de tus servicios de Turnos.'
                        : 'Servicios que tus clientes pueden reservar, con duración, precio y seña.'
                }
            />
            <nav aria-label="Secciones de Servicios" className="border-b border-slate-200">
                <div className="flex gap-0 -mb-px">
                    <Link
                        href="/app/turnos/servicios"
                        className={cn(
                            'border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 rounded-t-sm',
                            !isCategoriesRoute
                                ? 'border-slate-900 text-slate-900'
                                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                        )}
                        aria-current={!isCategoriesRoute ? 'page' : undefined}
                    >
                        Servicios
                    </Link>
                    <Link
                        href="/app/turnos/servicios/categorias"
                        className={cn(
                            'border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 rounded-t-sm',
                            isCategoriesRoute
                                ? 'border-slate-900 text-slate-900'
                                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                        )}
                        aria-current={isCategoriesRoute ? 'page' : undefined}
                    >
                        Categorías
                    </Link>
                </div>
            </nav>

            {children}
        </section>
    );
}

"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ReactNode } from 'react';

import { AppPageHeader } from '@/components/navigation/app-page-header';
import { cn } from '@/lib/utils';

type ProductsLayoutProps = {
    children: ReactNode;
    canManage: boolean;
    canCreate: boolean;
    canViewQuotes?: boolean;
    canCreateQuotes?: boolean;
};

export function ProductsLayout({ children, canManage, canCreate }: ProductsLayoutProps) {
    const pathname = usePathname();
    const isCategoriesRoute = pathname?.includes('/categorias');
    
    return (
        <section className="space-y-4">
            <AppPageHeader
                title="Productos"
                description={
                    isCategoriesRoute
                        ? 'Administrá las categorías de tu catálogo.'
                        : 'Catálogo de productos y servicios del negocio.'
                }
            />
            <nav aria-label="Secciones de Productos" className="border-b border-slate-200">
                <div className="flex gap-0 -mb-px">
                    <Link
                        href="/app/gestion/productos"
                        className={cn(
                            'border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 rounded-t-sm',
                            !isCategoriesRoute
                                ? 'border-slate-900 text-slate-900'
                                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                        )}
                        aria-current={!isCategoriesRoute ? 'page' : undefined}
                    >
                        Productos
                    </Link>
                    <Link
                        href="/app/gestion/productos/categorias"
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

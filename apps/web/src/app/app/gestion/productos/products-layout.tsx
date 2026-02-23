"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ReactNode } from 'react';

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
            <header className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                        <h2 className="text-2xl font-semibold text-slate-900">Productos</h2>
                        <p className="text-sm text-slate-500">
                            {isCategoriesRoute 
                                ? 'Administrá las categorías de tu catálogo.' 
                                : 'Catálogo de productos y servicios del negocio.'}
                        </p>
                    </div>
                </div>
                <div className="flex gap-2 border-t border-slate-200 pt-3">
                    <Link
                        href="/app/gestion/productos"
                        className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                            !isCategoriesRoute
                                ? 'bg-slate-900 text-white'
                                : 'text-slate-600 hover:bg-slate-100'
                        }`}
                        aria-current={!isCategoriesRoute ? 'page' : undefined}
                    >
                        Productos
                    </Link>
                    <Link
                        href="/app/gestion/productos/categorias"
                        className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                            isCategoriesRoute
                                ? 'bg-slate-900 text-white'
                                : 'text-slate-600 hover:bg-slate-100'
                        }`}
                        aria-current={isCategoriesRoute ? 'page' : undefined}
                    >
                        Categorías
                    </Link>
                </div>
            </header>

            {children}
        </section>
    );
}

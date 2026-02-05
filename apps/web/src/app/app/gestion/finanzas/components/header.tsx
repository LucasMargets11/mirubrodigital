"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';

const tabs = [
    { href: '/app/gestion/finanzas/resumen', label: 'Resumen' },
    { href: '/app/gestion/finanzas/cuentas', label: 'Cuentas' },
    { href: '/app/gestion/finanzas/movimientos', label: 'Movimientos' },
    { href: '/app/gestion/finanzas/gastos', label: 'Gastos' },
    { href: '/app/gestion/finanzas/sueldos', label: 'Sueldos' },
];

export function FinanceTabs() {
    const pathname = usePathname();

    return (
        <div className="flex flex-wrap border-b border-slate-200">
            {tabs.map((tab) => {
                const isActive = pathname?.startsWith(tab.href);
                return (
                    <Link
                        key={tab.href}
                        href={tab.href}
                        className={cn(
                            'border-b-2 px-4 py-2 text-sm font-medium transition-colors hover:text-slate-900',
                            isActive
                                ? 'border-slate-900 text-slate-900'
                                : 'border-transparent text-slate-500 hover:border-slate-300'
                        )}
                    >
                        {tab.label}
                    </Link>
                );
            })}
        </div>
    );
}

export function FinanceHeader() {
    return (
        <div className="flex flex-col gap-1">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">Finanzas Operativas</h1>
            <p className="text-sm text-slate-500">
                Llevá el control de tu caja, bancos y gastos. Recordá que este es un registro interno y no está conectado directamente a los bancos.
            </p>
        </div>
    );
}

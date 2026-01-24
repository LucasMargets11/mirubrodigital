"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { cn } from '@/lib/utils';

const STOCK_TABS = [
    { href: '/app/gestion/stock', label: 'Inventario' },
    { href: '/app/gestion/stock/importar', label: 'Importar' },
    { href: '/app/gestion/stock/valorizacion', label: 'Valorización' },
];

export function StockNav() {
    const pathname = usePathname();

    return (
        <nav className="flex flex-wrap gap-2">
            {STOCK_TABS.map((tab) => (
                <Link
                    key={tab.href}
                    href={tab.href}
                    className={cn(
                        'rounded-full border px-4 py-2 text-sm font-semibold transition',
                        pathname?.startsWith(tab.href)
                            ? 'border-slate-900 bg-slate-900 text-white'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-900 hover:text-slate-900'
                    )}
                >
                    {tab.label}
                </Link>
            ))}
        </nav>
    );
}

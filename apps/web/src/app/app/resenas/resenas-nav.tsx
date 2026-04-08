'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { Route } from 'next';

const TABS: readonly { href: string; label: string; exact?: boolean }[] = [
    { href: '/app/resenas', label: 'Dashboard', exact: true },
    { href: '/app/resenas/qr', label: 'Mi QR' },
    { href: '/app/resenas/feedback', label: 'Feedback' },
    { href: '/app/resenas/configuracion', label: 'Configuración' },
];

export function ResenasNav() {
    const pathname = usePathname();

    function isActive(tab: (typeof TABS)[number]) {
        if (tab.exact) return pathname === tab.href;
        return pathname.startsWith(tab.href);
    }

    return (
        <nav className="flex gap-1 rounded-xl bg-slate-100 p-1">
            {TABS.map((tab) => {
                const active = isActive(tab);
                return (
                    <Link
                        key={tab.href}
                        href={tab.href as Route}
                        className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                            active
                                ? 'bg-white text-slate-900 shadow-sm'
                                : 'text-slate-500 hover:text-slate-700'
                        }`}
                    >
                        {tab.label}
                    </Link>
                );
            })}
        </nav>
    );
}

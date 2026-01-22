'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export type ReportsTab = {
    href: string;
    label: string;
};

type ReportsSubnavProps = {
    tabs: ReportsTab[];
};

export function ReportsSubnav({ tabs }: ReportsSubnavProps) {
    const pathname = usePathname();

    if (!tabs.length) {
        return null;
    }

    return (
        <nav className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 p-1 shadow-inner shadow-white/40">
            {tabs.map((tab) => {
                const active = pathname === tab.href || pathname.startsWith(`${tab.href}/`);
                return (
                    <Link
                        key={tab.href}
                        href={tab.href}
                        className={`rounded-full px-4 py-2 text-sm font-medium transition ${active ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:text-slate-900'
                            }`}
                    >
                        {tab.label}
                    </Link>
                );
            })}
        </nav>
    );
}

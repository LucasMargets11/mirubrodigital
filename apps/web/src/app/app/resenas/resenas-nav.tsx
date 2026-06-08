'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { Route } from 'next';
import { getReviewSettings, getReviewStats } from '@/features/reviews/api';
import type { ReviewConfig, ReviewStats } from '@/features/reviews/types';

type TabDef = {
    href: string;
    label: string;
    exact?: boolean;
    badge?: number;
};

/* ── Base tabs (always visible) ──────────────────────────── */

const BASE_TABS: TabDef[] = [
    { href: '/app/resenas', label: 'Dashboard', exact: true },
    { href: '/app/resenas/qr', label: 'Mi QR' },
];

export function ResenasNav() {
    const pathname = usePathname();
    const [config, setConfig] = useState<ReviewConfig | null>(null);
    const [stats, setStats] = useState<ReviewStats | null>(null);

    const refreshStats = useCallback(() => {
        getReviewStats().then(setStats).catch(() => null);
    }, []);

    useEffect(() => {
        Promise.all([
            getReviewSettings().catch(() => null),
            getReviewStats().catch(() => null),
        ]).then(([c, s]) => {
            setConfig(c);
            setStats(s);
        });
    }, []);

    useEffect(() => {
        const handler = () => refreshStats();
        window.addEventListener('reviews-updated', handler);
        return () => window.removeEventListener('reviews-updated', handler);
    }, [refreshStats]);

    // Re-fetch config + stats when upgrade is confirmed (event from UpgradeSuccessBanner)
    useEffect(() => {
        const handler = () => {
            getReviewSettings().then(setConfig).catch(() => null);
            refreshStats();
        };
        window.addEventListener('reviews-config-changed', handler);
        return () => window.removeEventListener('reviews-config-changed', handler);
    }, [refreshStats]);

    const isReviewsPro = config?.is_reviews_pro ?? false;
    const cartelesAccessible = config?.print_posters_allowed ?? false;
    const feedbackAccessible = config?.smart_filter_allowed ?? false;
    const newCount = stats?.new_reviews ?? 0;
    const isTrial = config?.trial_active ?? false;

    const tabs: TabDef[] = [
        ...BASE_TABS,
        ...(cartelesAccessible
            ? [{ href: '/app/resenas/carteles', label: 'Carteles' }]
            : []),
        {
            href: '/app/resenas/feedback',
            label: 'Feedback',
            badge: feedbackAccessible && newCount > 0 ? newCount : undefined,
        },
        ...(isReviewsPro
            ? [{ href: '/app/resenas/analytics', label: 'Analytics' }]
            : []),
        { href: '/app/resenas/configuracion', label: 'Configuración' },
    ];

    function isActive(tab: TabDef) {
        if (tab.exact) return pathname === tab.href;
        return pathname.startsWith(tab.href);
    }

    return (
        <div className="space-y-2">
            {isTrial && config?.trial_ends_at && (() => {
                const daysLeft = Math.max(0, Math.ceil((new Date(config.trial_ends_at!).getTime() - Date.now()) / 86_400_000));
                return (
                    <div className="flex items-center gap-2 rounded-lg bg-indigo-50 px-3 py-1.5 text-xs text-indigo-700">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span className="font-medium">
                            Trial · {daysLeft === 0 ? 'vence hoy' : `${daysLeft}d restante${daysLeft === 1 ? '' : 's'}`}
                        </span>
                    </div>
                );
            })()}
            <nav className="flex gap-1 rounded-xl bg-slate-100 p-1">
            {tabs.map((tab) => {
                const active = isActive(tab);
                return (
                    <Link
                        key={tab.href}
                        href={tab.href as Route}
                        className={`relative rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                            active
                                ? 'bg-white text-slate-900 shadow-sm'
                                : 'text-slate-500 hover:text-slate-700'
                        }`}
                    >
                        {tab.label}
                        {tab.badge != null && tab.badge > 0 && (
                            <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-blue-600 px-1 text-[10px] font-bold text-white">
                                {tab.badge > 99 ? '99+' : tab.badge}
                            </span>
                        )}
                    </Link>
                );
            })}
        </nav>
        </div>
    );
}

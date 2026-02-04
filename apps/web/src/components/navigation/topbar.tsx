"use client";

import { useMemo, useState, useTransition } from 'react';

import { logout } from '@/lib/auth/client';

const SERVICE_LABELS: Record<string, string> = {
    gestion: 'Gestión Comercial',
    restaurante: 'Restaurante Inteligente',
    menu_qr: 'Menú QR Online',
};

type TopbarProps = {
    userName: string;
    role: string;
    businessName: string;
    subscriptionStatus: string;
    service: string;
};

export function Topbar({ userName, role, businessName, subscriptionStatus, service }: TopbarProps) {
    const [error, setError] = useState<string | null>(null);
    const [isPending, startTransition] = useTransition();

    const initials = useMemo(() => {
        if (!userName) {
            return '??';
        }
        return userName
            .split(' ')
            .filter(Boolean)
            .map((part) => part[0]?.toUpperCase())
            .slice(0, 2)
            .join('');
    }, [userName]);

    const handleLogout = () => {
        setError(null);
        startTransition(async () => {
            try {
                await logout();
            } catch (err) {
                setError('No pudimos cerrar sesión.');
            }
        });
    };

    const statusLabel = subscriptionStatus === 'active' ? 'Plan activo' : 'Plan pendiente';
    const serviceLabel = SERVICE_LABELS[service] ?? service;

    return (
        <header className="flex items-center justify-between border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur">
            <div>
                <p className="text-xs uppercase tracking-wide text-slate-400">{businessName}</p>
                <h2 className="text-lg font-semibold text-slate-800">{statusLabel}</h2>
                <p className="text-xs text-slate-400">{role} · {serviceLabel}</p>
            </div>
            <div className="flex items-center gap-4">
                {error ? <span className="text-xs text-red-500">{error}</span> : null}
                <div className="flex items-center gap-3 rounded-full border border-slate-200 bg-white px-3 py-1.5">
                    <div className="text-right">
                        <p className="text-sm font-medium text-slate-800">{userName}</p>
                        <p className="text-xs text-slate-400">{subscriptionStatus}</p>
                    </div>
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-700">
                        {initials}
                    </div>
                    <button
                        type="button"
                        onClick={handleLogout}
                        className="rounded-full bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
                        disabled={isPending}
                    >
                        Salir
                    </button>
                </div>
            </div>
        </header>
    );
}

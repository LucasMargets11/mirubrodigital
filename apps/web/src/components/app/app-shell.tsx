"use client";

import { ReactNode, useMemo } from 'react';
import { usePathname } from 'next/navigation';

import { Sidebar } from '@/components/navigation/sidebar';
import { Topbar } from '@/components/navigation/topbar';
import { AccessMessage } from '@/components/app/access-message';
import type { Session } from '@/lib/auth/types';

const MENU_QR_ALLOWED_PATHS = [
    '/app',
    '/app/menu',
    '/app/menu/branding',
    '/app/menu/qr',
    '/app/menu/preview',
    '/app/servicios',
    '/app/planes',
    '/app/settings',
];

function pathMatches(pathname: string, allowed: string): boolean {
    if (pathname === allowed) {
        return true;
    }
    return pathname.startsWith(`${allowed}/`);
}

function isMenuQrPathAllowed(pathname: string): boolean {
    return MENU_QR_ALLOWED_PATHS.some((allowed) => pathMatches(pathname, allowed));
}

export function AppShell({ session, children }: { session: Session; children: ReactNode }) {
    const pathname = usePathname() ?? '/app';
    const service = session.current.service;

    const isRestricted = useMemo(() => {
        if (service !== 'menu_qr') {
            return false;
        }
        return !isMenuQrPathAllowed(pathname);
    }, [pathname, service]);

    return (
        <div className="flex min-h-screen bg-slate-50">
            <Sidebar
                businessName={session.current.business.name}
                service={service}
                features={session.features}
                permissions={session.permissions}
            />
            <div className="flex flex-1 flex-col overflow-hidden">
                <Topbar
                    userName={session.user.name}
                    role={session.current.role}
                    businessName={session.current.business.name}
                    subscriptionStatus={session.subscription.status}
                    service={service}
                />
                <main className="flex-1 space-y-6 overflow-y-auto p-6">
                    {isRestricted ? (
                        <AccessMessage
                            title="No disponible en tu plan"
                            description="Esta sección pertenece a otros servicios. Actualizá tu suscripción para habilitarla."
                            hint="Gestioná tu plan desde la sección Servicios."
                        />
                    ) : (
                        children
                    )}
                </main>
            </div>
        </div>
    );
}

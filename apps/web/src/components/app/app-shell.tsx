"use client";

import { ReactNode, useMemo } from 'react';
import { usePathname } from 'next/navigation';

import { Sidebar } from '@/components/navigation/sidebar';
import { AccessMessage } from '@/components/app/access-message';
import { MobileMenuProvider, useMobileMenu } from '@/components/app/mobile-menu-context';
import { MobileMenuButton } from '@/components/app/mobile-menu-button';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetCloseButton } from '@/components/ui/sheet';
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

function AppShellContent({ session, children }: { session: Session; children: ReactNode }) {
    const pathname = usePathname() ?? '/app';
    const service = session.current.service;
    const { isOpen, close } = useMobileMenu();

    const isRestricted = useMemo(() => {
        if (service !== 'menu_qr') {
            return false;
        }
        return !isMenuQrPathAllowed(pathname);
    }, [pathname, service]);

    return (
        <div className="flex h-screen bg-slate-50 overflow-hidden">
            {/* Desktop Sidebar - Hidden on mobile */}
            <div className="hidden md:block">
                <Sidebar
                    businessName={session.current.business.name}
                    branchName={session.current.branch?.name}
                    service={service}
                    features={session.features}
                    permissions={session.permissions}
                    userName={session.user.name}
                    role={session.current.role}
                    subscriptionStatus={session.subscription.status}
                    subscriptionPlan={session.subscription.plan}
                />
            </div>

            {/* Mobile Drawer */}
            <Sheet open={isOpen} onOpenChange={(open) => !open && close()}>
                <SheetContent side="left" className="w-[85vw] max-w-[360px] p-0 flex flex-col">
                    <SheetHeader className="shrink-0">
                        <SheetTitle>Menú</SheetTitle>
                        <SheetCloseButton />
                    </SheetHeader>
                    <div className="flex-1 overflow-hidden">
                        <Sidebar
                            businessName={session.current.business.name}
                            branchName={session.current.branch?.name}
                            service={service}
                            features={session.features}
                            permissions={session.permissions}
                            userName={session.user.name}
                            role={session.current.role}
                            subscriptionStatus={session.subscription.status}
                            subscriptionPlan={session.subscription.plan}
                            isMobile={true}
                            onNavigate={close}
                        />
                    </div>
                </SheetContent>
            </Sheet>

            <div className="flex flex-1 flex-col min-w-0">
                {/* Mobile header with menu button - Only visible on mobile */}
                <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-white shrink-0">
                    <h1 className="text-lg font-semibold text-slate-900">
                        {session.current.business.name}
                    </h1>
                    <MobileMenuButton />
                </div>

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

export function AppShell({ session, children }: { session: Session; children: ReactNode }) {
    return (
        <MobileMenuProvider>
            <AppShellContent session={session}>
                {children}
            </AppShellContent>
        </MobileMenuProvider>
    );
}

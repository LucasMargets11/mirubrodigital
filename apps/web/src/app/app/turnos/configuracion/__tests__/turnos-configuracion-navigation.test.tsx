import { render, screen } from '@testing-library/react';
import type { AnchorHTMLAttributes, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const nav = vi.hoisted(() => ({ pathname: '/app/turnos/configuracion' }));

vi.mock('next/navigation', () => ({
    usePathname: () => nav.pathname,
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));

vi.mock('@/features/resto/hooks', () => ({
    useRestaurantOperationSettings: () => ({ data: undefined }),
    getEffectiveRestaurantOperationSettings: (value: unknown) => value,
}));

vi.mock('@/lib/auth/client', () => ({ logout: vi.fn() }));

vi.mock('@/components/app/subscription-banner', () => ({ SubscriptionBanner: () => null }));

vi.mock('@/components/ui/sheet', () => ({
    Sheet: ({ children }: { children: ReactNode }) => <>{children}</>,
    SheetContent: () => null,
    SheetHeader: () => null,
    SheetTitle: () => null,
    SheetCloseButton: () => null,
}));

import { AppShell } from '@/components/app/app-shell';
import { Sidebar } from '@/components/navigation/sidebar';
import type { Session } from '@/lib/auth/types';

class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
}
Object.defineProperty(globalThis, 'ResizeObserver', { writable: true, value: ResizeObserverMock });

const sidebarProps = {
    businessName: 'Turnos Demo',
    service: 'appointments',
    features: { appointments_core: true, dashboard: true, services: true, settings: true },
    permissions: { manage_users: true, manage_settings: true, view_appointments: true },
    userName: 'Owner Demo',
    role: 'owner',
    subscriptionStatus: 'active',
    subscriptionPlan: 'appointments_base',
} satisfies Parameters<typeof Sidebar>[0];

// Business solo-Turnos: appointments habilitado, menú NO habilitado.
const appointmentsOnlySession = {
    user: { name: 'Owner Demo' },
    current: { service: 'appointments', role: 'owner', business: { id: 1, name: 'Turnos Demo' } },
    services: { enabled: ['appointments'] },
    features: sidebarProps.features,
    permissions: sidebarProps.permissions,
    subscription: { status: 'active', plan: 'appointments_base', reason_code: null, grace_until: null, show_renewal_prompt: false },
} as unknown as Session;

describe('Turnos → Configuración (Mercado Pago) navigation', () => {
    beforeEach(() => {
        nav.pathname = '/app/turnos/configuracion';
    });

    it('sidebar shows Configuración → /app/turnos/configuracion for admins', () => {
        render(<Sidebar {...sidebarProps} />);
        const link = screen.getByRole('link', { name: 'Configuración' });
        expect(link).toHaveAttribute('href', '/app/turnos/configuracion');
    });

    it('sidebar hides Configuración for roles without manage_settings (viewer)', () => {
        render(<Sidebar {...sidebarProps} role="viewer" permissions={{ view_appointments: true }} />);
        expect(screen.queryByRole('link', { name: 'Configuración' })).not.toBeInTheDocument();
    });

    it('appointments-only business can open /app/turnos/configuracion', () => {
        render(
            <AppShell session={appointmentsOnlySession}>
                <div>turnos-config-page</div>
            </AppShell>,
        );
        expect(screen.getByText('turnos-config-page')).toBeInTheDocument();
        expect(screen.queryByText('No disponible en tu plan')).not.toBeInTheDocument();
    });
});

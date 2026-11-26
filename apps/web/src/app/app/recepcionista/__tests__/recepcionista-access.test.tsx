import { render, screen } from '@testing-library/react';
import type { AnchorHTMLAttributes, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PROD-02G1: Recepcionista IA independiente. Login → /app/dashboard → entrada
// del servicio; layout propio por `services.enabled`; enforcement global de
// /app sin cambios (beneficio futuro/vencido = sin acceso → planes).

class RedirectSignal extends Error {
    constructor(public readonly to: string) {
        super(`redirect:${to}`);
    }
}

const nav = vi.hoisted(() => ({
    redirect: vi.fn((to: string) => {
        throw new RedirectSignal(to);
    }),
}));
vi.mock('next/navigation', () => ({ redirect: nav.redirect }));

const headerStore = vi.hoisted(() => ({ pathname: '/app/recepcionista' }));
vi.mock('next/headers', () => ({
    headers: async () => ({ get: (name: string) => (name === 'x-pathname' ? headerStore.pathname : null) }),
}));

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));

vi.mock('@/lib/auth', () => ({ getSession: vi.fn() }));
vi.mock('@/app/providers', () => ({ Providers: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock('@/components/app/app-shell', () => ({
    AppShell: ({ children }: { children: ReactNode }) => <div data-testid="app-shell">{children}</div>,
}));
vi.mock('@/features/reception/ai-usage-summary-panel', () => ({
    AIUsageSummaryPanel: ({ variant }: { variant: string }) => <div data-testid={`ai-usage-${variant}`} />,
}));

import { getSession } from '@/lib/auth';
import { getServiceEntryPath, planDisplayName, serviceDisplayName } from '@/lib/services';

import AppLayout from '../../layout';
import DashboardPage from '../../dashboard/page';
import AppIndexPage from '../../page';
import RecepcionistaLayout from '../layout';
import RecepcionistaPage from '../page';
import RecepcionistaConsumoPage from '../consumo/page';

const getSessionMock = vi.mocked(getSession);

const RECEPTION_PERMISSIONS = {
    view_leads: true, manage_leads: true, view_ai_usage: true, view_customers: true,
    manage_customers: true, manage_users: true, manage_settings: true,
};

function receptionSession(overrides: Record<string, unknown> = {}) {
    return {
        user: { id: 1, name: 'Dueña', must_change_password: false },
        current: { service: 'reception', role: 'owner', business: { id: 7, name: 'Clínica Sol', status: 'trialing' } },
        services: { enabled: ['reception'], default: 'reception' },
        features: { reception_core: true, leads: true, customers: true, sales: false, appointments_core: false },
        permissions: RECEPTION_PERMISSIONS,
        subscription: { access_allowed: true, status: 'trialing', plan: 'reception', reason_code: 'access_granted' },
        ...overrides,
    } as never;
}

async function redirectOf(run: () => Promise<unknown>): Promise<string | null> {
    try {
        await run();
        return null;
    } catch (error) {
        if (error instanceof RedirectSignal) return error.to;
        throw error;
    }
}

beforeEach(() => {
    getSessionMock.mockReset();
    nav.redirect.mockClear();
    headerStore.pathname = '/app/recepcionista';
});

describe('Recepcionista IA — entrada y redirección', () => {
    it('registra la entrada y los nombres del producto', () => {
        expect(getServiceEntryPath('reception')).toBe('/app/recepcionista');
        expect(serviceDisplayName('reception')).toBe('Recepcionista IA');
        expect(planDisplayName('reception')).toBe('Recepcionista IA');
    });

    it('el login (→ /app/dashboard) y /app llevan a /app/recepcionista', async () => {
        getSessionMock.mockResolvedValue(receptionSession());
        expect(await redirectOf(() => DashboardPage())).toBe('/app/recepcionista');
        expect(await redirectOf(() => AppIndexPage())).toBe('/app/recepcionista');
    });

    it('Turnos y Gestión conservan su entrada', async () => {
        getSessionMock.mockResolvedValue(receptionSession({
            current: { service: 'appointments', role: 'owner', business: { id: 1, name: 'T', status: 'active' } },
        }));
        expect(await redirectOf(() => DashboardPage())).toBe('/app/turnos');
        getSessionMock.mockResolvedValue(receptionSession({
            current: { service: 'gestion', role: 'owner', business: { id: 1, name: 'G', status: 'active' } },
        }));
        expect(await redirectOf(() => DashboardPage())).toBe('/app/gestion/dashboard');
    });
});

describe('Recepcionista IA — acceso', () => {
    it('beneficio vigente: /app/recepcionista entra al panel', async () => {
        getSessionMock.mockResolvedValue(receptionSession());
        const tree = await AppLayout({ children: <p>contenido</p> });
        render(tree);
        expect(screen.getByTestId('app-shell')).toBeInTheDocument();
        expect(screen.getByText('contenido')).toBeInTheDocument();
    });

    it('beneficio futuro o vencido: sin acceso → planes, también por URL directa', async () => {
        for (const reason of ['no_subscription', 'trial_expired']) {
            for (const path of ['/app/recepcionista', '/app/recepcionista/consumo']) {
                headerStore.pathname = path;
                getSessionMock.mockResolvedValue(receptionSession({
                    subscription: { access_allowed: false, status: 'trialing', plan: 'reception', reason_code: reason },
                }));
                expect(await redirectOf(() => AppLayout({ children: null }))).toBe('/app/planes');
            }
        }
    });

    it('sin Recepcionista en services.enabled el módulo vuelve al hub (acceso directo por URL)', async () => {
        getSessionMock.mockResolvedValue(receptionSession({
            services: { enabled: ['appointments'], default: 'appointments' },
            current: { service: 'appointments', role: 'owner', business: { id: 1, name: 'T', status: 'active' } },
        }));
        expect(await redirectOf(() => RecepcionistaLayout({ children: null }))).toBe('/app/servicios');
    });

    it('con Recepcionista el layout del módulo renderiza su contenido', async () => {
        getSessionMock.mockResolvedValue(receptionSession());
        render(await RecepcionistaLayout({ children: <p>modulo</p> }));
        expect(screen.getByText('modulo')).toBeInTheDocument();
    });

    it('Recepcionista también entra cuando es un servicio adicional (Gestión principal)', async () => {
        getSessionMock.mockResolvedValue(receptionSession({
            services: { enabled: ['gestion', 'reception'], default: 'gestion' },
            current: { service: 'gestion', role: 'owner', business: { id: 1, name: 'G', status: 'active' } },
        }));
        render(await RecepcionistaLayout({ children: <p>modulo</p> }));
        expect(screen.getByText('modulo')).toBeInTheDocument();
    });
});

describe('Recepcionista IA — Inicio y Consumo', () => {
    it('Inicio muestra solo accesos implementados según permisos y plan', async () => {
        getSessionMock.mockResolvedValue(receptionSession());
        render(await RecepcionistaPage());
        expect(screen.getByRole('heading', { name: 'Recepcionista IA' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Ver leads' })).toHaveAttribute('href', '/app/recepcionista/leads');
        expect(screen.getByRole('link', { name: 'Ver consumo' })).toHaveAttribute('href', '/app/recepcionista/consumo');
        expect(screen.getByRole('link', { name: 'Ver clientes' })).toHaveAttribute('href', '/app/clientes');
        expect(screen.getByTestId('ai-usage-compact')).toBeInTheDocument();
        const hrefs = screen.getAllByRole('link').map((link) => link.getAttribute('href') ?? '');
        for (const foreign of ['/app/turnos', '/app/gestion', '/app/stock', '/app/sales', '/app/cash', '/app/products', '/app/orders']) {
            expect(hrefs.some((href) => href.startsWith(foreign))).toBe(false);
        }
    });

    it('sin plan de Clientes ni permiso de consumo no ofrece esos accesos', async () => {
        getSessionMock.mockResolvedValue(receptionSession({
            features: { reception_core: true, leads: true, customers: false },
            permissions: { view_leads: true },
        }));
        render(await RecepcionistaPage());
        expect(screen.queryByRole('link', { name: 'Ver clientes' })).not.toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Ver leads' })).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Ver consumo' })).not.toBeInTheDocument();
        expect(screen.queryByTestId('ai-usage-compact')).not.toBeInTheDocument();
    });

    it('Consumo exige view_ai_usage', async () => {
        getSessionMock.mockResolvedValue(receptionSession({ permissions: { view_leads: true } }));
        render(await RecepcionistaConsumoPage());
        expect(screen.getByText('Tu rol no puede ver el consumo de Recepcionista IA.')).toBeInTheDocument();
        expect(screen.queryByTestId('ai-usage-full')).not.toBeInTheDocument();
    });

    it('Consumo con permiso muestra el detalle', async () => {
        getSessionMock.mockResolvedValue(receptionSession());
        render(await RecepcionistaConsumoPage());
        expect(screen.getByTestId('ai-usage-full')).toBeInTheDocument();
    });
});

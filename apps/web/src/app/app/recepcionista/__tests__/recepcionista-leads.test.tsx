import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactElement } from 'react';

// PROD-02G2: rutas de Leads de Recepcionista IA (misma implementación que
// Turnos), contexto sin agenda, gating y deep links desde `/app/turnos/leads`.

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
vi.mock('next/navigation', () => ({ redirect: nav.redirect, useRouter: () => ({ push: vi.fn() }) }));

const headerStore = vi.hoisted(() => ({ pathname: '' }));
vi.mock('next/headers', () => ({
    headers: async () => ({ get: (name: string) => (name === 'x-pathname' ? headerStore.pathname : null) }),
}));
vi.mock('@/lib/auth', () => ({ getSession: vi.fn() }));

import { getSession } from '@/lib/auth';
import { LeadsContextProvider } from '@/features/leads/ui/leads-context';
import { LeadDetailClient } from '@/features/leads/ui/lead-detail-client';
import { LeadsInboxClient } from '@/features/leads/ui/leads-inbox-client';
import {
    contactNoun, leadDetailHref, personalize, receptionLeadsPathFor,
} from '@/features/leads/ui/leads-routes';

import TurnosLayout from '../../turnos/layout';
import RecepcionistaLeadsPage from '../leads/page';
import RecepcionistaLeadDetailPage from '../leads/[id]/page';
import TurnosLeadsPage from '../../turnos/leads/page';

const getSessionMock = vi.mocked(getSession);

function session(overrides: Record<string, unknown> = {}) {
    return {
        user: { id: 3, name: 'Dueña' },
        current: { service: 'reception', role: 'owner', business: { id: 7, name: 'Clínica', status: 'trialing', timezone: 'America/Argentina/Buenos_Aires' } },
        services: { enabled: ['reception'], default: 'reception' },
        features: { reception_core: true, leads: true, customers: true, agenda_integration: false },
        permissions: { view_leads: true, manage_leads: true, view_customers: true },
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

type ProviderElement = ReactElement<{ value: { basePath: string; agendaEnabled: boolean; product: string }; children: ReactElement<Record<string, unknown>> }>;

beforeEach(() => {
    getSessionMock.mockReset();
    nav.redirect.mockClear();
    headerStore.pathname = '';
});

describe('leads-routes', () => {
    it('mapea deep links de Leads de Turnos a Recepcionista y nada más', () => {
        expect(receptionLeadsPathFor('/app/turnos/leads')).toBe('/app/recepcionista/leads');
        expect(receptionLeadsPathFor('/app/turnos/leads/abc-1')).toBe('/app/recepcionista/leads/abc-1');
        expect(receptionLeadsPathFor('/app/turnos/leadsx')).toBeNull();
        expect(receptionLeadsPathFor('/app/turnos/turnos')).toBeNull();
        expect(receptionLeadsPathFor('')).toBeNull();
    });

    it('vocabulario por producto sin tocar Turnos', () => {
        expect(contactNoun('reception').singular).toBe('cliente');
        expect(contactNoun('appointments').singular).toBe('paciente');
        expect(personalize('Mensaje para el paciente. Paciente: X', 'reception')).toBe('Mensaje para el cliente. Cliente: X');
        expect(personalize('Mensaje para el paciente', 'appointments')).toBe('Mensaje para el paciente');
        expect(personalize('pacientes', 'reception')).toBe('pacientes');
        expect(leadDetailHref('/app/recepcionista/leads', 'x')).toBe('/app/recepcionista/leads/x');
    });
});

describe('páginas de Leads de Recepcionista', () => {
    it('la bandeja monta la implementación compartida con contexto Recepcionista sin agenda', async () => {
        getSessionMock.mockResolvedValue(session());
        const element = (await RecepcionistaLeadsPage()) as ProviderElement;
        expect(element.type).toBe(LeadsContextProvider);
        expect(element.props.value).toEqual({ basePath: '/app/recepcionista/leads', agendaEnabled: false, product: 'reception' });
        expect(element.props.children.type).toBe(LeadsInboxClient);
        expect(element.props.children.props).toMatchObject({ canManage: true, currentUserId: 3 });
    });

    it('agenda solo con agenda_integration', async () => {
        getSessionMock.mockResolvedValue(session({ features: { leads: true, agenda_integration: true } }));
        const element = (await RecepcionistaLeadsPage()) as ProviderElement;
        expect(element.props.value.agendaEnabled).toBe(true);
    });

    it('el detalle usa la misma implementación y el mismo gating', async () => {
        getSessionMock.mockResolvedValue(session());
        const element = (await RecepcionistaLeadDetailPage({ params: Promise.resolve({ id: 'lead-9' }) })) as ProviderElement;
        expect(element.type).toBe(LeadsContextProvider);
        expect(element.props.children.type).toBe(LeadDetailClient);
        expect(element.props.children.props).toMatchObject({ leadId: 'lead-9', canManage: true, canViewCustomers: true });
    });

    it('sin plan de Leads o sin permiso no monta la bandeja', async () => {
        getSessionMock.mockResolvedValue(session({ features: { reception_core: true, leads: false } }));
        const noPlan = (await RecepcionistaLeadsPage()) as ReactElement<{ title: string; description: string }>;
        expect(noPlan.props.title).toBe('Tu plan no incluye Leads');
        expect(noPlan.props.description).toContain('Recepcionista IA');

        getSessionMock.mockResolvedValue(session({ permissions: { view_leads: false } }));
        const noPermission = (await RecepcionistaLeadDetailPage({ params: Promise.resolve({ id: 'x' }) })) as ReactElement<{ title: string }>;
        expect(noPermission.props.title).toBe('Sin acceso');
    });

    it('Turnos sigue montando su bandeja sin provider (contexto por defecto)', async () => {
        getSessionMock.mockResolvedValue(session({
            services: { enabled: ['appointments'] }, current: { service: 'appointments', role: 'owner', business: { id: 1, name: 'T', status: 'active' } },
        }));
        const element = (await TurnosLeadsPage()) as ReactElement;
        expect(element.type).toBe(LeadsInboxClient);
    });
});

describe('deep links de /app/turnos/leads', () => {
    it('negocio solo Recepcionista: redirige al módulo propio (bandeja y detalle de notificación)', async () => {
        getSessionMock.mockResolvedValue(session());
        headerStore.pathname = '/app/turnos/leads/lead-42';
        expect(await redirectOf(() => TurnosLayout({ children: null }))).toBe('/app/recepcionista/leads/lead-42');
        headerStore.pathname = '/app/turnos/leads';
        expect(await redirectOf(() => TurnosLayout({ children: null }))).toBe('/app/recepcionista/leads');
    });

    it('otras rutas de Turnos siguen yendo al hub', async () => {
        getSessionMock.mockResolvedValue(session());
        headerStore.pathname = '/app/turnos/profesionales';
        expect(await redirectOf(() => TurnosLayout({ children: null }))).toBe('/app/servicios');
        headerStore.pathname = '';
        expect(await redirectOf(() => TurnosLayout({ children: null }))).toBe('/app/servicios');
    });

    it('sin Recepcionista ni Turnos: hub, sin redirigir a Recepcionista', async () => {
        getSessionMock.mockResolvedValue(session({ services: { enabled: ['gestion'] } }));
        headerStore.pathname = '/app/turnos/leads/lead-42';
        expect(await redirectOf(() => TurnosLayout({ children: null }))).toBe('/app/servicios');
    });

    it('con Turnos (aunque también tenga Recepcionista) se queda en Turnos', async () => {
        getSessionMock.mockResolvedValue(session({ services: { enabled: ['appointments', 'reception'] } }));
        headerStore.pathname = '/app/turnos/leads/lead-42';
        expect(await redirectOf(() => TurnosLayout({ children: null }))).toBeNull();
    });
});

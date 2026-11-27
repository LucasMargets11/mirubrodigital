import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState, type AnchorHTMLAttributes, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// PROD-08E2: «Conexiones WhatsApp» (estado local de PROD-08E1) dentro del
// bloque de Recepcionista IA del detalle del cliente de Platform Admin.

const providerMounts = vi.hoisted(() => ({ count: 0 }));

vi.mock('@/lib/api/client', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/lib/api/client')>()),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiPatch: vi.fn(),
}));
vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));
vi.mock('@/components/admin/qr-reviews-card', () => ({ QRResenasCard: () => null }));
// PROD-09B: la preparación tiene su propio suite (receptionist-readiness).
vi.mock('@/components/admin/receptionist-readiness-section', () => ({ ReceptionistReadinessSection: () => null }));
// Cuenta montajes reales del Provider (un QueryClient por montaje).
vi.mock('@/app/providers', async (importOriginal) => {
    const real = await importOriginal<typeof import('@/app/providers')>();
    return {
        Providers: (props: { children: ReactNode }) => {
            useState(() => { providerMounts.count += 1; return null; });
            return real.Providers(props);
        },
    };
});

import { ClienteDetailContent } from '@/app/admin/clientes/[clienteId]/cliente-detail-content';
import type { AdminWhatsAppChannel, AdminWhatsAppConnections } from '@/features/reception/types';
import type { AdminClientDetail } from '@/lib/admin/types';
import { ApiError, apiGet, apiPatch, apiPost } from '@/lib/api/client';

const getMock = vi.mocked(apiGet);
const base = (id: number) => `/api/v1/platform-admin/clients/${id}`;
const connectionsPath = (id: number) => `${base(id)}/whatsapp-connections/`;

function client(id = 7, name = 'Clínica Sol'): AdminClientDetail {
    return {
        id, name, slug: `c-${id}`, status: 'active', service_type: 'management', country: 'AR', currency: 'ARS',
        created_at: null, activated_at: null, trial_starts_at: null, trial_ends_at: null, owner: null,
        members: [], member_count: 0, branch_count: 0, subscription: null, risk_badges: [],
        recent_payments: [], recent_events: [], recent_audit: [], notes: [], billing_profile: null,
        support_summary: {
            total_tickets: 0, open_tickets: 0, resolved_tickets: 0, last_ticket_at: null,
            last_ticket_reference: null, recent_tickets: [],
        },
    };
}

function channel(phone: string, overrides: Partial<AdminWhatsAppChannel> = {}): AdminWhatsAppChannel {
    return {
        id: `ch-${phone}`,
        provider: 'whatsapp_cloud',
        phone_number_id: phone,
        waba_id: '900800700600',
        is_active: true,
        created_at: '2026-11-20T15:00:00+00:00',
        deactivated_at: null,
        agent_instance: { external_id: 'recepcion-prod', name: 'Recepcionista prod', is_enabled: true, disabled_at: null },
        authorization: {
            id: `auth-${phone}`, kind: 'business', owned_by_this_business: true, status: 'active', expired: false,
            expires_at: '2027-01-15T15:00:00+00:00', revoked_at: null,
            created_at: '2026-11-20T15:05:00+00:00', updated_at: '2026-11-20T15:05:00+00:00',
        },
        local_status: 'credential_ready',
        ...overrides,
    };
}

function connections(channels: AdminWhatsAppChannel[], businessId = 7): AdminWhatsAppConnections {
    return {
        contract_version: 1,
        business_id: businessId,
        evaluated_at: '2026-11-27T18:00:00+00:00',
        channels,
        external_verification: { performed: false, meta_connectivity: 'unknown', detail: 'Estado local.' },
    };
}

type Routes = Record<string, unknown>;

/** Respuesta por prefijo de ruta; un `Error` se rechaza; rutas no previstas fallan. */
function serve(routes: Routes) {
    getMock.mockImplementation(async (path: string) => {
        const key = Object.keys(routes).find((prefix) => path.startsWith(prefix));
        if (!key) throw new Error(`unexpected GET ${path}`);
        const value = routes[key];
        if (value instanceof Error) throw value;
        return typeof value === 'function' ? (value as () => unknown)() : value;
    });
}

function routesFor(id: number, conn: unknown): Routes {
    return {
        [`${base(id)}/receptionist-config/`]: { config: null },
        [`${base(id)}/ai-usage/`]: new ApiError('x', 500, {}),
        [`${base(id)}/operational-metrics/`]: new ApiError('x', 500, {}),
        [connectionsPath(id)]: conn,
    };
}

async function section() {
    const heading = await screen.findByRole('heading', { name: 'Conexiones WhatsApp' });
    return heading.closest('div.rounded-xl') as HTMLElement;
}

const getPaths = () => getMock.mock.calls.map(([path]) => path as string);

beforeEach(() => {
    getMock.mockReset();
    vi.mocked(apiPost).mockReset();
    vi.mocked(apiPatch).mockReset();
    providerMounts.count = 0;
});

describe('Platform Admin — Conexiones WhatsApp', () => {
    it('cliente sin canales: estado vacío existente y aclaración de verificación local', async () => {
        serve(routesFor(7, connections([])));
        render(<ClienteDetailContent client={client()} />);
        const card = await section();
        expect(await within(card).findByText('Sin canales WhatsApp registrados')).toBeInTheDocument();
        expect(within(card).getByText(/No se realizó verificación externa con Meta/)).toBeInTheDocument();
        expect(within(card).getByText(/evaluado el/)).toBeInTheDocument();
    });

    it('varios canales: Phone Number ID como ID, WABA, canal, instancia y autorización', async () => {
        serve(routesFor(7, connections([
            channel('100200300400'),
            channel('100200300999', {
                is_active: false, deactivated_at: '2026-11-21T15:00:00+00:00', waba_id: null,
                authorization: null, local_status: 'channel_not_active',
            }),
        ])));
        render(<ClienteDetailContent client={client()} />);
        const card = await section();
        const items = await within(card).findAllByRole('listitem');
        expect(items).toHaveLength(2);

        const [ready, inactive] = items;
        expect(within(ready).getByText(/Phone Number ID/)).toHaveTextContent('Phone Number ID 100200300400');
        expect(within(ready).getByText('900800700600')).toBeInTheDocument();
        expect(within(ready).getByText('Credencial vigente (estado local)')).toBeInTheDocument();
        expect(within(ready).getByText('Activo')).toBeInTheDocument();
        expect(within(ready).getByText('Recepcionista prod · habilitada')).toBeInTheDocument();
        expect(within(ready).getByText('Del comercio · activa')).toBeInTheDocument();
        expect(within(ready).getByText('Vencimiento')).toBeInTheDocument();

        expect(within(inactive).getByText('Canal desactivado')).toBeInTheDocument();
        expect(within(inactive).getByText(/^Desactivado · /)).toBeInTheDocument();
        expect(within(inactive).queryByText('WABA ID')).not.toBeInTheDocument();
        expect(within(inactive).getAllByText('Sin autorización').length).toBeGreaterThan(0);
        expect(within(inactive).queryByText('Vencimiento')).not.toBeInTheDocument();
        // Sin identificadores técnicos innecesarios.
        expect(card).not.toHaveTextContent('ch-100200300400');
        expect(card).not.toHaveTextContent('auth-100200300400');
        expect(card).not.toHaveTextContent('recepcion-prod');
    });

    it('los nueve estados locales y uno desconocido', async () => {
        const cases: Array<[string, string]> = [
            ['credential_ready', 'Credencial vigente (estado local)'],
            ['channel_not_active', 'Canal desactivado'],
            ['whatsapp_authorization_missing', 'Sin autorización'],
            ['whatsapp_authorization_owner_mismatch', 'Autorización inconsistente'],
            ['whatsapp_authorization_revoked', 'Autorización revocada'],
            ['whatsapp_authorization_invalid', 'Autorización inválida'],
            ['whatsapp_authorization_expired', 'Autorización vencida'],
            ['whatsapp_waba_missing', 'WABA no informada'],
            ['agent_instance_disabled', 'Instancia deshabilitada'],
            ['meta_says_ok', 'Estado no reconocido (meta_says_ok)'],
        ];
        serve(routesFor(7, connections(cases.map(([code], i) => channel(`5000${i}`, { local_status: code })))));
        render(<ClienteDetailContent client={client()} />);
        const card = await section();
        const items = await within(card).findAllByRole('listitem');
        cases.forEach(([, label], i) => {
            expect(within(items[i]).getAllByText(label).length).toBeGreaterThan(0);
        });
        // El desconocido no se presenta como válido.
        expect(within(items[9]).queryByText('Credencial vigente (estado local)')).not.toBeInTheDocument();
    });

    it('autorización de plataforma, revocada y valores nulos', async () => {
        serve(routesFor(7, connections([
            channel('7001', {
                authorization: {
                    id: 'p', kind: 'platform', owned_by_this_business: null, status: 'revoked', expired: false,
                    expires_at: null, revoked_at: '2026-11-25T15:00:00+00:00', created_at: null, updated_at: null,
                },
                local_status: 'whatsapp_authorization_revoked',
            }),
            channel('7002', {
                created_at: null,
                agent_instance: { external_id: 'x', name: 'Agente B', is_enabled: false, disabled_at: null },
                authorization: {
                    id: 'e', kind: 'business', owned_by_this_business: true, status: 'active', expired: true,
                    expires_at: '2026-11-01T15:00:00+00:00', revoked_at: null, created_at: null, updated_at: null,
                },
                local_status: 'whatsapp_authorization_expired',
            }),
        ])));
        render(<ClienteDetailContent client={client()} />);
        const [platform, expired] = await within(await section()).findAllByRole('listitem');

        expect(within(platform).getByText('De plataforma · revocada')).toBeInTheDocument();
        expect(within(platform).getByText('Sin vencimiento informado')).toBeInTheDocument();
        expect(within(platform).getByText('Revocada')).toBeInTheDocument();

        expect(within(expired).getByText('Del comercio · activa')).toBeInTheDocument();
        expect(within(expired).getByText(/· vencida$/)).toBeInTheDocument();
        expect(within(expired).getByText('Agente B · deshabilitada · Sin dato')).toBeInTheDocument();
        expect(within(expired).getByText('Alta del canal').nextSibling).toHaveTextContent('Sin dato');
    });

    it('sin indicadores falsos de conectividad', async () => {
        serve(routesFor(7, connections([channel('8001')])));
        render(<ClienteDetailContent client={client()} />);
        const card = await section();
        await within(card).findByText('Credencial vigente (estado local)');
        for (const phrase of [/conectado/i, /en línea|online/i, /envío disponible/i, /verificad[oa] con Meta/i]) {
            const matches = within(card).queryAllByText(phrase)
                .filter((el) => !el.textContent?.includes('No se realizó verificación externa con Meta'));
            expect(matches).toHaveLength(0);
        }
        expect(within(card).getByText(/no indica WhatsApp conectado, agente online ni envío disponible/)).toBeInTheDocument();
        // Solo lectura: sin escrituras ni campos para secretos.
        expect(within(card).queryByRole('textbox')).not.toBeInTheDocument();
        expect(within(card).getAllByRole('button').map((b) => b.textContent)).toEqual(['Actualizar']);
        expect(apiPost).not.toHaveBeenCalled();
        expect(apiPatch).not.toHaveBeenCalled();
    });

    it('actualización manual: vuelve a consultar solo a pedido', async () => {
        let call = 0;
        serve(routesFor(7, () => {
            call += 1;
            return connections(call === 1 ? [] : [channel('9001')]);
        }));
        render(<ClienteDetailContent client={client()} />);
        const card = await section();
        await within(card).findByText('Sin canales WhatsApp registrados');
        expect(getPaths().filter((p) => p === connectionsPath(7))).toHaveLength(1);

        fireEvent.click(within(card).getByRole('button', { name: 'Actualizar' }));
        expect(await within(card).findByText('Credencial vigente (estado local)')).toBeInTheDocument();
        expect(getPaths().filter((p) => p === connectionsPath(7))).toHaveLength(2);
    });

    it('403 y error de red: estados propios, sin afectar la configuración', async () => {
        serve(routesFor(7, new ApiError('forbidden', 403, { detail: 'forbidden' })));
        const { unmount } = render(<ClienteDetailContent client={client()} />);
        let card = await section();
        expect(await within(card).findByText('Tu rol de Platform Admin no puede ver las conexiones WhatsApp.')).toBeInTheDocument();
        expect(await screen.findByRole('button', { name: 'Crear borrador' })).toBeInTheDocument();
        unmount();

        serve(routesFor(7, new Error('network')));
        render(<ClienteDetailContent client={client()} />);
        card = await section();
        expect(await within(card).findByText(/No pudimos cargar las conexiones WhatsApp/)).toBeInTheDocument();
        expect(within(card).getByRole('button', { name: 'Reintentar' })).toBeInTheDocument();
    });

    it('cambio de cliente: query por Business ID, sin mezclar datos', async () => {
        serve({ ...routesFor(7, connections([channel('7777')])), ...routesFor(8, connections([channel('8888')], 8)) });
        const { rerender } = render(<ClienteDetailContent client={client(7)} />);
        expect(await within(await section()).findByText('7777')).toBeInTheDocument();

        rerender(<ClienteDetailContent client={client(8, 'Spa Luna')} />);
        const card = await section();
        expect(await within(card).findByText('8888')).toBeInTheDocument();
        expect(within(card).queryByText('7777')).not.toBeInTheDocument();
        expect(getPaths()).toContain(connectionsPath(8));
        expect(getPaths().every((p) => p.startsWith('/api/v1/platform-admin/clients/'))).toBe(true);
    });

    it('reutiliza el Provider del bloque: un solo QueryClient para todas las secciones', async () => {
        serve(routesFor(7, connections([])));
        render(<ClienteDetailContent client={client()} />);
        await within(await section()).findByText('Sin canales WhatsApp registrados');
        await screen.findByRole('heading', { name: 'Consumo comercial de IA' });
        await screen.findByRole('heading', { name: 'Métricas operativas' });
        expect(providerMounts.count).toBe(1);
        // Ningún endpoint del comercio.
        expect(getPaths().some((p) => p.startsWith('/api/v1/ai-usage') || p.startsWith('/api/v1/receptionist-config'))).toBe(false);
    });

    it('cliente sin Recepcionista (404 de dominio): no consulta conexiones', async () => {
        serve({
            ...routesFor(7, connections([])),
            [`${base(7)}/receptionist-config/`]: new ApiError('x', 404, { code: 'client_not_found' }),
        });
        render(<ClienteDetailContent client={client()} />);
        await waitFor(() => expect(getPaths()).toContain(`${base(7)}/receptionist-config/`));
        await waitFor(() => expect(screen.queryByRole('heading', { name: 'Recepcionista IA' })).not.toBeInTheDocument());
        expect(screen.queryByRole('heading', { name: 'Conexiones WhatsApp' })).not.toBeInTheDocument();
        expect(getPaths()).not.toContain(connectionsPath(7));
    });
});

import { act, fireEvent, render, screen } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const auth = vi.hoisted(() => ({ session: null as unknown }));

vi.mock('next/navigation', () => ({
    redirect: vi.fn(),
    usePathname: () => '/app/turnos',
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));
vi.mock('@/lib/auth', () => ({ getSession: async () => auth.session }));
vi.mock('@/app/app/turnos/whatsapp-contact-card', () => ({ WhatsappContactCard: () => <div>whatsapp-card</div> }));
// CUSTOMER 07B: la tarjeta de automatizaciones usa React Query; se prueba aparte.
vi.mock('@/features/appointments/reminder-automation-card', () => ({ ReminderAutomationCard: () => null }));
vi.mock('@/features/appointments/reply-to-email-card', () => ({ ReplyToEmailCard: () => null }));
vi.mock('@/features/merchant-payments/mercado-pago-connection-card', () => ({
    MercadoPagoConnectionCard: ({ canManage }: { canManage: boolean }) => (
        <div>mp-card {canManage ? 'manage' : 'readonly'}</div>
    ),
}));

import TurnosConfiguracionPage from '@/app/app/turnos/configuracion/page';
import TurnosPage from '@/app/app/turnos/page';
import { PublicBookingLinkCard, usablePublicBookingUrl } from '@/features/appointments/public-booking-link-card';
import type { PublicBookingPage, Session } from '@/lib/auth/types';

const URL_OK = 'https://app.example.test/t/peluqueria-sol';
const available: PublicBookingPage = { available: true, url: URL_OK, reason: null };

function makeSession(role: string, permissions: Record<string, boolean>, publicBooking: PublicBookingPage | null = available) {
    return {
        user: { name: 'Demo' },
        current: {
            service: 'appointments',
            role,
            business: { id: 77, name: 'Peluquería Sol', status: 'active', public_booking: publicBooking },
        },
        services: { enabled: ['appointments'] },
        features: {},
        permissions,
        subscription: { status: 'active' },
    } as unknown as Session;
}

const OWNER_PERMS = { view_appointments: true, manage_appointments: true, manage_settings: true, manage_users: true };
const MANAGER_PERMS = { view_appointments: true, manage_appointments: true, manage_settings: true };
const VIEWER_PERMS = { view_appointments: true };

let writeText: ReturnType<typeof vi.fn>;

beforeEach(() => {
    writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
});

afterEach(() => {
    vi.useRealTimers();
});

describe('PublicBookingLinkCard', () => {
    it('muestra la URL cuando Turnos está habilitado y hay slug', () => {
        render(<PublicBookingLinkCard publicBooking={available} />);
        expect(screen.getByText('Página de reservas')).toBeInTheDocument();
        expect(screen.getByText('Compartí este enlace para que tus clientes puedan reservar un turno.')).toBeInTheDocument();
        expect(screen.getByTestId('public-booking-url')).toHaveTextContent(URL_OK);
    });

    it('la URL termina en /t/<slug> y no contiene ids, tokens ni query', () => {
        render(<PublicBookingLinkCard publicBooking={available} />);
        const shown = screen.getByTestId('public-booking-url').textContent ?? '';
        expect(shown.endsWith('/t/peluqueria-sol')).toBe(true);
        expect(shown).not.toMatch(/[?#]/);
        expect(shown).not.toContain('77');
        expect(shown).not.toMatch(/token|business_id|preference|[0-9a-f]{8}-[0-9a-f]{4}/i);
    });

    it('Copiar enlace llama al clipboard con la URL exacta y muestra feedback', async () => {
        render(<PublicBookingLinkCard publicBooking={available} />);
        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: 'Copiar enlace' }));
        });
        expect(writeText).toHaveBeenCalledTimes(1);
        expect(writeText).toHaveBeenCalledWith(URL_OK);
        expect(screen.getByRole('status')).toHaveTextContent('Enlace copiado');
    });

    it('el feedback de copiado desaparece solo', async () => {
        vi.useFakeTimers();
        render(<PublicBookingLinkCard publicBooking={available} />);
        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: 'Copiar enlace' }));
        });
        expect(screen.getByRole('status')).toHaveTextContent('Enlace copiado');
        act(() => {
            vi.advanceTimersByTime(3000);
        });
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    it('si el clipboard falla muestra error sin romper la pantalla', async () => {
        writeText.mockRejectedValueOnce(new Error('denied'));
        render(<PublicBookingLinkCard publicBooking={available} />);
        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: 'Copiar enlace' }));
        });
        expect(screen.getByRole('status')).toHaveTextContent('No pudimos copiar el enlace');
        expect(screen.getByTestId('public-booking-url')).toHaveTextContent(URL_OK);
    });

    it('si no existe Clipboard API también maneja el error', async () => {
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
        render(<PublicBookingLinkCard publicBooking={available} />);
        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: 'Copiar enlace' }));
        });
        expect(screen.getByRole('status')).toHaveTextContent('No pudimos copiar el enlace');
    });

    it('Abrir página usa la URL correcta en una pestaña nueva segura', () => {
        render(<PublicBookingLinkCard publicBooking={available} />);
        const link = screen.getByRole('link', { name: 'Abrir página' });
        expect(link).toHaveAttribute('href', URL_OK);
        expect(link).toHaveAttribute('target', '_blank');
        const rel = link.getAttribute('rel') ?? '';
        expect(rel).toContain('noopener');
        expect(rel).toContain('noreferrer');
    });

    it('sin slug no genera una URL inválida', () => {
        const { container } = render(
            <PublicBookingLinkCard publicBooking={{ available: false, url: null, reason: 'missing_slug' }} />,
        );
        expect(screen.getByText('La página pública todavía no está disponible.')).toBeInTheDocument();
        expect(container.innerHTML).not.toContain('/t/');
        expect(container.innerHTML).not.toContain('undefined');
        expect(screen.queryByRole('button', { name: 'Copiar enlace' })).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Abrir página' })).not.toBeInTheDocument();
    });

    it('Business no publicable → estado no disponible, sin link accionable', () => {
        render(<PublicBookingLinkCard publicBooking={{ available: false, url: null, reason: 'not_publishable' }} />);
        expect(screen.getByText(/no está disponible mientras tu negocio no esté activo/)).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Abrir página' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Copiar enlace' })).not.toBeInTheDocument();
    });

    it('Turnos no habilitado (null) → sin link accionable', () => {
        render(<PublicBookingLinkCard publicBooking={null} />);
        expect(screen.getByText('Turnos no está habilitado para este negocio.')).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Abrir página' })).not.toBeInTheDocument();
    });

    it('descarta URLs que no sean http(s) /t/<slug> aunque vengan como disponibles', () => {
        expect(usablePublicBookingUrl({ available: true, url: 'javascript:alert(1)', reason: null })).toBeNull();
        expect(usablePublicBookingUrl({ available: true, url: 'https://x.test/t/undefined/extra', reason: null })).toBeNull();
        expect(usablePublicBookingUrl({ available: true, url: 'https://x.test/m/slug', reason: null })).toBeNull();
        expect(usablePublicBookingUrl({ available: false, url: URL_OK, reason: 'not_publishable' })).toBeNull();
        expect(usablePublicBookingUrl(available)).toBe(URL_OK);
    });
});

describe('Turnos → Configuración: Página de reservas', () => {
    it('owner ve la página de reservas y la card de MP', async () => {
        auth.session = makeSession('owner', OWNER_PERMS);
        render(await TurnosConfiguracionPage({}));
        expect(screen.getByTestId('public-booking-url')).toHaveTextContent(URL_OK);
        expect(screen.getByText('mp-card manage')).toBeInTheDocument();
    });

    it('manager puede compartir aunque MP sea solo OWNER/ADMIN', async () => {
        auth.session = makeSession('manager', MANAGER_PERMS);
        render(await TurnosConfiguracionPage({}));
        expect(screen.getByTestId('public-booking-url')).toHaveTextContent(URL_OK);
        expect(screen.getByRole('button', { name: 'Copiar enlace' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Abrir página' })).toHaveAttribute('href', URL_OK);
        // La regla financiera sigue restringiendo MP, pero no afecta el link.
        expect(screen.getByText('mp-card readonly')).toBeInTheDocument();
    });
});

describe('Turnos home', () => {
    it('ya no muestra el placeholder fijo y ofrece accesos reales', async () => {
        auth.session = makeSession('owner', OWNER_PERMS);
        render(await TurnosPage());
        expect(screen.queryByText('Todavía no configuraste tu agenda.')).not.toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Ver turnos' })).toHaveAttribute('href', '/app/turnos/turnos');
        expect(screen.getByRole('link', { name: 'Configuración' })).toHaveAttribute('href', '/app/turnos/configuracion');
        expect(screen.getByTestId('public-booking-url')).toHaveTextContent(URL_OK);
    });

    it('manager ve la página de reservas en el inicio', async () => {
        auth.session = makeSession('manager', MANAGER_PERMS);
        render(await TurnosPage());
        expect(screen.getByRole('link', { name: 'Abrir página' })).toHaveAttribute('href', URL_OK);
    });

    it('viewer sigue la política del módulo: ve el link público pero no la configuración', async () => {
        auth.session = makeSession('viewer', VIEWER_PERMS);
        render(await TurnosPage());
        expect(screen.getByTestId('public-booking-url')).toHaveTextContent(URL_OK);
        expect(screen.queryByRole('link', { name: 'Configuración' })).not.toBeInTheDocument();
        expect(screen.queryByText('whatsapp-card')).not.toBeInTheDocument();
    });

    it('negocio no disponible: el inicio no muestra link accionable', async () => {
        auth.session = makeSession('owner', OWNER_PERMS, { available: false, url: null, reason: 'not_publishable' });
        render(await TurnosPage());
        expect(screen.queryByRole('link', { name: 'Abrir página' })).not.toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Ver turnos' })).toBeInTheDocument();
    });
});

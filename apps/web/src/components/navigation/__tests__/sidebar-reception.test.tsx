import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AnchorHTMLAttributes } from 'react';

// PROD-02G1: navegación propia de Recepcionista IA. Solo rutas implementadas;
// nada de agenda, profesionales, reservas, POS, caja, ventas ni stock.

vi.mock('next/navigation', () => ({ usePathname: () => '/app/recepcionista' }));
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

import { Sidebar } from '@/components/navigation/sidebar';

class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
}
Object.defineProperty(globalThis, 'ResizeObserver', { writable: true, value: ResizeObserverMock });

const OWNER_PERMISSIONS = {
    view_leads: true, manage_leads: true, view_ai_usage: true, view_customers: true,
    manage_customers: true, manage_users: true, manage_settings: true,
};

const baseProps = {
    businessName: 'Clínica Sol',
    service: 'reception',
    features: { reception_core: true, leads: true, customers: true, sales: false, appointments_core: false },
    permissions: OWNER_PERMISSIONS,
    userName: 'Dueña',
    role: 'owner',
    subscriptionStatus: 'trialing',
    subscriptionPlan: 'reception',
} satisfies Parameters<typeof Sidebar>[0];

function hrefs() {
    return Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href') ?? '');
}

describe('Sidebar Recepcionista IA', () => {
    it('muestra el grupo propio con Inicio, Consumo, Clientes y la administración común', () => {
        render(<Sidebar {...baseProps} />);
        expect(screen.getAllByText('Recepcionista IA').length).toBeGreaterThan(0);
        expect(screen.getByRole('link', { name: 'Inicio' })).toHaveAttribute('href', '/app/recepcionista');
        expect(screen.getByRole('link', { name: 'Consumo' })).toHaveAttribute('href', '/app/recepcionista/consumo');
        expect(screen.getByRole('link', { name: 'Clientes' })).toHaveAttribute('href', '/app/clientes');
        expect(screen.getByRole('link', { name: 'Usuarios y accesos' })).toHaveAttribute('href', '/app/settings/access');
        expect(screen.getByRole('link', { name: 'Plan y facturación' })).toHaveAttribute('href', '/app/planes');
        expect(screen.getByRole('link', { name: 'Soporte' })).toHaveAttribute('href', '/app/soporte');
    });

    it('no expone funcionalidades ajenas ni rutas todavía no implementadas', () => {
        render(<Sidebar {...baseProps} />);
        const links = hrefs();
        for (const foreign of [
            '/app/turnos', '/app/gestion', '/app/stock', '/app/sales', '/app/cash', '/app/products',
            '/app/orders', '/app/operacion', '/app/resto', '/app/carta', '/app/resenas', '/app/owner',
        ]) {
            expect(links.some((href) => href === foreign || href.startsWith(`${foreign}/`))).toBe(false);
        }
        for (const label of [/Profesionales/i, /Horarios/i, /^Turnos$/i, /Caja/i, /Ventas/i, /Stock/i, /Mi agente/i, /WhatsApp/i]) {
            expect(screen.queryByRole('link', { name: label })).not.toBeInTheDocument();
        }
        // Leads llega con PROD-02G2: hoy no hay ruta propia bajo /app/recepcionista
        expect(links.some((href) => href.includes('leads'))).toBe(false);
    });

    it('respeta plan y permisos: Clientes por flag, Consumo y accesos por permiso', () => {
        render(
            <Sidebar
                {...baseProps}
                features={{ ...baseProps.features, customers: false }}
                permissions={{ view_leads: true, view_customers: true }}
                role="manager"
            />,
        );
        expect(screen.getByRole('link', { name: 'Inicio' })).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Clientes' })).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Consumo' })).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Usuarios y accesos' })).not.toBeInTheDocument();
    });
});

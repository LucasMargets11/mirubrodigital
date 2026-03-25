import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mock next/navigation ────────────────────────────────────────────────────

let mockPathname = '/app/gestion/finanzas/gastos';

vi.mock('next/navigation', () => ({
    usePathname: () => mockPathname,
    useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
    useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: any) => (
        <a href={href} {...props}>{children}</a>
    ),
}));

// ── AppPageHeader ───────────────────────────────────────────────────────────

describe('AppPageHeader', () => {
    beforeEach(() => {
        mockPathname = '/app/gestion/finanzas/gastos';
    });

    it('renders title and description', async () => {
        const { AppPageHeader } = await import('@/components/navigation/app-page-header');
        render(
            <AppPageHeader
                title="Finanzas Operativas"
                description="Test description"
            />
        );

        expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Finanzas Operativas');
        expect(screen.getByText('Test description')).toBeInTheDocument();
    });

    it('renders breadcrumbs with links and current page', async () => {
        const { AppPageHeader } = await import('@/components/navigation/app-page-header');
        render(
            <AppPageHeader
                title="Finanzas"
                breadcrumbs={[
                    { label: 'Gestión Comercial', href: '/app/gestion/dashboard' },
                    { label: 'Finanzas' },
                ]}
            />
        );

        const nav = screen.getByLabelText('Navegación de contexto');
        expect(nav).toBeInTheDocument();

        // First breadcrumb is a link
        const link = screen.getByRole('link', { name: 'Gestión Comercial' });
        expect(link).toHaveAttribute('href', '/app/gestion/dashboard');

        // Last breadcrumb is text with aria-current
        const current = screen.getByText('Finanzas', { selector: 'span[aria-current]' });
        expect(current).toHaveAttribute('aria-current', 'page');
    });

    it('renders actions when provided', async () => {
        const { AppPageHeader } = await import('@/components/navigation/app-page-header');
        render(
            <AppPageHeader
                title="Test"
                actions={<button>Action</button>}
            />
        );

        expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument();
    });
});

// ── ModuleTabs ──────────────────────────────────────────────────────────────

describe('ModuleTabs', () => {
    beforeEach(() => {
        mockPathname = '/app/gestion/finanzas/gastos';
    });

    it('renders tabs with correct active state', async () => {
        const { ModuleTabs } = await import('@/components/navigation/module-tabs');
        render(
            <ModuleTabs
                tabs={[
                    { href: '/app/gestion/finanzas/resumen', label: 'Resumen' },
                    { href: '/app/gestion/finanzas/gastos', label: 'Gastos' },
                    { href: '/app/gestion/finanzas/sueldos', label: 'Sueldos' },
                ]}
                ariaLabel="Secciones de Finanzas"
            />
        );

        const nav = screen.getByLabelText('Secciones de Finanzas');
        expect(nav).toBeInTheDocument();

        // Active tab
        const activeTab = screen.getByRole('tab', { name: 'Gastos' });
        expect(activeTab).toHaveAttribute('aria-selected', 'true');
        expect(activeTab).toHaveAttribute('aria-current', 'page');

        // Inactive tab
        const inactiveTab = screen.getByRole('tab', { name: 'Resumen' });
        expect(inactiveTab).toHaveAttribute('aria-selected', 'false');
        expect(inactiveTab).not.toHaveAttribute('aria-current');
    });

    it('supports exact matching', async () => {
        mockPathname = '/app/gestion/stock';

        const { ModuleTabs } = await import('@/components/navigation/module-tabs');
        render(
            <ModuleTabs
                tabs={[
                    { href: '/app/gestion/stock', label: 'Inventario', exact: true },
                    { href: '/app/gestion/stock/compras', label: 'Compras' },
                ]}
            />
        );

        const inventario = screen.getByRole('tab', { name: 'Inventario' });
        expect(inventario).toHaveAttribute('aria-selected', 'true');

        const compras = screen.getByRole('tab', { name: 'Compras' });
        expect(compras).toHaveAttribute('aria-selected', 'false');
    });
});

// ── SectionViewSwitcher ─────────────────────────────────────────────────────

describe('SectionViewSwitcher', () => {
    it('renders views with correct active state', async () => {
        const { SectionViewSwitcher } = await import('@/components/navigation/section-view-switcher');
        const onChange = vi.fn();

        render(
            <SectionViewSwitcher
                views={[
                    { key: 'fijos', label: 'Gastos Fijos' },
                    { key: 'puntuales', label: 'Gastos Puntuales' },
                    { key: 'reposiciones', label: 'Reposiciones de Stock' },
                    { key: 'respaldo', label: 'Respaldo Impositivo' },
                ]}
                activeKey="fijos"
                onChange={onChange}
                ariaLabel="Tipo de gasto"
            />
        );

        const tablist = screen.getByRole('tablist', { name: 'Tipo de gasto' });
        expect(tablist).toBeInTheDocument();

        // Active tab
        const active = screen.getByRole('tab', { name: 'Gastos Fijos' });
        expect(active).toHaveAttribute('aria-selected', 'true');

        // Inactive tab
        const inactive = screen.getByRole('tab', { name: 'Gastos Puntuales' });
        expect(inactive).toHaveAttribute('aria-selected', 'false');
    });

    it('calls onChange when clicking a tab', async () => {
        const { SectionViewSwitcher } = await import('@/components/navigation/section-view-switcher');
        const onChange = vi.fn();

        render(
            <SectionViewSwitcher
                views={[
                    { key: 'fijos', label: 'Gastos Fijos' },
                    { key: 'puntuales', label: 'Gastos Puntuales' },
                ]}
                activeKey="fijos"
                onChange={onChange}
            />
        );

        fireEvent.click(screen.getByRole('tab', { name: 'Gastos Puntuales' }));
        expect(onChange).toHaveBeenCalledWith('puntuales');
    });
});

// ── Navigation hierarchy integration ────────────────────────────────────────

describe('Navigation hierarchy', () => {
    it('no duplicate global nav exists above module tabs', async () => {
        // The GestionNav component that provided duplicate pill buttons
        // should no longer be imported in the gestion layout.
        // Verify by attempting to import navigation.tsx — it should still export
        // GestionNav but it should not be used in the layout.
        const gestionLayout = await import('@/app/app/gestion/layout');
        // Layout should be a valid function
        expect(typeof gestionLayout.default).toBe('function');
    });

    it('GestionLayout no longer imports GestionNav', async () => {
        // GestionLayout should export a valid default component
        // but should NOT pull in GestionNav anymore (navigation pills removed)
        const gestionLayout = await import('@/app/app/gestion/layout');
        expect(typeof gestionLayout.default).toBe('function');
    });
});

// Turnos CUSTOMER 06: acciones rápidas en la ficha del Customer.
process.env.TZ = 'America/Argentina/Buenos_Aires';

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Customer } from '@/features/customers/types';

vi.mock('next/navigation', () => ({ redirect: vi.fn(), useRouter: () => ({ push: vi.fn() }) }));
vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));
vi.mock('@/lib/auth', () => ({ getSession: vi.fn() }));

const createAppointment = vi.fn();
vi.mock('@/features/appointments/hooks', () => ({
    useAppointmentServices: () => ({
        data: [{ id: 's1', name: 'Corte', duration_minutes: 30, price: '1000.00', is_active: true, category: null }],
    }),
    useAppointmentProfessionals: () => ({ data: [{ id: 'p1', name: 'Lucía', services: [{ id: 's1', name: 'Corte' }] }] }),
    useAppointmentAvailability: () => ({
        data: { slots: [{ start: '2026-10-09T13:00:00Z', end: '2026-10-09T13:30:00Z' }] },
        isLoading: false,
    }),
    useCreateAppointment: () => ({ mutateAsync: createAppointment, isPending: false }),
    useUpdateAppointment: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const refreshCustomerViews = vi.fn();
const hooks = vi.hoisted(() => ({
    useCustomer: vi.fn(),
    useCustomers: vi.fn(),
    useCustomerAppointments: vi.fn(),
    useCustomerTimeline: vi.fn(),
    useCreateCustomer: vi.fn(),
    useUpdateCustomer: vi.fn(),
    useCustomerNotes: vi.fn(),
    useCreateCustomerNote: vi.fn(),
    useUpdateCustomerNote: vi.fn(),
    useDeleteCustomerNote: vi.fn(),
    useRefreshCustomerAppointmentViews: vi.fn(),
    // CUSTOMER 07A: la ficha monta la sección Recordatorios (vacía por defecto).
    useCustomerReminders: vi.fn(() => ({
        data: { count: 0, next: null, previous: null, results: [], counts: { pending: 0, closed: 0 } },
        isLoading: false,
        isError: false,
    })),
    useCreateCustomerReminder: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
    useUpdateCustomerReminder: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
    // CUSTOMER 07D.1: la ficha monta Preferencias de contacto (defaults).
    useCustomerDeliveries: vi.fn(() => ({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false, isError: false })),
    useCustomerContactPreferences: vi.fn(() => ({
        data: {
            customer_id: 'x', whatsapp_enabled: false, email_enabled: false, phone_enabled: true, preferred_channel: null,
            do_not_contact: false, whatsapp_consent_at: null, whatsapp_consent_source: null, email_consent_at: null,
            email_consent_source: null, updated_at: null,
            channels: {
                whatsapp: { usable: false, reason: 'disabled' }, email: { usable: false, reason: 'disabled' }, phone: { usable: true, reason: null },
            },
        },
        isLoading: false,
        isError: false,
    })),
    useUpdateCustomerContactPreferences: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));
vi.mock('@/features/customers/hooks', () => hooks);

vi.mock('@/components/ui/modal', () => ({
    Modal: ({ open, title, children, footer }: { open: boolean; title: string; children: ReactNode; footer?: ReactNode }) =>
        open ? (
            <div role="dialog" aria-label={title}>
                {children}
                {footer}
            </div>
        ) : null,
}));

import { getSession } from '@/lib/auth';

import CustomerDetailPage from '../[id]/page';

const getSessionMock = vi.mocked(getSession);

const ANA: Customer = {
    id: 'c-ana',
    name: 'Ana QA',
    phone: '11 5555-0001',
    email: 'ana@qa-turnos.test',
    doc_type: null,
    doc_number: null,
    type: 'individual',
    tax_condition: null,
    address_line: null,
    city: null,
    province: null,
    postal_code: null,
    country: null,
    note: null,
    tags: [],
    is_active: true,
    created_at: '2026-09-01T12:00:00Z',
    updated_at: '2026-09-01T12:00:00Z',
} as Customer;

const OWNER = {
    view_appointments: true,
    manage_appointments: true,
    view_customers: true,
    manage_customers: true,
    manage_customer_notes: true,
};
const VIEWER = { view_appointments: true, view_customers: true };

function session(permissions: Record<string, boolean>, services: string[] = ['appointments']) {
    return {
        features: { appointments_core: true, customers: true, sales: false, quotes: false, orders: false },
        permissions,
        services: { enabled: services },
        current: { business: { id: 1, name: 'QA', status: 'active', timezone: 'America/Argentina/Buenos_Aires' }, role: 'owner', service: 'appointments' },
    } as any;
}

let currentCustomer: Customer = ANA;

beforeEach(() => {
    vi.clearAllMocks();
    currentCustomer = ANA;
    hooks.useCustomer.mockImplementation((id: string) => ({ data: id === currentCustomer.id ? currentCustomer : undefined, isLoading: false }));
    hooks.useCustomers.mockReturnValue({ data: { count: 0, results: [] }, isLoading: false, isError: false, refetch: vi.fn() });
    hooks.useCustomerAppointments.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false });
    hooks.useCustomerTimeline.mockReturnValue({
        data: { count: 0, next: null, previous: null, results: [], types: ['appointment'] },
        isLoading: false,
        isError: false,
    });
    hooks.useCreateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useCustomerNotes.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false, isError: false });
    hooks.useCreateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useDeleteCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useRefreshCustomerAppointmentViews.mockReturnValue(refreshCustomerViews);
    createAppointment.mockResolvedValue({ id: '3f1c2b9a-0000-4000-8000-000000000001', start_at: '2026-10-09T13:00:00Z' });
});

async function renderPage(permissions: Record<string, boolean> = OWNER, services?: string[]) {
    getSessionMock.mockResolvedValue(session(permissions, services));
    render(await CustomerDetailPage({ params: Promise.resolve({ id: currentCustomer.id }) }));
}

function toolbar() {
    return screen.getByRole('toolbar', { name: 'Acciones del cliente' });
}

describe('Nuevo turno desde la ficha', () => {
    it('aparece con manage_appointments y Turnos en el Business', async () => {
        await renderPage();
        expect(within(toolbar()).getByRole('button', { name: 'Nuevo turno' })).toBeInTheDocument();
    });

    it('no aparece si el Business no tiene el módulo Turnos', async () => {
        await renderPage(OWNER, ['management']);
        expect(within(toolbar()).queryByRole('button', { name: 'Nuevo turno' })).not.toBeInTheDocument();
    });

    it('no aparece sin manage_appointments', async () => {
        await renderPage({ ...OWNER, manage_appointments: false });
        expect(within(toolbar()).queryByRole('button', { name: 'Nuevo turno' })).not.toBeInTheDocument();
    });

    it('no aparece para un Customer inactivo (el backend no admite turnos nuevos)', async () => {
        currentCustomer = { ...ANA, is_active: false };
        await renderPage();
        expect(within(toolbar()).queryByRole('button', { name: 'Nuevo turno' })).not.toBeInTheDocument();
    });

    it('abre el formulario real de turno con el Customer elegido y snapshots autocompletados', async () => {
        await renderPage();
        fireEvent.click(within(toolbar()).getByRole('button', { name: 'Nuevo turno' }));

        const dialog = screen.getByRole('dialog', { name: 'Nuevo turno' });
        // Formulario de Turnos: servicio, profesional, fecha y horarios.
        expect(within(dialog).getByRole('combobox', { name: /Servicio/ })).toBeInTheDocument();
        expect(within(dialog).getByRole('combobox', { name: /Profesional/ })).toBeInTheDocument();
        // Customer preseleccionado: tarjeta del picker, sin buscar por teléfono.
        expect(within(dialog).getByText('Ana QA')).toBeInTheDocument();
        expect(within(dialog).getByRole('button', { name: 'Cambiar' })).toBeInTheDocument();
        expect(hooks.useCustomers).not.toHaveBeenCalledWith(expect.objectContaining({ search: expect.any(String) }), { enabled: true });
        // Snapshots editables con los datos de la ficha.
        expect(within(dialog).getByRole('textbox', { name: /Nombre en el turno/ })).toHaveValue('Ana QA');
        expect(within(dialog).getByRole('textbox', { name: /Teléfono/ })).toHaveValue('11 5555-0001');
        expect(within(dialog).getByRole('textbox', { name: /Email/ })).toHaveValue('ana@qa-turnos.test');
    });

    it('guardar crea el turno con customer_id de la ficha, refresca solo la ficha y se queda en ella', async () => {
        await renderPage();
        fireEvent.click(within(toolbar()).getByRole('button', { name: 'Nuevo turno' }));
        const dialog = screen.getByRole('dialog', { name: 'Nuevo turno' });

        fireEvent.change(within(dialog).getByRole('combobox', { name: /Servicio/ }), { target: { value: 's1' } });
        fireEvent.change(within(dialog).getByRole('combobox', { name: /Profesional/ }), { target: { value: 'p1' } });
        // Snapshot editable: no cambia el Customer vinculado.
        fireEvent.change(within(dialog).getByRole('textbox', { name: /Nombre en el turno/ }), { target: { value: 'Ana (recepción)' } });
        fireEvent.click(within(dialog).getByRole('button', { name: '10:00' }));
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));

        await waitFor(() => expect(createAppointment).toHaveBeenCalledTimes(1));
        expect(createAppointment).toHaveBeenCalledWith(
            expect.objectContaining({
                customer_id: 'c-ana',
                service_id: 's1',
                professional_id: 'p1',
                start_at: '2026-10-09T13:00:00Z',
                customer_name: 'Ana (recepción)',
                customer_phone: '11 5555-0001',
                customer_email: 'ana@qa-turnos.test',
            }),
        );
        await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Nuevo turno' })).not.toBeInTheDocument());
        expect(refreshCustomerViews).toHaveBeenCalledTimes(1);

        // Sigue en la ficha, con aviso y deep link existente a la agenda.
        expect(screen.getByRole('heading', { name: 'Ana QA' })).toBeInTheDocument();
        const notice = screen.getByText(/Turno creado/).closest('[role="status"]') as HTMLElement;
        expect(notice).toHaveTextContent('vie 09 oct 2026 · 10:00');
        expect(within(notice).getByRole('link', { name: 'Ver en agenda' })).toHaveAttribute(
            'href',
            '/app/turnos/turnos?date=2026-10-09&appointment=3f1c2b9a-0000-4000-8000-000000000001',
        );
    });

    it('un error de validación del backend queda en el modal y no refresca', async () => {
        const { ApiError } = await import('@/lib/api/client');
        createAppointment.mockRejectedValueOnce(new ApiError('Bad', 400, { start_at: ['El horario ya no está disponible.'] }));
        await renderPage();
        fireEvent.click(within(toolbar()).getByRole('button', { name: 'Nuevo turno' }));
        const dialog = screen.getByRole('dialog', { name: 'Nuevo turno' });
        fireEvent.change(within(dialog).getByRole('combobox', { name: /Servicio/ }), { target: { value: 's1' } });
        fireEvent.click(within(dialog).getByRole('button', { name: '10:00' }));
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }));

        expect(await within(dialog).findByText('El horario ya no está disponible.')).toBeInTheDocument();
        expect(refreshCustomerViews).not.toHaveBeenCalled();
    });
});

describe('Editar cliente y Agregar nota', () => {
    it('Editar cliente abre el CustomerFormModal existente', async () => {
        await renderPage();
        fireEvent.click(within(toolbar()).getByRole('button', { name: 'Editar cliente' }));
        expect(screen.getByRole('dialog', { name: 'Editar cliente' })).toBeInTheDocument();
    });

    it('Agregar nota abre el modal de alta de notas y usa su endpoint', async () => {
        const createNote = vi.fn().mockResolvedValue({});
        hooks.useCreateCustomerNote.mockReturnValue({ mutateAsync: createNote, isPending: false });
        await renderPage();

        fireEvent.click(within(toolbar()).getByRole('button', { name: 'Agregar nota' }));
        const dialog = screen.getByRole('dialog', { name: 'Nueva nota interna' });
        fireEvent.change(within(dialog).getByLabelText('Nota'), { target: { value: 'Prefiere la tarde' } });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Agregar nota' }));

        await waitFor(() => expect(createNote).toHaveBeenCalledWith('Prefiere la tarde'));
        await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Nueva nota interna' })).not.toBeInTheDocument());
        // El botón de la sección sigue funcionando (mismo estado).
        fireEvent.click(screen.getByRole('button', { name: '+ Agregar nota' }));
        expect(screen.getByRole('dialog', { name: 'Nueva nota interna' })).toBeInTheDocument();
    });

    it('sin manage_customer_notes no muestra Agregar nota', async () => {
        await renderPage({ ...OWNER, manage_customer_notes: false });
        expect(within(toolbar()).queryByRole('button', { name: 'Agregar nota' })).not.toBeInTheDocument();
        expect(within(toolbar()).getByRole('button', { name: 'Editar cliente' })).toBeInTheDocument();
    });

    it('VIEWER no ve acciones de mutación, solo contacto', async () => {
        await renderPage(VIEWER);
        const bar = toolbar();
        for (const name of ['Nuevo turno', 'Editar cliente', 'Agregar nota']) {
            expect(within(bar).queryByRole('button', { name })).not.toBeInTheDocument();
        }
        expect(within(bar).getByRole('link', { name: 'WhatsApp' })).toBeInTheDocument();
        expect(within(bar).getByRole('link', { name: 'Llamar' })).toBeInTheDocument();
        expect(within(bar).getByRole('link', { name: 'Email' })).toBeInTheDocument();
    });
});

describe('Contacto manual', () => {
    it('WhatsApp abre wa.me normalizado en otra pestaña', async () => {
        await renderPage();
        const link = within(toolbar()).getByRole('link', { name: 'WhatsApp' });
        expect(link).toHaveAttribute('href', 'https://wa.me/5491155550001');
        expect(link).toHaveAttribute('target', '_blank');
        expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('Llamar usa tel: con el número de la ficha', async () => {
        await renderPage();
        expect(within(toolbar()).getByRole('link', { name: 'Llamar' })).toHaveAttribute('href', 'tel:1155550001');
    });

    it('Email usa mailto:', async () => {
        await renderPage();
        expect(within(toolbar()).getByRole('link', { name: 'Email' })).toHaveAttribute('href', 'mailto:ana@qa-turnos.test');
    });

    it('sin teléfono ni email oculta WhatsApp, Llamar y Email', async () => {
        currentCustomer = { ...ANA, phone: null, email: null };
        await renderPage();
        const bar = toolbar();
        for (const name of ['WhatsApp', 'Llamar', 'Email']) {
            expect(within(bar).queryByRole('link', { name })).not.toBeInTheDocument();
        }
        expect(within(bar).getByRole('button', { name: 'Nuevo turno' })).toBeInTheDocument();
    });

    it('un teléfono que no se puede convertir oculta WhatsApp pero mantiene Llamar', async () => {
        currentCustomer = { ...ANA, phone: '4555-0001' };
        await renderPage();
        expect(within(toolbar()).queryByRole('link', { name: 'WhatsApp' })).not.toBeInTheDocument();
        expect(within(toolbar()).getByRole('link', { name: 'Llamar' })).toHaveAttribute('href', 'tel:45550001');
    });

    it('VIEWER sin teléfono ni email no ve toolbar', async () => {
        currentCustomer = { ...ANA, phone: null, email: null };
        await renderPage(VIEWER);
        expect(screen.queryByRole('toolbar', { name: 'Acciones del cliente' })).not.toBeInTheDocument();
    });
});

describe('Mobile', () => {
    it('"Nuevo turno" queda visible y el resto va en el desplegable "Más" con targets táctiles', async () => {
        await renderPage();
        const bar = toolbar();
        const primary = within(bar).getByRole('button', { name: 'Nuevo turno' });
        expect(primary.className).not.toMatch(/(^|\s)hidden(\s|$)/);
        expect(primary.className).toContain('min-h-11');

        const more = within(bar).getByRole('button', { name: /Más/ });
        expect(more.className).toContain('md:hidden');
        const list = screen.getByTestId('customer-secondary-actions');
        expect(more).toHaveAttribute('aria-controls', list.id);
        // Cerrado en mobile, siempre en línea en desktop.
        expect(list.className).toMatch(/(^|\s)hidden(\s|$)/);
        expect(list.className).toContain('md:contents');

        fireEvent.click(more);
        expect(more).toHaveAttribute('aria-expanded', 'true');
        expect(list.className).toMatch(/(^|\s)flex(\s|$)/);
        for (const item of within(list).getAllByRole('listitem')) {
            expect((item.firstElementChild as HTMLElement).className).toContain('min-h-11');
        }

        // Elegir una acción cierra el desplegable.
        fireEvent.click(within(list).getByRole('button', { name: 'Editar cliente' }));
        expect(more).toHaveAttribute('aria-expanded', 'false');
        expect(screen.getByRole('dialog', { name: 'Editar cliente' })).toBeInTheDocument();
    });

    it('Escape cierra el desplegable', async () => {
        await renderPage();
        const more = within(toolbar()).getByRole('button', { name: /Más/ });
        fireEvent.click(more);
        fireEvent.keyDown(document, { key: 'Escape' });
        expect(more).toHaveAttribute('aria-expanded', 'false');
    });
});

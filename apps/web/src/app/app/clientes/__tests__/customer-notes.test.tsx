import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// CUSTOMER 04C/04C.1: "Notas internas" en la ficha `/app/clientes/[id]`.
// Lectura para todo rol con `view_customers`; alta/edición/borrado solo con
// `manage_customer_notes` (owner/admin/manager). `manage_customers` NO alcanza
// (cashier/staff lo tienen). Las mutaciones no tocan ficha ni timeline.

vi.mock('next/navigation', () => ({ redirect: vi.fn(), useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/lib/auth', () => ({ getSession: vi.fn() }));
vi.mock('next/link', () => ({
    __esModule: true,
    default: ({ href, children, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
        <a href={href} {...props}>{children}</a>
    ),
}));

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

import { ApiError } from '@/lib/api/client';
import { getSession } from '@/lib/auth';

import CustomerDetailPage from '../[id]/page';
import { CustomerDetailClient } from '../[id]/customer-detail-client';

const getSessionMock = vi.mocked(getSession);

const TZ = 'America/Argentina/Buenos_Aires';

// Permisos reales de Gestión relevantes por rol (`accounts/rbac.py`).
const ROLE_PERMS: Record<string, Record<string, boolean>> = {
    manager: { view_customers: true, manage_customers: true, manage_customer_notes: true, view_sales: true },
    cashier: { view_customers: true, manage_customers: true, view_sales: true },
    staff: { view_customers: true, manage_customers: true, view_sales: true },
    viewer: { view_customers: true, view_sales: true },
};

function gestionSession(role: keyof typeof ROLE_PERMS) {
    return {
        features: { customers: true, sales: true, quotes: true, orders: true },
        permissions: ROLE_PERMS[role],
        current: { business: { timezone: TZ } },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
}

async function renderPageAs(role: keyof typeof ROLE_PERMS) {
    getSessionMock.mockResolvedValue(gestionSession(role));
    render(await CustomerDetailPage({ params: Promise.resolve({ id: 'c-1' }) }));
}


const CUSTOMER = {
    id: 'c-1',
    name: 'Ana Cliente',
    doc_type: null,
    doc_number: null,
    email: null,
    phone: '11 5555-0001',
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
};

const NOTE_RECENT = {
    id: 'n-2',
    body: 'Prefiere turnos después de las 17.',
    author: { id: 'u-1', name: 'Lucía' },
    // 13:00Z = 10:00 del 02/10 en Buenos Aires.
    created_at: '2026-10-02T13:00:00.000001Z',
    updated_at: '2026-10-02T13:00:00.000009Z',
};

const NOTE_OLD = {
    id: 'n-1',
    body: 'Llamar antes de confirmar.\nNo acepta WhatsApp.',
    author: null,
    created_at: '2026-09-20T15:00:00Z',
    updated_at: '2026-09-25T15:00:00Z',
};

const TIMELINE_EVENT = {
    type: 'sale',
    id: 'sale:s-1',
    source_id: 's-1',
    occurred_at: '2026-10-01T15:00:00Z',
    title: 'Venta #12',
    subtitle: 'Tarjeta',
    status: 'completed',
    status_display: 'Completada',
    amount: '2500.00',
    currency: null,
    href: '/app/gestion/ventas/s-1',
    metadata: { number: 12, items_count: 3, payment_method: 'card', payment_method_display: 'Tarjeta', cancelled_at: null, invoice: null },
};

const mutations = {
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
};

function notesPage(results: unknown[], count = results.length) {
    return { data: { count, next: null, previous: null, results }, isLoading: false, isError: false };
}

function renderDetail({ canManageNotes = true, canManage = true }: { canManageNotes?: boolean; canManage?: boolean } = {}) {
    return render(
        <CustomerDetailClient
            customerId="c-1"
            canManage={canManage}
            canManageNotes={canManageNotes}
            canViewSales
            canViewQuotes={false}
            businessTimeZone={TZ}
        />,
    );
}

function expectNoMutationActions() {
    const section = notesSection();
    expect(within(section).queryByRole('button', { name: '+ Agregar nota' })).not.toBeInTheDocument();
    expect(within(section).queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument();
    expect(within(section).queryByRole('button', { name: 'Eliminar' })).not.toBeInTheDocument();
}

function notesSection() {
    return screen.getByRole('region', { name: 'Notas internas' });
}

function noteRows() {
    return within(notesSection()).getAllByTestId('customer-note');
}

beforeEach(() => {
    vi.clearAllMocks();
    hooks.useCustomer.mockReturnValue({ data: CUSTOMER, isLoading: false });
    hooks.useCustomerAppointments.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false });
    hooks.useCustomerTimeline.mockReturnValue({
        data: { count: 1, next: null, previous: null, results: [TIMELINE_EVENT], types: ['sale'] },
        isLoading: false,
        isError: false,
    });
    hooks.useCreateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useCustomerNotes.mockReturnValue(notesPage([NOTE_RECENT, NOTE_OLD]));
    mutations.create.mockResolvedValue({});
    mutations.update.mockResolvedValue({});
    mutations.remove.mockResolvedValue(undefined);
    hooks.useCreateCustomerNote.mockReturnValue({ mutateAsync: mutations.create, isPending: false });
    hooks.useUpdateCustomerNote.mockReturnValue({ mutateAsync: mutations.update, isPending: false });
    hooks.useDeleteCustomerNote.mockReturnValue({ mutateAsync: mutations.remove, isPending: false });
});

describe('Notas internas en la ficha (CUSTOMER 04C)', () => {
    it('renderiza las notas en el orden del backend con fecha local, autor y texto', () => {
        renderDetail();
        expect(hooks.useCustomerNotes).toHaveBeenCalledWith('c-1', { limit: 20 });

        const [recent, old] = noteRows();
        expect(within(recent).getByText('02 oct 2026 · Lucía')).toBeInTheDocument();
        expect(within(recent).getByText('Prefiere turnos después de las 17.')).toBeInTheDocument();
        // Autor eliminado + editada (updated_at muy posterior a created_at).
        expect(within(old).getByText('20 sep 2026 · Usuario eliminado · editada')).toBeInTheDocument();
        expect(within(old).getByText(/Llamar antes de confirmar\.\s+No acepta WhatsApp\./)).toHaveClass('whitespace-pre-wrap', 'break-words');
    });

    it('muestra el empty state si no hay notas', () => {
        hooks.useCustomerNotes.mockReturnValue(notesPage([]));
        renderDetail();
        expect(within(notesSection()).getByText('No hay notas internas para este cliente.')).toBeInTheDocument();
        expect(within(notesSection()).queryAllByTestId('customer-note')).toHaveLength(0);
    });

    it('agrega una nota: trim, POST y cierra el modal', async () => {
        renderDetail();
        fireEvent.click(within(notesSection()).getByRole('button', { name: '+ Agregar nota' }));

        const dialog = screen.getByRole('dialog', { name: 'Nueva nota interna' });
        const save = within(dialog).getByRole('button', { name: 'Agregar nota' });
        expect(save).toBeDisabled();
        fireEvent.change(within(dialog).getByLabelText('Nota'), { target: { value: '   ' } });
        expect(save).toBeDisabled();

        fireEvent.change(within(dialog).getByLabelText('Nota'), { target: { value: '  Cliente frecuente  ' } });
        fireEvent.click(save);

        await waitFor(() => expect(mutations.create).toHaveBeenCalledWith('Cliente frecuente'));
        await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Nueva nota interna' })).not.toBeInTheDocument());
    });

    it('edita una nota reutilizando el formulario precargado (PATCH)', async () => {
        renderDetail();
        fireEvent.click(within(noteRows()[0]).getByRole('button', { name: 'Editar' }));

        const dialog = screen.getByRole('dialog', { name: 'Editar nota' });
        const textarea = within(dialog).getByLabelText('Nota');
        expect(textarea).toHaveValue('Prefiere turnos después de las 17.');
        fireEvent.change(textarea, { target: { value: 'Prefiere turnos después de las 18.' } });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar cambios' }));

        await waitFor(() =>
            expect(mutations.update).toHaveBeenCalledWith({ noteId: 'n-2', body: 'Prefiere turnos después de las 18.' }),
        );
        await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Editar nota' })).not.toBeInTheDocument());
    });

    it('elimina solo después de confirmar; cancelar no borra', async () => {
        renderDetail();
        fireEvent.click(within(noteRows()[1]).getByRole('button', { name: 'Eliminar' }));

        let dialog = screen.getByRole('dialog', { name: '¿Eliminar esta nota?' });
        expect(within(dialog).getByText(/Llamar antes de confirmar/)).toBeInTheDocument();
        fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }));
        expect(mutations.remove).not.toHaveBeenCalled();
        expect(screen.queryByRole('dialog', { name: '¿Eliminar esta nota?' })).not.toBeInTheDocument();

        fireEvent.click(within(noteRows()[1]).getByRole('button', { name: 'Eliminar' }));
        dialog = screen.getByRole('dialog', { name: '¿Eliminar esta nota?' });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Eliminar nota' }));

        await waitFor(() => expect(mutations.remove).toHaveBeenCalledWith('n-1'));
        await waitFor(() => expect(screen.queryByRole('dialog', { name: '¿Eliminar esta nota?' })).not.toBeInTheDocument());
    });

    it('muestra el error del backend al guardar y mantiene el modal abierto', async () => {
        mutations.create.mockRejectedValue(new ApiError('Bad request', 400, { body: ['La nota no puede estar vacía.'] }));
        renderDetail();
        fireEvent.click(within(notesSection()).getByRole('button', { name: '+ Agregar nota' }));
        const dialog = screen.getByRole('dialog', { name: 'Nueva nota interna' });
        fireEvent.change(within(dialog).getByLabelText('Nota'), { target: { value: 'Hola' } });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Agregar nota' }));

        expect(await within(dialog).findByRole('alert')).toHaveTextContent('La nota no puede estar vacía.');
        expect(screen.getByRole('dialog', { name: 'Nueva nota interna' })).toBeInTheDocument();
    });

    it('muestra el error del backend al eliminar (403)', async () => {
        mutations.remove.mockRejectedValue(
            new ApiError('Forbidden', 403, { code: 'permission_denied', message: 'No tenés permiso para esta acción.' }),
        );
        renderDetail();
        fireEvent.click(within(noteRows()[0]).getByRole('button', { name: 'Eliminar' }));
        const dialog = screen.getByRole('dialog', { name: '¿Eliminar esta nota?' });
        fireEvent.click(within(dialog).getByRole('button', { name: 'Eliminar nota' }));
        expect(await within(dialog).findByRole('alert')).toHaveTextContent('No tenés permiso para esta acción.');
    });

    it('muestra el error si no se pueden cargar las notas', () => {
        hooks.useCustomerNotes.mockReturnValue({
            data: undefined,
            isLoading: false,
            isError: true,
            error: new ApiError('Error', 500, { detail: 'Error interno.' }),
        });
        renderDetail();
        expect(within(notesSection()).getByRole('alert')).toHaveTextContent('Error interno.');
    });

    it('sin manage_customer_notes no hay acciones aunque tenga manage_customers', () => {
        renderDetail({ canManageNotes: false, canManage: true });
        expect(noteRows()).toHaveLength(2);
        expectNoMutationActions();
        // El permiso general de Clientes sigue intacto.
        expect(screen.getByRole('button', { name: 'Editar cliente' })).toBeInTheDocument();
    });

    it.each(['viewer', 'cashier', 'staff'] as const)('%s (página real): ve las notas pero no ve acciones', async (role) => {
        await renderPageAs(role);
        expect(noteRows()).toHaveLength(2);
        expect(within(notesSection()).getByText('Prefiere turnos después de las 17.')).toBeInTheDocument();
        expectNoMutationActions();
    });

    it('cashier/staff conservan "Editar cliente" (manage_customers sin cambios)', async () => {
        await renderPageAs('cashier');
        expect(screen.getByRole('button', { name: 'Editar cliente' })).toBeInTheDocument();
    });

    it('manager (página real): ve agregar, editar y eliminar en cada nota', async () => {
        await renderPageAs('manager');
        expect(within(notesSection()).getByRole('button', { name: '+ Agregar nota' })).toBeInTheDocument();
        for (const row of noteRows()) {
            expect(within(row).getByRole('button', { name: 'Editar' })).toBeInTheDocument();
            expect(within(row).getByRole('button', { name: 'Eliminar' })).toBeInTheDocument();
        }
    });

    it('los modales de notas no muestran el rótulo genérico "Formulario"', () => {
        renderDetail();
        fireEvent.click(within(notesSection()).getByRole('button', { name: '+ Agregar nota' }));
        expect(within(screen.getByRole('dialog', { name: 'Nueva nota interna' })).queryByText('Formulario')).not.toBeInTheDocument();
        fireEvent.click(screen.getAllByRole('button', { name: 'Cancelar' })[0]);

        fireEvent.click(within(noteRows()[0]).getByRole('button', { name: 'Editar' }));
        expect(within(screen.getByRole('dialog', { name: 'Editar nota' })).queryByText('Formulario')).not.toBeInTheDocument();
        fireEvent.click(screen.getAllByRole('button', { name: 'Cancelar' })[0]);

        fireEvent.click(within(noteRows()[0]).getByRole('button', { name: 'Eliminar' }));
        expect(within(screen.getByRole('dialog', { name: '¿Eliminar esta nota?' })).queryByText('Formulario')).not.toBeInTheDocument();
    });

    it('pagina con "Ver más notas" aumentando el limit', () => {
        hooks.useCustomerNotes.mockReturnValue(notesPage([NOTE_RECENT, NOTE_OLD], 25));
        renderDetail();
        fireEvent.click(within(notesSection()).getByRole('button', { name: 'Ver más notas' }));
        expect(hooks.useCustomerNotes).toHaveBeenLastCalledWith('c-1', { limit: 40 });
    });

    it('la ficha y la timeline siguen funcionando junto a las notas', () => {
        renderDetail();
        expect(screen.getByRole('heading', { name: 'Ana Cliente' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Editar cliente' })).toBeInTheDocument();
        const history = screen.getByRole('region', { name: 'Historial' });
        expect(within(history).getByText('Venta #12')).toBeInTheDocument();
        // Las notas NO entran a la timeline (slice futuro).
        expect(within(history).queryByText('Prefiere turnos después de las 17.')).not.toBeInTheDocument();
    });
});

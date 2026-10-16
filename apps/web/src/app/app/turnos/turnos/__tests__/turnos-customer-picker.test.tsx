// Turnos CUSTOMER 05: CustomerPicker en Nuevo / Editar turno.
process.env.TZ = 'America/Argentina/Buenos_Aires';

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Appointment } from '@/features/appointments/types';
import type { Customer, CustomerFilters, CustomerPayload } from '@/features/customers/types';

const createAppointment = vi.fn();
const updateAppointment = vi.fn();
const createCustomer = vi.fn();
const searchCalls: CustomerFilters[] = [];
let appointmentsData: Appointment[] = [];
let customersDb: Customer[] = [];
let searchError = false;

vi.mock('@/features/appointments/hooks', () => ({
    useAppointments: () => ({ data: appointmentsData, isLoading: false, isError: false }),
    useAppointmentServices: () => ({
        data: [{ id: 's1', name: 'Corte', duration_minutes: 30, price: '1000.00', is_active: true, category: null }],
    }),
    useAppointmentProfessionals: () => ({
        data: [{ id: 'p1', name: 'Ana', services: [{ id: 's1', name: 'Corte' }] }],
    }),
    useAppointmentAvailability: () => ({
        data: { slots: [{ start: '2026-10-05T13:00:00Z', end: '2026-10-05T13:30:00Z' }] },
        isLoading: false,
    }),
    useCreateAppointment: () => ({ mutateAsync: createAppointment, isPending: false }),
    useUpdateAppointment: () => ({ mutateAsync: updateAppointment, isPending: false }),
    useCancelAppointment: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('@/features/customers/hooks', () => ({
    useCustomers: (filters: CustomerFilters, options?: { enabled?: boolean }) => {
        if (options?.enabled === false) return { data: undefined, isLoading: false, isError: false, refetch: vi.fn() };
        searchCalls.push(filters);
        if (searchError) return { data: undefined, isLoading: false, isError: true, refetch: vi.fn() };
        const term = (filters.search ?? '').toLowerCase();
        const results = customersDb.filter((c) =>
            [c.name, c.phone ?? '', c.email ?? ''].some((value) => value.toLowerCase().includes(term)),
        );
        return { data: { count: results.length, next: null, previous: null, results }, isLoading: false, isError: false, refetch: vi.fn() };
    },
    useCustomer: (id: string) => ({
        data: id ? customersDb.find((c) => c.id === id) : undefined,
        isLoading: false,
    }),
    useCreateCustomer: () => ({ mutateAsync: createCustomer, isPending: false }),
    useUpdateCustomer: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('@/components/ui/modal', () => ({
    Modal: ({ open, title, children, footer }: { open: boolean; title: string; children: ReactNode; footer?: ReactNode }) =>
        open ? (
            <div role="dialog" aria-label={title}>
                {children}
                {footer}
            </div>
        ) : null,
}));

import { TurnosClient } from '../turnos-client';

function customer(id: string, name: string, phone: string | null, email: string | null = null, overrides: Partial<Customer> = {}): Customer {
    return {
        id, name, phone, email, doc_type: null, doc_number: null, type: 'individual', tax_condition: null,
        address_line: null, city: null, province: null, postal_code: null, country: null, note: null, tags: [],
        is_active: true, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z', ...overrides,
    };
}

function appointment(overrides: Partial<Appointment> = {}): Appointment {
    return {
        id: 'a1',
        service: { id: 's1', name: 'Corte', duration_minutes: 30, price: '1000.00', is_active: true, category: null },
        professional: { id: 'p1', name: 'Ana' } as Appointment['professional'],
        customer_id: 'c1',
        customer_name: 'Juan - recepción',
        customer_phone: '1140000001',
        customer_email: '',
        start_at: '2026-10-05T13:00:00Z',
        end_at: '2026-10-05T13:30:00Z',
        status: 'confirmed',
        status_display: 'Confirmado',
        effective_status: 'confirmed',
        effective_status_display: 'Confirmado',
        expires_at: null,
        payment_summary: null,
        notes: 'Trae foto',
        source: 'manual',
        service_name: 'Corte',
        service_duration_minutes: 30,
        service_price: '1000.00',
        deposit_type: 'none',
        deposit_value: '0',
        created_at: '2026-09-20T12:00:00Z',
        updated_at: '2026-09-20T12:00:00Z',
        ...overrides,
    } as Appointment;
}

function renderClient(props: { canPickCustomer?: boolean; canCreateCustomer?: boolean } = {}) {
    return render(
        <TurnosClient
            canManage
            canPickCustomer={props.canPickCustomer ?? true}
            canCreateCustomer={props.canCreateCustomer ?? true}
            timeZone="America/Argentina/Buenos_Aires"
            initialDate="2026-10-05"
        />,
    );
}

function dialog() {
    return screen.getByRole('dialog', { name: /turno/i });
}

function openNew() {
    fireEvent.click(screen.getAllByRole('button', { name: /nuevo turno/i })[0]);
    return dialog();
}

function search(term: string) {
    fireEvent.change(screen.getByPlaceholderText(/buscar cliente por nombre/i), { target: { value: term } });
}

function fillAppointment(modal: HTMLElement) {
    const [serviceSelect, professionalSelect] = within(modal).getAllByRole('combobox');
    fireEvent.change(serviceSelect, { target: { value: 's1' } });
    fireEvent.change(professionalSelect, { target: { value: 'p1' } });
    fireEvent.click(within(modal).getByRole('button', { name: '10:00' }));
    fireEvent.change(within(modal).getByLabelText('Notas'), { target: { value: 'Trae foto' } });
}

beforeEach(() => {
    appointmentsData = [];
    customersDb = [
        customer('c1', 'Juan Pérez', '+54 9 11 4000-0001', 'juan@example.com'),
        customer('c2', 'María Gómez', '11 4000-0002'),
    ];
    searchCalls.length = 0;
    searchError = false;
    createAppointment.mockReset().mockResolvedValue({});
    updateAppointment.mockReset().mockResolvedValue({});
    createCustomer.mockReset();
});

afterEach(() => {
    vi.useRealTimers();
});

describe('CustomerPicker en Nuevo turno', () => {
    it('busca por nombre con debounce y mínimo de caracteres', async () => {
        renderClient();
        const modal = openNew();

        search('J');
        expect(screen.getByText(/escribí al menos 2 caracteres/i)).toBeInTheDocument();

        search('Juan');
        expect(within(modal).getByRole('status')).toHaveTextContent(/buscando clientes/i);
        const list = await screen.findByRole('list', { name: /resultados de clientes/i });
        expect(within(list).getByText('Juan Pérez')).toBeInTheDocument();
        expect(within(list).getByText(/juan@example.com/)).toBeInTheDocument();
        expect(within(list).queryByText('María Gómez')).not.toBeInTheDocument();
        expect(searchCalls.every((call) => call.limit === 8 && (call.search ?? '').length >= 2)).toBe(true);
    });

    it('busca por teléfono', async () => {
        renderClient();
        openNew();
        search('4000-0002');
        const list = await screen.findByRole('list', { name: /resultados de clientes/i });
        expect(within(list).getByText('María Gómez')).toBeInTheDocument();
    });

    it('seleccionar autocompleta snapshots, conserva el turno y envía customer_id', async () => {
        renderClient();
        const modal = openNew();
        fillAppointment(modal);

        search('Juan');
        fireEvent.click(await screen.findByRole('button', { name: /juan pérez/i }));

        const card = screen.getByTestId('customer-picker-selected');
        expect(within(card).getByText('Juan Pérez')).toBeInTheDocument();
        expect(within(card).getByRole('link', { name: /ver ficha/i })).toHaveAttribute('href', '/app/clientes/c1');
        expect(within(modal).getByLabelText(/nombre en el turno/i)).toHaveValue('Juan Pérez');
        expect(within(modal).getByLabelText(/teléfono/i)).toHaveValue('+54 9 11 4000-0001');
        expect(within(modal).getByLabelText(/email/i)).toHaveValue('juan@example.com');

        // El snapshot se puede editar sin tocar el Customer.
        fireEvent.change(within(modal).getByLabelText(/nombre en el turno/i), { target: { value: 'Juan - recepción' } });
        fireEvent.click(within(modal).getByRole('button', { name: 'Guardar' }));

        await waitFor(() => expect(createAppointment).toHaveBeenCalledTimes(1));
        expect(createAppointment.mock.calls[0][0]).toMatchObject({
            customer_id: 'c1',
            customer_name: 'Juan - recepción',
            customer_phone: '+54 9 11 4000-0001',
            service_id: 's1',
            professional_id: 'p1',
            start_at: '2026-10-05T13:00:00Z',
            notes: 'Trae foto',
        });
    });

    it('cambiar Customer reemplaza la selección y los snapshots', async () => {
        renderClient();
        const modal = openNew();
        search('Juan');
        fireEvent.click(await screen.findByRole('button', { name: /juan pérez/i }));

        fireEvent.click(screen.getByRole('button', { name: 'Cambiar' }));
        search('María');
        fireEvent.click(await screen.findByRole('button', { name: /maría gómez/i }));

        expect(within(screen.getByTestId('customer-picker-selected')).getByText('María Gómez')).toBeInTheDocument();
        expect(within(modal).getByLabelText(/teléfono/i)).toHaveValue('11 4000-0002');
        expect(within(modal).getByLabelText(/email/i)).toHaveValue('');
    });

    it('crea Customer inline, lo selecciona y no pierde datos del turno', async () => {
        const created = customer('c9', 'Lucía Nueva', '11 5000-0000');
        createCustomer.mockImplementation(async (payload: CustomerPayload) => {
            expect(payload.phone).toBe('11 5000-0000');
            return created;
        });
        renderClient();
        const modal = openNew();
        fillAppointment(modal);

        search('11 5000-0000');
        expect(await screen.findByText(/no encontramos clientes/i)).toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: /crear nuevo cliente/i }));

        const customerModal = screen.getByRole('dialog', { name: 'Nuevo cliente' });
        // Lo tipeado (teléfono) precarga el alta.
        expect(within(customerModal).getByDisplayValue('11 5000-0000')).toBeInTheDocument();
        fireEvent.change(within(customerModal).getAllByRole('textbox')[0], { target: { value: 'Lucía Nueva' } });
        fireEvent.click(within(customerModal).getByRole('button', { name: 'Crear cliente' }));

        await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Nuevo cliente' })).not.toBeInTheDocument());
        expect(within(screen.getByTestId('customer-picker-selected')).getByText('Lucía Nueva')).toBeInTheDocument();
        expect(within(modal).getByLabelText(/nombre en el turno/i)).toHaveValue('Lucía Nueva');
        expect(within(modal).getByLabelText('Notas')).toHaveValue('Trae foto');
        expect(within(modal).getByRole('button', { name: '10:00' }).className).toMatch(/bg-slate-900/);

        fireEvent.click(within(modal).getByRole('button', { name: 'Guardar' }));
        await waitFor(() => expect(createAppointment).toHaveBeenCalledTimes(1));
        expect(createAppointment.mock.calls[0][0]).toMatchObject({ customer_id: 'c9', service_id: 's1', notes: 'Trae foto' });
    });

    it('sin permiso de crear Customers no ve "+ Crear nuevo cliente"', async () => {
        renderClient({ canCreateCustomer: false });
        openNew();
        search('zzz');
        expect(await screen.findByText(/no encontramos clientes/i)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /crear nuevo cliente/i })).not.toBeInTheDocument();
    });

    it('sin view_customers no hay picker y el turno sigue sin customer_id', async () => {
        renderClient({ canPickCustomer: false, canCreateCustomer: false });
        const modal = openNew();
        expect(screen.queryByPlaceholderText(/buscar cliente/i)).not.toBeInTheDocument();
        fillAppointment(modal);
        fireEvent.change(within(modal).getByLabelText(/^cliente/i), { target: { value: 'Sin Ficha' } });
        fireEvent.change(within(modal).getByLabelText(/teléfono/i), { target: { value: '11 6000-0000' } });
        fireEvent.click(within(modal).getByRole('button', { name: 'Guardar' }));
        await waitFor(() => expect(createAppointment).toHaveBeenCalledTimes(1));
        expect(createAppointment.mock.calls[0][0].customer_id).toBeUndefined();
    });

    it('muestra el error de búsqueda', async () => {
        searchError = true;
        renderClient();
        openNew();
        search('Juan');
        expect(await screen.findByRole('alert')).toHaveTextContent(/no pudimos buscar clientes/i);
        expect(screen.getByRole('button', { name: /reintentar/i })).toBeInTheDocument();
    });

    it('layout usable en mobile: tarjeta apilada, textos truncados y resultados con scroll propio', async () => {
        renderClient();
        openNew();
        search('Juan');
        const list = await screen.findByRole('list', { name: /resultados de clientes/i });
        expect(list.className).toMatch(/max-h-60/);
        expect(list.className).toMatch(/overflow-y-auto/);
        fireEvent.click(within(list).getByRole('button', { name: /juan pérez/i }));
        const card = screen.getByTestId('customer-picker-selected');
        expect(card.className).toMatch(/flex-col/);
        expect(card.className).toMatch(/sm:flex-row/);
        expect(within(card).getByText('Juan Pérez').className).toMatch(/truncate/);
    });
});

describe('CustomerPicker en Editar turno', () => {
    function openEdit() {
        fireEvent.click(screen.getByRole('button', { name: /editar/i }));
        return dialog();
    }

    it('muestra el Customer vinculado (ficha) y los snapshots actuales; guardar conserva el FK', async () => {
        appointmentsData = [appointment()];
        renderClient();
        const modal = openEdit();

        const card = screen.getByTestId('customer-picker-selected');
        expect(within(card).getByText('Juan Pérez')).toBeInTheDocument();
        expect(within(modal).getByLabelText(/nombre en el turno/i)).toHaveValue('Juan - recepción');

        fireEvent.click(within(modal).getByRole('button', { name: 'Guardar' }));
        await waitFor(() => expect(updateAppointment).toHaveBeenCalledTimes(1));
        expect(updateAppointment.mock.calls[0][0].payload).toMatchObject({ customer_id: 'c1', customer_name: 'Juan - recepción' });
    });

    it('cambiar Customer al editar envía el nuevo customer_id; "Mantener" vuelve al actual', async () => {
        appointmentsData = [appointment()];
        renderClient();
        const modal = openEdit();

        fireEvent.click(screen.getByRole('button', { name: 'Cambiar' }));
        fireEvent.click(screen.getByRole('button', { name: /mantener cliente actual/i }));
        expect(within(screen.getByTestId('customer-picker-selected')).getByText('Juan Pérez')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'Cambiar' }));
        search('María');
        fireEvent.click(await screen.findByRole('button', { name: /maría gómez/i }));
        fireEvent.click(within(modal).getByRole('button', { name: 'Guardar' }));

        await waitFor(() => expect(updateAppointment).toHaveBeenCalledTimes(1));
        expect(updateAppointment.mock.calls[0][0]).toMatchObject({
            id: 'a1',
            payload: { customer_id: 'c2', customer_name: 'María Gómez', customer_phone: '11 4000-0002' },
        });
    });

    it('legacy customer=NULL: snapshots visibles, sin autovínculo al guardar', async () => {
        appointmentsData = [appointment({ customer_id: null })];
        renderClient();
        const modal = openEdit();

        expect(screen.queryByTestId('customer-picker-selected')).not.toBeInTheDocument();
        expect(screen.getByPlaceholderText(/buscar cliente/i)).toHaveValue('');
        expect(within(modal).getByLabelText(/nombre en el turno/i)).toHaveValue('Juan - recepción');

        fireEvent.click(within(modal).getByRole('button', { name: 'Guardar' }));
        await waitFor(() => expect(updateAppointment).toHaveBeenCalledTimes(1));
        expect(updateAppointment.mock.calls[0][0].payload.customer_id).toBeUndefined();
    });

    it('legacy customer=NULL puede vincularse eligiendo un Customer', async () => {
        appointmentsData = [appointment({ customer_id: null })];
        renderClient();
        const modal = openEdit();
        search('Juan');
        fireEvent.click(await screen.findByRole('button', { name: /juan pérez/i }));
        fireEvent.click(within(modal).getByRole('button', { name: 'Guardar' }));
        await waitFor(() => expect(updateAppointment).toHaveBeenCalledTimes(1));
        expect(updateAppointment.mock.calls[0][0].payload.customer_id).toBe('c1');
    });
});

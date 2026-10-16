import { fireEvent, render, screen, within } from '@testing-library/react';
import type { AnchorHTMLAttributes } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// CUSTOMER 04A: la ficha muestra un "Historial" unificado (Turnos + Ventas +
// Presupuestos) desde `GET /customers/{id}/timeline/`. El backend decide
// fuentes y orden; el frontend agrupa por día, pagina y enlaza.

vi.mock('next/navigation', () => ({ redirect: vi.fn(), useRouter: () => ({ push: vi.fn() }) }));
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

import { CustomerDetailClient } from '../[id]/customer-detail-client';

const TZ = 'America/Argentina/Buenos_Aires';

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

const SUMMARY = {
    total: 1,
    completed: 1,
    cancelled: 0,
    no_show: 0,
    upcoming: 0,
    next_appointment: null,
    last_appointment: null,
};

const APPOINTMENT_EVENT = {
    type: 'appointment',
    id: 'appointment:a-1',
    source_id: 'a-1',
    // 13:00Z = 10:00 en Buenos Aires, 02/10/2026.
    occurred_at: '2026-10-02T13:00:00Z',
    title: 'Corte de pelo',
    subtitle: 'Lucía QA',
    status: 'confirmed',
    status_display: 'Confirmado',
    amount: '15000.00',
    currency: null,
    href: '/app/turnos/turnos?date=2026-10-02&appointment=a-1',
    metadata: {
        type: 'appointment',
        id: 'a-1',
        occurred_at: '2026-10-02T13:00:00Z',
        start_at: '2026-10-02T13:00:00Z',
        end_at: '2026-10-02T13:30:00Z',
        status: 'confirmed',
        status_display: 'Confirmado',
        source: 'manual',
        service_name: 'Corte de pelo',
        service_price: '15000.00',
        professional_id: 'p-1',
        professional_name: 'Lucía QA',
        customer_name: 'Ana Cliente',
        payment_summary: null,
        created_at: '2026-09-30T12:00:00Z',
    },
};

const SALE_EVENT = {
    type: 'sale',
    id: 'sale:s-1',
    source_id: 's-1',
    // 02:30Z del 03/10 = 23:30 del 02/10 en Buenos Aires: mismo día local que el turno.
    occurred_at: '2026-10-03T02:30:00Z',
    title: 'Venta #12',
    subtitle: 'Tarjeta',
    status: 'completed',
    status_display: 'Completada',
    amount: '2500.00',
    currency: null,
    href: '/app/gestion/ventas/s-1',
    metadata: { number: 12, items_count: 3, payment_method: 'card', payment_method_display: 'Tarjeta', cancelled_at: null, invoice: null },
};

const QUOTE_EVENT = {
    type: 'quote',
    id: 'quote:q-1',
    source_id: 'q-1',
    occurred_at: '2026-09-28T15:00:00Z',
    title: 'Presupuesto P-000004',
    subtitle: null,
    status: 'accepted',
    status_display: 'Aceptado',
    amount: '9800.00',
    currency: 'ARS',
    href: '/app/gestion/ventas/presupuestos/q-1',
    metadata: { number: 'P-000004', items_count: 1, valid_until: null, sent_at: null },
};

const ORDER_EVENT = {
    type: 'order',
    id: 'order:o-1',
    source_id: 'o-1',
    // 18:00Z = 15:00 en Buenos Aires, 30/09/2026.
    occurred_at: '2026-09-30T18:00:00Z',
    title: 'Pedido O-000007',
    subtitle: null,
    status: 'in_preparation',
    status_display: 'En Preparación',
    amount: '42000.00',
    currency: null,
    href: '/app/gestion/ventas/pedidos/o-1',
    metadata: {
        number: 'O-000007',
        items_count: 2,
        order_date: '2026-09-30',
        estimated_delivery_date: null,
        payment_status: 'partial',
        payment_status_display: 'Parcial',
        total_paid: '10000.00',
        pending_balance: '32000.00',
    },
};

function timeline(results: unknown[], types: string[], count = results.length) {
    return { data: { count, next: null, previous: null, results, types }, isLoading: false, isError: false };
}

function renderDetail(
    props: { summary?: boolean; canViewSales?: boolean; canViewQuotes?: boolean; canViewOrders?: boolean } = {},
) {
    hooks.useCustomer.mockReturnValue({
        data: props.summary ? { ...CUSTOMER, appointments_summary: SUMMARY } : CUSTOMER,
        isLoading: false,
    });
    return render(
        <CustomerDetailClient
            customerId="c-1"
            canManage={false}
            canViewSales={props.canViewSales ?? false}
            canViewQuotes={props.canViewQuotes ?? false}
            canViewOrders={props.canViewOrders ?? false}
            businessTimeZone={TZ}
        />,
    );
}

function rows() {
    return within(screen.getByRole('region', { name: 'Historial' })).getAllByTestId('customer-timeline-event');
}

beforeEach(() => {
    vi.clearAllMocks();
    hooks.useCustomerAppointments.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false });
    hooks.useUpdateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useCreateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    // CUSTOMER 04C: la ficha siempre monta "Notas internas".
    hooks.useCustomerNotes.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false, isError: false });
    hooks.useCreateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useDeleteCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

describe('Timeline unificada en la ficha (CUSTOMER 04A)', () => {
    it('renderiza un Turno: tipo, hora local, servicio, profesional, estado, precio y link a la agenda', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([APPOINTMENT_EVENT], ['appointment']));
        renderDetail({ summary: true });

        const [row] = rows();
        expect(row).toHaveAttribute('data-type', 'appointment');
        expect(within(row).getByText('Turno')).toBeInTheDocument();
        expect(within(row).getByText('10:00')).toBeInTheDocument();
        expect(within(row).getByText('Corte de pelo')).toBeInTheDocument();
        expect(within(row).getByText('Lucía QA')).toBeInTheDocument();
        expect(within(row).getByText('Confirmado')).toBeInTheDocument();
        expect(within(row).getByText('$ 15.000')).toBeInTheDocument();
        expect(within(row).getByRole('link', { name: 'Ver en agenda' })).toHaveAttribute(
            'href',
            '/app/turnos/turnos?date=2026-10-02&appointment=a-1',
        );
    });

    it('renderiza una Venta con número, medio de pago, ítems, estado, total y link', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([SALE_EVENT], ['sale', 'quote']));
        renderDetail({ canViewSales: true, canViewQuotes: true });

        const [row] = rows();
        expect(within(row).getByText('Venta')).toBeInTheDocument();
        expect(within(row).getByText('Venta #12')).toBeInTheDocument();
        expect(within(row).getByText('Tarjeta · 3 ítems')).toBeInTheDocument();
        expect(within(row).getByText('Completada')).toBeInTheDocument();
        expect(within(row).getByText('$ 2.500')).toBeInTheDocument();
        expect(within(row).getByRole('link', { name: 'Ver venta' })).toHaveAttribute('href', '/app/gestion/ventas/s-1');
    });

    it('renderiza un Presupuesto con estado, total y link', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([QUOTE_EVENT], ['sale', 'quote']));
        renderDetail({ canViewSales: true, canViewQuotes: true });

        const [row] = rows();
        expect(within(row).getByText('Presupuesto')).toBeInTheDocument();
        expect(within(row).getByText('Presupuesto P-000004')).toBeInTheDocument();
        expect(within(row).getByText('1 ítem')).toBeInTheDocument();
        expect(within(row).getByText('Aceptado')).toBeInTheDocument();
        expect(within(row).getByText('$ 9.800')).toBeInTheDocument();
        expect(within(row).getByRole('link', { name: 'Ver presupuesto' })).toHaveAttribute(
            'href',
            '/app/gestion/ventas/presupuestos/q-1',
        );
    });

    it('timeline mezclada: respeta el orden del backend y agrupa por día en la zona del Business', () => {
        hooks.useCustomerTimeline.mockReturnValue(
            timeline([SALE_EVENT, APPOINTMENT_EVENT, QUOTE_EVENT], ['appointment', 'sale', 'quote']),
        );
        renderDetail({ summary: true, canViewSales: true, canViewQuotes: true });

        expect(rows().map((row) => row.getAttribute('data-type'))).toEqual(['sale', 'appointment', 'quote']);
        const oct2 = screen.getByRole('region', { name: '02 OCT 2026' });
        expect(within(oct2).getAllByTestId('customer-timeline-event')).toHaveLength(2);
        const sep28 = screen.getByRole('region', { name: '28 SEP 2026' });
        expect(within(sep28).getAllByTestId('customer-timeline-event')).toHaveLength(1);
        expect(within(oct2).getByText('23:30')).toBeInTheDocument();
    });

    it('turno futuro cancelado: se agrupa por la fecha de cancelación y aclara para cuándo era', () => {
        const cancelled = {
            ...APPOINTMENT_EVENT,
            // Cancelado el 02/10 13:40Z (10:40 local); el turno era el 20/10 14:15Z (11:15 local).
            occurred_at: '2026-10-02T13:40:00Z',
            status: 'cancelled',
            status_display: 'Cancelado',
            metadata: { ...APPOINTMENT_EVENT.metadata, start_at: '2026-10-20T14:15:00Z', status: 'cancelled' },
        };
        hooks.useCustomerTimeline.mockReturnValue(timeline([cancelled, SALE_EVENT, QUOTE_EVENT], ['appointment', 'sale', 'quote']));
        renderDetail({ summary: true, canViewSales: true, canViewQuotes: true });

        expect(screen.queryByRole('region', { name: '20 OCT 2026' })).not.toBeInTheDocument();
        const oct2 = screen.getByRole('region', { name: '02 OCT 2026' });
        const [row] = within(oct2).getAllByTestId('customer-timeline-event');
        expect(within(row).getByText('10:40')).toBeInTheDocument();
        expect(within(row).getByText('Cancelado')).toBeInTheDocument();
        expect(within(row).getByText('Turno del mar 20 oct 2026 · 11:15')).toBeInTheDocument();
    });

    it('turno histórico normal (occurred_at = start_at) no repite la fecha', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([APPOINTMENT_EVENT], ['appointment']));
        renderDetail({ summary: true });

        expect(screen.queryByText(/^Turno del /)).not.toBeInTheDocument();
    });

    it('el monto solo aparece si el evento lo trae y el link solo si hay href', () => {
        hooks.useCustomerTimeline.mockReturnValue(
            timeline([{ ...APPOINTMENT_EVENT, amount: null, href: null }], ['appointment']),
        );
        renderDetail({ summary: true });

        const [row] = rows();
        expect(within(row).queryByText(/\$/)).not.toBeInTheDocument();
        expect(within(row).queryByRole('link')).not.toBeInTheDocument();
    });

    it('muestra estados cancelados de venta y turno', () => {
        hooks.useCustomerTimeline.mockReturnValue(
            timeline(
                [
                    { ...SALE_EVENT, status: 'cancelled', status_display: 'Cancelada' },
                    { ...APPOINTMENT_EVENT, status: 'cancelled', status_display: 'Cancelado' },
                ],
                ['appointment', 'sale'],
            ),
        );
        renderDetail({ summary: true, canViewSales: true });

        expect(screen.getByText('Cancelada')).toBeInTheDocument();
        expect(screen.getByText('Cancelado')).toBeInTheDocument();
    });

    it('empty state si no hay actividad', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([], ['appointment', 'sale', 'quote']));
        renderDetail({ summary: true, canViewSales: true, canViewQuotes: true });

        const section = screen.getByRole('region', { name: 'Historial' });
        expect(within(section).getByText('No hay actividad registrada para este cliente.')).toBeInTheDocument();
    });

    it('Turnos-only: sin filtros de módulos ausentes, solo eventos de Turnos', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([APPOINTMENT_EVENT], ['appointment']));
        renderDetail({ summary: true });

        expect(screen.queryByRole('group', { name: 'Filtrar historial' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Ventas' })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Pedidos' })).not.toBeInTheDocument();
        expect(rows()).toHaveLength(1);
        expect(screen.getByRole('region', { name: 'Resumen de Turnos' })).toBeInTheDocument();
    });

    it('Gestión-only: ventas y presupuestos, filtros por tipo y sin secciones de Turnos', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([SALE_EVENT, QUOTE_EVENT], ['sale', 'quote']));
        renderDetail({ canViewSales: true, canViewQuotes: true });

        expect(screen.queryByRole('region', { name: 'Resumen de Turnos' })).not.toBeInTheDocument();
        expect(screen.queryByRole('region', { name: 'Próximos turnos' })).not.toBeInTheDocument();
        expect(hooks.useCustomerAppointments).not.toHaveBeenCalled();

        const filters = screen.getByRole('group', { name: 'Filtrar historial' });
        expect(within(filters).getAllByRole('button').map((b) => b.textContent)).toEqual(['Todo', 'Ventas', 'Presupuestos']);
        fireEvent.click(within(filters).getByRole('button', { name: 'Presupuestos' }));
        expect(hooks.useCustomerTimeline).toHaveBeenLastCalledWith('c-1', { types: ['quote'], limit: 20, offset: 0 });
        // Los chips se mantienen aunque la respuesta filtrada traiga un solo tipo.
        expect(screen.getByRole('button', { name: 'Ventas' })).toBeInTheDocument();
    });

    it('pagina por offset', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([SALE_EVENT, QUOTE_EVENT], ['sale', 'quote'], 45));
        renderDetail({ canViewSales: true, canViewQuotes: true });

        expect(hooks.useCustomerTimeline).toHaveBeenCalledWith('c-1', { limit: 20, offset: 0 });
        expect(screen.getByText('1–2 de 45')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Más recientes' })).toBeDisabled();
        fireEvent.click(screen.getByRole('button', { name: 'Más antiguos' }));
        expect(hooks.useCustomerTimeline).toHaveBeenLastCalledWith('c-1', { limit: 20, offset: 20 });
    });

    it('403 (ninguna fuente visible) oculta la sección sin romper la ficha', () => {
        hooks.useCustomerTimeline.mockReturnValue({
            data: undefined,
            isLoading: false,
            isError: true,
            error: new ApiError('forbidden', 403),
        });
        renderDetail({ canViewSales: true });

        expect(screen.queryByRole('region', { name: 'Historial' })).not.toBeInTheDocument();
        expect(screen.getByRole('heading', { name: 'Ana Cliente' })).toBeInTheDocument();
    });

    it('sin ninguna fuente posible no renderiza la timeline; el resumen existente sigue igual', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([], []));
        renderDetail();

        expect(screen.queryByRole('region', { name: 'Historial' })).not.toBeInTheDocument();
        expect(screen.getByRole('heading', { name: 'Ana Cliente' })).toBeInTheDocument();
        expect(screen.getByText('11 5555-0001')).toBeInTheDocument();
    });

    it('no rompe el resumen de Turnos existente', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([APPOINTMENT_EVENT], ['appointment']));
        renderDetail({ summary: true });

        const summary = screen.getByRole('region', { name: 'Resumen de Turnos' });
        expect(within(summary).getByText('Completados', { selector: 'dt' }).nextElementSibling?.textContent).toBe('1');
        expect(within(summary).getByText('Sin turnos próximos.')).toBeInTheDocument();
    });
});

describe('Pedidos en la timeline (CUSTOMER 04B)', () => {
    it('renderiza un Pedido: tipo, número, ítems, estado, pago, monto, hora y link', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([ORDER_EVENT], ['sale', 'quote', 'order']));
        renderDetail({ canViewSales: true, canViewQuotes: true, canViewOrders: true });

        const [row] = rows();
        expect(row).toHaveAttribute('data-type', 'order');
        expect(within(row).getByText('Pedido')).toBeInTheDocument();
        expect(within(row).getByText('Pedido O-000007')).toBeInTheDocument();
        expect(within(row).getByText('2 ítems')).toBeInTheDocument();
        expect(within(row).getByText('En Preparación')).toBeInTheDocument();
        expect(within(row).getByText('Pago parcial')).toBeInTheDocument();
        expect(within(row).getByText('$ 42.000')).toBeInTheDocument();
        expect(within(row).getByText('15:00')).toBeInTheDocument();
        expect(within(row).getByRole('link', { name: 'Ver pedido' })).toHaveAttribute('href', '/app/gestion/ventas/pedidos/o-1');
        expect(screen.getByRole('region', { name: '30 SEP 2026' })).toBeInTheDocument();
    });

    it('pedido cancelado: muestra el estado y no el estado de pago', () => {
        hooks.useCustomerTimeline.mockReturnValue(
            timeline([{ ...ORDER_EVENT, status: 'cancelled', status_display: 'Cancelado' }], ['order']),
        );
        renderDetail({ canViewOrders: true });

        const [row] = rows();
        expect(within(row).getByText('Cancelado')).toBeInTheDocument();
        expect(within(row).queryByText(/^Pago /)).not.toBeInTheDocument();
    });

    it('timeline con los 4 tipos: respeta el orden del backend y agrupa por día', () => {
        hooks.useCustomerTimeline.mockReturnValue(
            timeline([SALE_EVENT, APPOINTMENT_EVENT, ORDER_EVENT, QUOTE_EVENT], ['appointment', 'sale', 'quote', 'order']),
        );
        renderDetail({ summary: true, canViewSales: true, canViewQuotes: true, canViewOrders: true });

        expect(rows().map((row) => row.getAttribute('data-type'))).toEqual(['sale', 'appointment', 'order', 'quote']);
        expect(within(screen.getByRole('region', { name: '02 OCT 2026' })).getAllByTestId('customer-timeline-event')).toHaveLength(2);
        expect(within(screen.getByRole('region', { name: '30 SEP 2026' })).getAllByTestId('customer-timeline-event')).toHaveLength(1);
        expect(within(screen.getByRole('region', { name: '28 SEP 2026' })).getAllByTestId('customer-timeline-event')).toHaveLength(1);

        const filters = screen.getByRole('group', { name: 'Filtrar historial' });
        expect(within(filters).getAllByRole('button').map((b) => b.textContent)).toEqual([
            'Todo',
            'Turnos',
            'Ventas',
            'Presupuestos',
            'Pedidos',
        ]);
    });

    it('filtro Pedidos pide solo `order` y conserva los chips', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([SALE_EVENT, ORDER_EVENT], ['sale', 'quote', 'order']));
        renderDetail({ canViewSales: true, canViewQuotes: true, canViewOrders: true });

        fireEvent.click(screen.getByRole('button', { name: 'Pedidos' }));
        expect(hooks.useCustomerTimeline).toHaveBeenLastCalledWith('c-1', { types: ['order'], limit: 20, offset: 0 });
        expect(screen.getByRole('button', { name: 'Pedidos' })).toHaveAttribute('aria-pressed', 'true');
        expect(screen.getByRole('button', { name: 'Ventas' })).toBeInTheDocument();
    });

    it('Gestión sin view_orders: sin chip Pedidos ni eventos de pedido, la ficha funciona', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([SALE_EVENT, QUOTE_EVENT], ['sale', 'quote']));
        renderDetail({ canViewSales: true, canViewQuotes: true, canViewOrders: false });

        expect(screen.queryByRole('button', { name: 'Pedidos' })).not.toBeInTheDocument();
        expect(rows().map((row) => row.getAttribute('data-type'))).toEqual(['sale', 'quote']);
        expect(screen.getByRole('heading', { name: 'Ana Cliente' })).toBeInTheDocument();
    });

    it('solo con Pedidos visibles la timeline se pide y se muestra', () => {
        hooks.useCustomerTimeline.mockReturnValue(timeline([ORDER_EVENT], ['order']));
        renderDetail({ canViewOrders: true });

        expect(rows()).toHaveLength(1);
        expect(screen.queryByRole('group', { name: 'Filtrar historial' })).not.toBeInTheDocument();
    });

    it('venta facturada muestra el número de factura (anulada lo aclara)', () => {
        hooks.useCustomerTimeline.mockReturnValue(
            timeline(
                [
                    {
                        ...SALE_EVENT,
                        metadata: {
                            ...SALE_EVENT.metadata,
                            invoice: { id: 'i-1', full_number: 'B-0001-00000007', status: 'issued', status_display: 'Emitida' },
                        },
                    },
                    {
                        ...SALE_EVENT,
                        id: 'sale:s-2',
                        source_id: 's-2',
                        metadata: {
                            ...SALE_EVENT.metadata,
                            invoice: { id: 'i-2', full_number: 'B-0001-00000008', status: 'voided', status_display: 'Anulada' },
                        },
                    },
                ],
                ['sale'],
            ),
        );
        renderDetail({ canViewSales: true });

        expect(screen.getByText('Tarjeta · 3 ítems · Factura B-0001-00000007')).toBeInTheDocument();
        expect(screen.getByText('Tarjeta · 3 ítems · Factura B-0001-00000008 (anulada)')).toBeInTheDocument();
    });
});

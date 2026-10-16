// CUSTOMER 07D.1: preferencias y consentimiento de contacto en la ficha.
// Lectura `view_customers`; edición `manage_customer_contact_preferences`
// (owner/admin/manager). Nada se envía: solo se registran preferencias.
process.env.TZ = 'America/Argentina/Buenos_Aires';

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AnchorHTMLAttributes, ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Customer, CustomerContactPreferences } from '@/features/customers/types';

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
    useRefreshCustomerAppointmentViews: vi.fn(),
    useCustomerReminders: vi.fn(),
    useCreateCustomerReminder: vi.fn(),
    useUpdateCustomerReminder: vi.fn(),
    useCustomerDeliveries: vi.fn(() => ({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false, isError: false })),
    useCustomerContactPreferences: vi.fn(),
    useUpdateCustomerContactPreferences: vi.fn(),
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

const ANA = {
    id: 'c-ana',
    name: 'Ana QA',
    phone: '11 5555-0001',
    email: 'ana@qa.test',
    doc_type: null,
    doc_number: null,
    type: 'individual',
    tags: [],
    is_active: true,
    created_at: '2026-09-01T12:00:00Z',
    updated_at: '2026-09-01T12:00:00Z',
} as unknown as Customer;

function prefs(overrides: Partial<CustomerContactPreferences> = {}): CustomerContactPreferences {
    return {
        customer_id: ANA.id,
        whatsapp_enabled: false,
        email_enabled: false,
        phone_enabled: true,
        preferred_channel: null,
        do_not_contact: false,
        whatsapp_consent_at: null,
        whatsapp_consent_source: null,
        email_consent_at: null,
        email_consent_source: null,
        updated_at: null,
        channels: {
            whatsapp: { usable: false, reason: 'disabled' },
            email: { usable: false, reason: 'disabled' },
            phone: { usable: true, reason: null },
        },
        ...overrides,
    };
}

const BASE = { view_customers: true, view_appointments: true };
const OWNER = { ...BASE, manage_customers: true, manage_customer_contact_preferences: true };
const MANAGER = { ...BASE, manage_customers: true, manage_customer_contact_preferences: true };
const VIEWER = { ...BASE };
// Gestión: cashier tiene `manage_customers` (POS) pero NO el permiso de preferencias.
const CASHIER = { ...BASE, manage_customers: true };

let currentCustomer: Customer = ANA;
let currentPrefs: CustomerContactPreferences = prefs();
const updatePrefs = vi.fn();

function session(permissions: Record<string, boolean>) {
    return {
        features: { appointments_core: true, customers: true, sales: false, quotes: false, orders: false },
        permissions,
        services: { enabled: ['appointments'] },
        current: { business: { id: 1, name: 'QA', status: 'active', timezone: 'America/Argentina/Buenos_Aires' }, role: 'owner', service: 'appointments' },
    } as any;
}

beforeEach(() => {
    vi.clearAllMocks();
    currentCustomer = ANA;
    currentPrefs = prefs();
    hooks.useCustomer.mockImplementation(() => ({ data: currentCustomer, isLoading: false }));
    hooks.useCustomers.mockReturnValue({ data: { count: 0, results: [] }, isLoading: false, isError: false, refetch: vi.fn() });
    hooks.useCustomerAppointments.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false });
    hooks.useCustomerTimeline.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [], types: [] }, isLoading: false, isError: false });
    hooks.useCreateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useCustomerNotes.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] }, isLoading: false, isError: false });
    hooks.useCreateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useDeleteCustomerNote.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useRefreshCustomerAppointmentViews.mockReturnValue(vi.fn());
    hooks.useCustomerReminders.mockReturnValue({
        data: { count: 0, next: null, previous: null, results: [], counts: { pending: 0, closed: 0 } },
        isLoading: false,
        isError: false,
    });
    hooks.useCreateCustomerReminder.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useUpdateCustomerReminder.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    hooks.useCustomerContactPreferences.mockImplementation(() => ({ data: currentPrefs, isLoading: false, isError: false }));
    hooks.useUpdateCustomerContactPreferences.mockReturnValue({ mutateAsync: updatePrefs, isPending: false });
    updatePrefs.mockResolvedValue(prefs());
});

async function renderPage(permissions: Record<string, boolean> = OWNER) {
    getSessionMock.mockResolvedValue(session(permissions));
    render(await CustomerDetailPage({ params: Promise.resolve({ id: currentCustomer.id }) }));
}

function section() {
    return screen.getByRole('region', { name: 'Preferencias de contacto' });
}

function openEditor() {
    fireEvent.click(within(section()).getByRole('button', { name: 'Editar preferencias' }));
    return screen.getByRole('dialog', { name: 'Preferencias de contacto' });
}

describe('CUSTOMER 07D.1 · Preferencias de contacto', () => {
    it('1-2. renderiza la sección con los defaults apagados', async () => {
        await renderPage();
        const region = section();
        expect(within(region).getByText('Estas preferencias se usarán para futuros recordatorios y comunicaciones automáticas.')).toBeInTheDocument();
        expect(within(within(region).getByTestId('contact-channel-whatsapp')).getByText('No permitido')).toBeInTheDocument();
        expect(within(within(region).getByTestId('contact-channel-email')).getByText('No permitido')).toBeInTheDocument();
        expect(within(within(region).getByTestId('contact-channel-phone')).getByText('Permitido')).toBeInTheDocument();
        expect(within(region).getByText('Sin canal preferido.')).toBeInTheDocument();
        expect(screen.queryByTestId('do-not-contact-banner')).not.toBeInTheDocument();
        expect(hooks.useCustomerContactPreferences).toHaveBeenCalledWith('c-ana');

        const dialog = openEditor();
        expect(within(dialog).getByLabelText('Permitido', { selector: '#contact-pref-whatsapp' })).not.toBeChecked();
        expect(within(dialog).getByLabelText('Permitido', { selector: '#contact-pref-email' })).not.toBeChecked();
        expect(within(dialog).getByLabelText('No contactar')).not.toBeChecked();
        expect(within(dialog).getByLabelText('Canal preferido')).toHaveValue('');
    });

    it('3-4. activar WhatsApp exige confirmar consentimiento y lo envía', async () => {
        await renderPage();
        const dialog = openEditor();
        fireEvent.click(within(dialog).getByLabelText('Permitido', { selector: '#contact-pref-whatsapp' }));
        const consent = within(dialog).getByLabelText(/Confirmo que el cliente autorizó este canal/);
        const save = within(dialog).getByRole('button', { name: 'Guardar preferencias' });
        expect(consent).not.toBeChecked();
        expect(save).toBeDisabled();

        fireEvent.click(consent);
        fireEvent.change(within(dialog).getByLabelText('¿Cómo se obtuvo la autorización?'), { target: { value: 'customer_request' } });
        expect(save).toBeEnabled();
        fireEvent.click(save);
        await waitFor(() => expect(updatePrefs).toHaveBeenCalledTimes(1));
        expect(updatePrefs).toHaveBeenCalledWith({
            whatsapp_enabled: true,
            email_enabled: false,
            phone_enabled: true,
            preferred_channel: null,
            do_not_contact: false,
            whatsapp_consent_confirmed: true,
            consent_source: 'customer_request',
        });
        await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    });

    it('5. activar email pide su propia confirmación', async () => {
        await renderPage();
        const dialog = openEditor();
        fireEvent.click(within(dialog).getByLabelText('Permitido', { selector: '#contact-pref-email' }));
        fireEvent.click(within(dialog).getByLabelText(/Confirmo que el cliente autorizó este canal/));
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar preferencias' }));
        await waitFor(() => expect(updatePrefs).toHaveBeenCalledTimes(1));
        expect(updatePrefs.mock.calls[0][0]).toMatchObject({ email_enabled: true, email_consent_confirmed: true, consent_source: 'manual' });
        expect(updatePrefs.mock.calls[0][0]).not.toHaveProperty('whatsapp_consent_confirmed');
    });

    it('07D.2 a11y: la confirmación de consentimiento tiene nombre accesible por canal', async () => {
        await renderPage();
        const dialog = openEditor();
        fireEvent.click(within(dialog).getByLabelText('Permitido', { selector: '#contact-pref-whatsapp' }));
        const consent = within(dialog).getByRole('checkbox', { name: 'Confirmo que el cliente autorizó este canal (WhatsApp)' });
        expect(consent).toHaveAttribute('id', 'contact-pref-whatsapp-consent');
        expect(within(dialog).queryByRole('checkbox', { name: 'on' })).not.toBeInTheDocument();
    });

    it('un canal ya permitido no vuelve a pedir consentimiento y muestra la fecha registrada', async () => {
        currentPrefs = prefs({
            whatsapp_enabled: true,
            whatsapp_consent_at: '2026-10-02T15:00:00-03:00',
            whatsapp_consent_source: 'customer_request',
            channels: { whatsapp: { usable: true, reason: null }, email: { usable: false, reason: 'disabled' }, phone: { usable: true, reason: null } },
        });
        await renderPage();
        expect(within(section()).getByText('Autorizado el 02 oct 2026 · pedido del cliente')).toBeInTheDocument();
        const dialog = openEditor();
        expect(within(dialog).queryByLabelText(/Confirmo que el cliente autorizó este canal/)).not.toBeInTheDocument();
        expect(within(dialog).getByRole('button', { name: 'Guardar preferencias' })).toBeEnabled();
    });

    it('canal apagado conserva el registro de autorización', async () => {
        currentPrefs = prefs({ whatsapp_consent_at: '2026-09-20T12:00:00-03:00', whatsapp_consent_source: 'manual' });
        await renderPage();
        expect(
            within(section()).getByText('Autorización registrada el 20 sep 2026 · registrado por el equipo (canal apagado)'),
        ).toBeInTheDocument();
    });

    it('6. do_not_contact: banner global, flags conservados y se envía', async () => {
        currentPrefs = prefs({
            whatsapp_enabled: true,
            whatsapp_consent_at: '2026-10-02T15:00:00-03:00',
            whatsapp_consent_source: 'manual',
            preferred_channel: 'whatsapp',
            do_not_contact: true,
            channels: {
                whatsapp: { usable: false, reason: 'do_not_contact' },
                email: { usable: false, reason: 'do_not_contact' },
                phone: { usable: false, reason: 'do_not_contact' },
            },
        });
        await renderPage();
        expect(screen.getByTestId('do-not-contact-banner')).toHaveTextContent('ningún canal automático se va a usar');
        expect(within(screen.getByTestId('contact-channel-whatsapp')).getByText('Permitido')).toBeInTheDocument();
        expect(within(screen.getByTestId('contact-channel-whatsapp')).getByText('Preferido')).toBeInTheDocument();
        expect(screen.getAllByText('No contactar').length).toBeGreaterThan(0); // badge del header

        const dialog = openEditor();
        const dnc = within(dialog).getByLabelText('No contactar');
        expect(dnc).toBeChecked();
        fireEvent.click(dnc);
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar preferencias' }));
        await waitFor(() => expect(updatePrefs).toHaveBeenCalledTimes(1));
        expect(updatePrefs.mock.calls[0][0]).toMatchObject({ do_not_contact: false, whatsapp_enabled: true, preferred_channel: 'whatsapp' });
    });

    it('7. canal preferido: solo canales permitidos y se limpia al apagar el canal', async () => {
        await renderPage();
        const dialog = openEditor();
        const preferred = within(dialog).getByLabelText('Canal preferido');
        expect(within(preferred).getByRole('option', { name: 'WhatsApp (no permitido)' })).toBeDisabled();
        expect(within(preferred).getByRole('option', { name: 'Llamada' })).toBeEnabled();

        fireEvent.click(within(dialog).getByLabelText('Permitido', { selector: '#contact-pref-whatsapp' }));
        fireEvent.click(within(dialog).getByLabelText(/Confirmo que el cliente autorizó este canal/));
        fireEvent.change(preferred, { target: { value: 'whatsapp' } });
        expect(preferred).toHaveValue('whatsapp');
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar preferencias' }));
        await waitFor(() => expect(updatePrefs).toHaveBeenCalledTimes(1));
        expect(updatePrefs.mock.calls[0][0]).toMatchObject({ preferred_channel: 'whatsapp', whatsapp_enabled: true });

        fireEvent.click(within(section()).getByRole('button', { name: 'Editar preferencias' }));
        const again = screen.getByRole('dialog', { name: 'Preferencias de contacto' });
        fireEvent.change(within(again).getByLabelText('Canal preferido'), { target: { value: 'phone' } });
        fireEvent.click(within(again).getByLabelText('Permitido', { selector: '#contact-pref-phone' }));
        expect(within(again).getByLabelText('Canal preferido')).toHaveValue('');
    });

    it('8. viewer: solo lectura', async () => {
        await renderPage(VIEWER);
        expect(section()).toBeInTheDocument();
        expect(within(section()).queryByRole('button', { name: 'Editar preferencias' })).not.toBeInTheDocument();
    });

    it('8b. cashier con manage_customers pero sin el permiso: solo lectura', async () => {
        await renderPage(CASHIER);
        expect(within(section()).queryByRole('button', { name: 'Editar preferencias' })).not.toBeInTheDocument();
    });

    it('9. manager con el permiso sí edita', async () => {
        await renderPage(MANAGER);
        const dialog = openEditor();
        fireEvent.click(within(dialog).getByLabelText('No contactar'));
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar preferencias' }));
        await waitFor(() => expect(updatePrefs).toHaveBeenCalledWith(expect.objectContaining({ do_not_contact: true })));
    });

    it('10. warning si falta teléfono/email (en la ficha y al activar)', async () => {
        currentCustomer = { ...ANA, phone: '', email: '' } as Customer;
        currentPrefs = prefs({
            email_enabled: true,
            email_consent_at: '2026-10-02T15:00:00-03:00',
            email_consent_source: 'manual',
            channels: {
                whatsapp: { usable: false, reason: 'disabled' },
                email: { usable: false, reason: 'missing_email' },
                phone: { usable: false, reason: 'missing_phone' },
            },
        });
        await renderPage();
        expect(within(screen.getByTestId('contact-channel-email')).getByText('Falta el email: no se puede usar.')).toBeInTheDocument();
        expect(within(screen.getByTestId('contact-channel-phone')).getByText('Falta el teléfono: no se puede usar.')).toBeInTheDocument();

        const dialog = openEditor();
        expect(within(dialog).getByText(/no tiene email cargado/)).toBeInTheDocument();
        // 07D.1.1: sin teléfono no hay destino que autorizar → WhatsApp no se puede encender.
        const whatsapp = within(dialog).getByLabelText('Permitido', { selector: '#contact-pref-whatsapp' });
        expect(whatsapp).toBeDisabled();
        expect(whatsapp).not.toBeChecked();
        expect(within(dialog).queryByLabelText(/Confirmo que el cliente autorizó/)).not.toBeInTheDocument();
        expect(within(dialog).getAllByText(/no tiene teléfono cargado/).length).toBe(2); // WhatsApp + Llamadas
    });

    it('11. do_not_contact: advertencia antes de una acción manual (sin bloquearla)', async () => {
        currentPrefs = prefs({
            do_not_contact: true,
            channels: {
                whatsapp: { usable: false, reason: 'do_not_contact' },
                email: { usable: false, reason: 'do_not_contact' },
                phone: { usable: false, reason: 'do_not_contact' },
            },
        });
        await renderPage();
        const toolbar = screen.getByRole('toolbar', { name: 'Acciones del cliente' });
        fireEvent.click(within(toolbar).getByRole('link', { name: 'Llamar' }));
        const warning = screen.getByRole('dialog', { name: 'Este cliente pidió no ser contactado' });
        const proceed = within(warning).getByRole('link', { name: 'Contactar igual (Llamar)' });
        expect(proceed).toHaveAttribute('href', expect.stringMatching(/^tel:/));
        fireEvent.click(within(warning).getByRole('button', { name: 'Cancelar' }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

        fireEvent.click(within(toolbar).getByRole('link', { name: 'WhatsApp' }));
        const wa = within(screen.getByRole('dialog', { name: 'Este cliente pidió no ser contactado' })).getByRole('link', {
            name: 'Contactar igual (WhatsApp)',
        });
        expect(wa).toHaveAttribute('href', expect.stringContaining('wa.me'));
        expect(wa).toHaveAttribute('target', '_blank');
    });

    it('sin do_not_contact las acciones manuales no muestran advertencia', async () => {
        await renderPage();
        const toolbar = screen.getByRole('toolbar', { name: 'Acciones del cliente' });
        fireEvent.click(within(toolbar).getByRole('link', { name: 'Email' }));
        expect(screen.queryByRole('dialog', { name: 'Este cliente pidió no ser contactado' })).not.toBeInTheDocument();
    });

    it('12. mobile: filas apiladas y controles con target táctil de 44px', async () => {
        await renderPage();
        expect(screen.getByTestId('contact-channel-whatsapp').className).toMatch(/flex-col/);
        const dialog = openEditor();
        for (const id of ['#contact-pref-whatsapp', '#contact-pref-email', '#contact-pref-phone']) {
            expect(within(dialog).getByLabelText('Permitido', { selector: id }).closest('label')?.className).toMatch(/min-h-11/);
        }
        expect(within(dialog).getByLabelText('No contactar').closest('label')?.className).toMatch(/min-h-11/);
    });
});

// CUSTOMER 07D.1.1: el consentimiento queda ligado al destino autorizado. La
// regla vive en el backend (`channels[].reason`); la UI solo la muestra.
describe('CUSTOMER 07D.1.1 · Consentimiento ligado al destino', () => {
    const AUTHORIZED = {
        whatsapp_enabled: true,
        whatsapp_consent_at: '2026-10-02T15:00:00-03:00',
        whatsapp_consent_source: 'manual' as const,
        email_enabled: true,
        email_consent_at: '2026-10-02T15:00:00-03:00',
        email_consent_source: 'manual' as const,
    };
    const USABLE = {
        whatsapp: { usable: true, reason: null },
        email: { usable: true, reason: null },
        phone: { usable: true, reason: null },
    };

    function withReason(channel: 'whatsapp' | 'email', reason: 'consent_destination_changed' | 'consent_missing') {
        return prefs({ ...AUTHORIZED, channels: { ...USABLE, [channel]: { usable: false, reason } } });
    }

    it('1. canal autorizado y usable: sin avisos ni renovación', async () => {
        currentPrefs = prefs({ ...AUTHORIZED, channels: USABLE });
        await renderPage();
        for (const channel of ['whatsapp', 'email']) {
            const row = screen.getByTestId(`contact-channel-${channel}`);
            expect(within(row).getByText('Listo para avisos automáticos.')).toBeInTheDocument();
            expect(within(row).queryByRole('button', { name: 'Renovar autorización' })).not.toBeInTheDocument();
        }
    });

    it('2. teléfono cambiado: aviso y "Renovar autorización"', async () => {
        currentPrefs = withReason('whatsapp', 'consent_destination_changed');
        await renderPage();
        const row = screen.getByTestId('contact-channel-whatsapp');
        expect(
            within(row).getByText(
                'El teléfono cambió desde la última autorización. Volvé a confirmar el consentimiento para usar WhatsApp automáticamente.',
            ),
        ).toBeInTheDocument();
        expect(within(row).queryByText('Listo para avisos automáticos.')).not.toBeInTheDocument();
        expect(within(row).getByRole('button', { name: 'Renovar autorización' })).toBeInTheDocument();
        expect(within(row).getByText('Permitido')).toBeInTheDocument(); // la preferencia histórica se mantiene
        expect(within(screen.getByTestId('contact-channel-email')).queryByRole('button', { name: 'Renovar autorización' })).not.toBeInTheDocument();
    });

    it('3. email cambiado: aviso propio', async () => {
        currentPrefs = withReason('email', 'consent_destination_changed');
        await renderPage();
        expect(
            within(screen.getByTestId('contact-channel-email')).getByText(
                'El email cambió desde la última autorización. Volvé a confirmar el consentimiento para usar Email automáticamente.',
            ),
        ).toBeInTheDocument();
    });

    it('consentimiento previo sin destino registrado también pide renovar', async () => {
        currentPrefs = withReason('whatsapp', 'consent_missing');
        await renderPage();
        const row = screen.getByTestId('contact-channel-whatsapp');
        expect(within(row).getByText(/No hay un destino autorizado registrado/)).toBeInTheDocument();
        expect(within(row).getByRole('button', { name: 'Renovar autorización' })).toBeInTheDocument();
    });

    it('4-5. renovar: confirma contra el destino actual y el aviso desaparece', async () => {
        currentPrefs = withReason('whatsapp', 'consent_destination_changed');
        updatePrefs.mockImplementation(async () => {
            currentPrefs = prefs({ ...AUTHORIZED, channels: USABLE });
            return currentPrefs;
        });
        await renderPage();
        fireEvent.click(within(screen.getByTestId('contact-channel-whatsapp')).getByRole('button', { name: 'Renovar autorización' }));
        const dialog = screen.getByRole('dialog', { name: 'Preferencias de contacto' });
        const consent = within(dialog).getByLabelText(/Confirmo que el cliente autorizó este canal/);
        expect(consent).not.toBeChecked(); // nunca se renueva solo
        expect(within(dialog).getByText('Destino: 11 5555-0001')).toBeInTheDocument();
        expect(within(dialog).getByText(/El teléfono cambió desde la última autorización/)).toBeInTheDocument();

        // Renovar es opcional: guardar sin confirmar no manda la confirmación.
        const save = within(dialog).getByRole('button', { name: 'Guardar preferencias' });
        expect(save).toBeEnabled();

        fireEvent.click(consent);
        fireEvent.change(within(dialog).getByLabelText('¿Cómo se obtuvo la autorización?'), { target: { value: 'customer_request' } });
        fireEvent.click(save);
        await waitFor(() => expect(updatePrefs).toHaveBeenCalledTimes(1));
        expect(updatePrefs.mock.calls[0][0]).toMatchObject({
            whatsapp_enabled: true,
            whatsapp_consent_confirmed: true,
            consent_source: 'customer_request',
        });
        expect(updatePrefs.mock.calls[0][0]).not.toHaveProperty('email_consent_confirmed');
        await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
        const row = screen.getByTestId('contact-channel-whatsapp');
        expect(within(row).queryByText(/El teléfono cambió/)).not.toBeInTheDocument();
        expect(within(row).queryByRole('button', { name: 'Renovar autorización' })).not.toBeInTheDocument();
        expect(within(row).getByText('Listo para avisos automáticos.')).toBeInTheDocument();
    });

    it('guardar otros cambios sin renovar no manda confirmación', async () => {
        currentPrefs = withReason('email', 'consent_destination_changed');
        await renderPage();
        const dialog = openEditor();
        fireEvent.click(within(dialog).getByLabelText('No contactar'));
        fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar preferencias' }));
        await waitFor(() => expect(updatePrefs).toHaveBeenCalledTimes(1));
        expect(updatePrefs.mock.calls[0][0]).not.toHaveProperty('email_consent_confirmed');
        expect(updatePrefs.mock.calls[0][0]).not.toHaveProperty('consent_source');
    });

    it('viewer ve el aviso pero no puede renovar', async () => {
        currentPrefs = withReason('whatsapp', 'consent_destination_changed');
        await renderPage(VIEWER);
        const row = screen.getByTestId('contact-channel-whatsapp');
        expect(within(row).getByText(/El teléfono cambió/)).toBeInTheDocument();
        expect(within(row).queryByRole('button', { name: 'Renovar autorización' })).not.toBeInTheDocument();
    });

    it('6. do_not_contact mantiene la prioridad visual', async () => {
        currentPrefs = prefs({
            ...AUTHORIZED,
            do_not_contact: true,
            channels: {
                whatsapp: { usable: false, reason: 'do_not_contact' },
                email: { usable: false, reason: 'do_not_contact' },
                phone: { usable: false, reason: 'do_not_contact' },
            },
        });
        await renderPage();
        expect(screen.getByTestId('do-not-contact-banner')).toBeInTheDocument();
        expect(screen.queryByText(/cambió desde la última autorización/)).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Renovar autorización' })).not.toBeInTheDocument();
    });

    it('7. las acciones manuales siguen disponibles con el destino cambiado', async () => {
        currentPrefs = withReason('whatsapp', 'consent_destination_changed');
        await renderPage();
        const toolbar = screen.getByRole('toolbar', { name: 'Acciones del cliente' });
        const whatsapp = within(toolbar).getByRole('link', { name: 'WhatsApp' });
        expect(whatsapp).toHaveAttribute('href', expect.stringContaining('wa.me'));
        fireEvent.click(whatsapp);
        expect(screen.queryByRole('dialog', { name: 'Este cliente pidió no ser contactado' })).not.toBeInTheDocument();
        expect(within(toolbar).getByRole('link', { name: 'Llamar' })).toBeInTheDocument();
        expect(within(toolbar).getByRole('link', { name: 'Email' })).toBeInTheDocument();
    });

    it('8. mobile: "Renovar autorización" con target táctil de 44px', async () => {
        currentPrefs = withReason('whatsapp', 'consent_destination_changed');
        await renderPage();
        const button = within(screen.getByTestId('contact-channel-whatsapp')).getByRole('button', { name: 'Renovar autorización' });
        expect(button.className).toMatch(/min-h-11/);
    });
});

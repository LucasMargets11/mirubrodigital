import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const pushMock = vi.fn();
const replaceMock = vi.fn();
const clipboardWriteTextMock = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
}));

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={typeof href === 'string' ? href : href?.pathname} {...props}>{children}</a>
  ),
}));

vi.mock('@/lib/admin/client', () => ({
  getAdminClientProvisioningOptions: vi.fn(),
  provisionAdminClient: vi.fn(),
}));

import { getAdminClientProvisioningOptions, provisionAdminClient } from '@/lib/admin/client';

const getOptionsMock = vi.mocked(getAdminClientProvisioningOptions);
const provisionMock = vi.mocked(provisionAdminClient);

const OPTIONS_FIXTURE = {
  services: [
    {
      value: 'gestion',
      label: 'Gestión Comercial',
      plans: [
        { code: 'gestion_pro', name: 'Gestión Pro' },
        { code: 'gestion_start', name: 'Gestión Starter' },
      ],
    },
    {
      value: 'menu_qr',
      label: 'Menú QR',
      plans: [{ code: 'menu_qr_basico', name: 'Menú QR Básico' }],
    },
  ],
};

const SUCCESS_RESULT = {
  owner_email: 'propietario@empresa.com',
  owner_user_id: 123,
  business_id: 456,
  membership_id: 789,
  login_url: 'https://frontend.example.com/entrar/cliente',
  business: { id: 55, name: 'Comercio Ejemplo', slug: 'comercio-ejemplo', status: 'trialing', service_type: 'gestion', country: 'AR', currency: 'ARS' },
  owner: { id: 1, email: 'legacy-owner@empresa.com', created: true },
  membership: { id: 2, role: 'owner', status: 'active' },
  subscription: { id: 'uuid-value', plan_code: 'gestion_pro', provider: 'manual', status: 'trialing', current_period_start: null, current_period_end: null },
};

async function renderForm() {
  const { NuevoClienteForm } = await import('../nuevo-cliente-form');
  render(<NuevoClienteForm />);
}

async function fillRequiredFields() {
  fireEvent.change(screen.getByLabelText('Nombre del negocio'), { target: { value: 'Comercio Ejemplo' } });
  fireEvent.change(screen.getByLabelText('Slug'), { target: { value: 'comercio-ejemplo' } });
  fireEvent.change(screen.getByLabelText('Email del owner'), { target: { value: 'owner@empresa.com' } });
  fireEvent.change(screen.getByLabelText('Servicio'), { target: { value: 'gestion' } });
  await waitFor(() => expect(screen.getByLabelText('Plan')).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText('Plan'), { target: { value: 'gestion_pro' } });
  fireEvent.change(screen.getByLabelText('Inicio de la bonificación'), { target: { value: '2026-08-14' } });
  fireEvent.change(screen.getByLabelText('Fin de la bonificación'), { target: { value: '2027-02-14' } });
  fireEvent.change(screen.getByLabelText('Motivo de la bonificación'), { target: { value: 'Cortesía comercial' } });
}

describe('NuevoClienteForm', () => {
  beforeEach(() => {
    getOptionsMock.mockReset();
    provisionMock.mockReset();
    pushMock.mockReset();
    replaceMock.mockReset();
    clipboardWriteTextMock.mockReset();
    clipboardWriteTextMock.mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: clipboardWriteTextMock },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows a loading state while provisioning options are being fetched', async () => {
    getOptionsMock.mockReturnValue(new Promise(() => {})); // never resolves
    await renderForm();
    expect(screen.getByText(/cargando servicios y planes/i)).toBeInTheDocument();
  });

  it('shows a recoverable error with a retry button when options fail to load', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'error', message: 'boom' });
    await renderForm();

    expect(await screen.findByText(/no pudimos cargar los servicios y planes/i)).toBeInTheDocument();

    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    fireEvent.click(screen.getByRole('button', { name: /reintentar/i }));

    await waitFor(() => expect(screen.getByLabelText('Servicio')).toBeInTheDocument());
    expect(getOptionsMock).toHaveBeenCalledTimes(2);
  });

  it('renders services and plans exclusively from the backend response', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();

    const serviceSelect = await screen.findByLabelText('Servicio');
    expect(within(serviceSelect).getByText('Gestión Comercial')).toBeInTheDocument();
    expect(within(serviceSelect).getByText('Menú QR')).toBeInTheDocument();
    expect(within(serviceSelect).queryByText(/restaurante/i)).not.toBeInTheDocument();
  });

  it('does not offer Restaurante as a service when the API never returns it', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    const serviceSelect = await screen.findByLabelText('Servicio');
    fireEvent.change(serviceSelect, { target: { value: 'gestion' } });
    const planSelect = screen.getByLabelText('Plan');
    expect(within(planSelect).queryByText(/restaurante/i)).not.toBeInTheDocument();
  });

  it('keeps the plan select disabled until a service is chosen', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await screen.findByLabelText('Servicio');
    expect(screen.getByLabelText('Plan')).toBeDisabled();
  });

  it('resets an incompatible plan when the service changes', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    const serviceSelect = await screen.findByLabelText('Servicio');

    fireEvent.change(serviceSelect, { target: { value: 'gestion' } });
    const planSelect = screen.getByLabelText('Plan') as HTMLSelectElement;
    fireEvent.change(planSelect, { target: { value: 'gestion_pro' } });
    expect(planSelect.value).toBe('gestion_pro');

    fireEvent.change(serviceSelect, { target: { value: 'menu_qr' } });
    expect(planSelect.value).toBe('');
  });

  it('renders exactly the ten allowed form fields and nothing else sensitive', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await screen.findByLabelText('Servicio');

    for (const label of [
      'Nombre del negocio', 'Slug', 'Email del owner', 'Servicio', 'Plan',
      'País', 'Moneda', 'Inicio de la bonificación', 'Fin de la bonificación',
      'Motivo de la bonificación',
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
  });

  it('never renders a password field', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await screen.findByLabelText('Servicio');
    expect(document.querySelector('input[type="password"]')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/contraseñ/i)).not.toBeInTheDocument();
  });

  it('never renders Google or Mercado Pago fields, and never claims Google is linked', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await screen.findByLabelText('Servicio');
    expect(screen.queryByLabelText(/google/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/mercado ?pago/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/no env[ií]a credenciales ni vincula todav[íi]a una cuenta de google/i),
    ).toBeInTheDocument();
  });

  it('country and currency start at AR and ARS', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await screen.findByLabelText('Servicio');
    expect((screen.getByLabelText('País') as HTMLInputElement).value).toBe('AR');
    expect((screen.getByLabelText('Moneda') as HTMLInputElement).value).toBe('ARS');
  });

  it('blocks submit on an invalid email', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await fillRequiredFields();
    fireEvent.change(screen.getByLabelText('Email del owner'), { target: { value: 'not-an-email' } });

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByText(/ingres[áa] un email v[áa]lido/i)).toBeInTheDocument();
    expect(provisionMock).not.toHaveBeenCalled();
  });

  it('blocks submit on a blank grant_reason', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await fillRequiredFields();
    fireEvent.change(screen.getByLabelText('Motivo de la bonificación'), { target: { value: '   ' } });

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByText(/ingres[áa] el motivo/i)).toBeInTheDocument();
    expect(provisionMock).not.toHaveBeenCalled();
  });

  it('blocks submit when the end date is not after the start date', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await fillRequiredFields();
    fireEvent.change(screen.getByLabelText('Inicio de la bonificación'), { target: { value: '2026-08-14' } });
    fireEvent.change(screen.getByLabelText('Fin de la bonificación'), { target: { value: '2026-08-14' } });

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByText(/debe ser posterior a la fecha de inicio/i)).toBeInTheDocument();
    expect(provisionMock).not.toHaveBeenCalled();
  });

  it('the "6 meses" quick-pick computes six calendar months from the start date', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await screen.findByLabelText('Servicio');
    fireEvent.change(screen.getByLabelText('Inicio de la bonificación'), { target: { value: '2026-01-15' } });

    fireEvent.click(screen.getByRole('button', { name: '6 meses' }));

    expect((screen.getByLabelText('Fin de la bonificación') as HTMLInputElement).value).toBe('2026-07-15');
  });

  it('the "1 año" quick-pick computes twelve calendar months and handles a leap-year Feb 29 start', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await screen.findByLabelText('Servicio');
    fireEvent.change(screen.getByLabelText('Inicio de la bonificación'), { target: { value: '2024-02-29' } });

    fireEvent.click(screen.getByRole('button', { name: '1 año' }));

    expect((screen.getByLabelText('Fin de la bonificación') as HTMLInputElement).value).toBe('2025-02-28');
  });

  it('submits successfully, preserves the payload, and replaces the form without automatic navigation', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({ status: 'ok', data: SUCCESS_RESULT });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    await waitFor(() => expect(provisionMock).toHaveBeenCalledTimes(1));
    const payload = provisionMock.mock.calls[0][0];
    expect(payload.complimentary_start).toBe('2026-08-14');
    expect(payload.complimentary_end).toBe('2027-02-14');
    expect(Object.keys(payload).sort()).toEqual([
      'business_name', 'business_slug', 'complimentary_end', 'complimentary_start',
      'country', 'currency', 'grant_reason', 'owner_email', 'plan_code', 'service_type',
    ].sort());

    expect(await screen.findByRole('heading', { name: 'Cliente creado correctamente' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Nombre del negocio')).not.toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('shows the real business and top-level owner email with the Google access guidance', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({ status: 'ok', data: SUCCESS_RESULT });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByText('Comercio Ejemplo')).toBeInTheDocument();
    expect(screen.getByText('propietario@empresa.com')).toBeInTheDocument();
    expect(screen.queryByText('legacy-owner@empresa.com')).not.toBeInTheDocument();
    expect(
      screen.getByText('El propietario debe ingresar con esta misma cuenta de Google'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('No se generó una contraseña ni se envió un email automáticamente'),
    ).toBeInTheDocument();

    const googleLink = screen.getByRole('link', { name: 'Ingresar con Google' });
    expect(googleLink).toHaveAttribute('href', SUCCESS_RESULT.login_url);
    expect(googleLink).toHaveAttribute('target', '_blank');
    expect(googleLink).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('a double click only fires a single provisioning request', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    let resolveProvision: (value: unknown) => void = () => {};
    provisionMock.mockReturnValue(new Promise((resolve) => { resolveProvision = resolve; }));
    await renderForm();
    await fillRequiredFields();

    const submitButton = screen.getByRole('button', { name: /crear cliente/i });
    fireEvent.click(submitButton);
    fireEvent.click(submitButton);
    fireEvent.click(submitButton);

    resolveProvision({ status: 'ok', data: SUCCESS_RESULT });
    await screen.findByRole('heading', { name: 'Cliente creado correctamente' });

    expect(provisionMock).toHaveBeenCalledTimes(1);
    expect(pushMock).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('copies only the owner email and backend login_url and reports success', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({ status: 'ok', data: SUCCESS_RESULT });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Copiar instrucciones' }));

    await waitFor(() => expect(clipboardWriteTextMock).toHaveBeenCalledTimes(1));
    const copiedText = clipboardWriteTextMock.mock.calls[0][0];
    expect(copiedText).toContain('propietario@empresa.com');
    expect(copiedText).toContain(SUCCESS_RESULT.login_url);
    expect(copiedText).not.toContain(String(SUCCESS_RESULT.owner_user_id));
    expect(copiedText).not.toContain(String(SUCCESS_RESULT.business_id));
    expect(copiedText).not.toContain(String(SUCCESS_RESULT.membership_id));
    expect(copiedText).not.toContain(SUCCESS_RESULT.subscription.id);
    expect(copiedText).not.toMatch(/token|contraseña/i);
    expect(await screen.findByRole('status')).toHaveTextContent('Instrucciones copiadas correctamente.');
  });

  it('controls a clipboard failure without removing or breaking the confirmation', async () => {
    clipboardWriteTextMock.mockRejectedValueOnce(new Error('clipboard unavailable'));
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({ status: 'ok', data: SUCCESS_RESULT });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));
    fireEvent.click(await screen.findByRole('button', { name: 'Copiar instrucciones' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'No se pudieron copiar las instrucciones. Intentá nuevamente.',
    );
    expect(screen.getByRole('heading', { name: 'Cliente creado correctamente' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ingresar con Google' })).toBeInTheDocument();
  });

  it('navigates to the client only on request and uses the top-level business_id', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({ status: 'ok', data: SUCCESS_RESULT });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));
    const viewClientButton = await screen.findByRole('button', { name: 'Ver cliente' });

    expect(pushMock).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
    fireEvent.click(viewClientButton);
    expect(pushMock).toHaveBeenCalledWith('/admin/clientes/456');
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it('shows a submitting state on the button while the request is in flight', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockReturnValue(new Promise(() => {})); // never resolves
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByRole('button', { name: /creando/i })).toBeDisabled();
  });

  it('shows a 400 field error on the matching control (business_name)', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({
      status: 'field_errors',
      httpStatus: 400,
      fieldErrors: { business_name: 'Este campo es requerido.' },
    });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByText('Este campo es requerido.')).toBeInTheDocument();
    expect((screen.getByLabelText('Nombre del negocio') as HTMLInputElement).value).toBe('Comercio Ejemplo');
    expect(screen.getByRole('button', { name: /crear cliente/i })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Cliente creado correctamente' })).not.toBeInTheDocument();
  });

  it('shows a 409 business_slug_conflict error on the slug field', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({
      status: 'domain_error',
      httpStatus: 409,
      error: { code: 'business_slug_conflict', detail: 'El slug ya está utilizado.', field: 'business_slug' },
    });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByText('El slug ya está utilizado.')).toBeInTheDocument();
  });

  it('shows an owner conflict (ambiguous_owner_email) on the email field', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({
      status: 'domain_error',
      httpStatus: 409,
      error: { code: 'ambiguous_owner_email', detail: 'Existen múltiples cuentas con ese email.', field: 'owner_email' },
    });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByText('Existen múltiples cuentas con ese email.')).toBeInTheDocument();
  });

  it('shows a 422 domain error as a general (non-field) error banner', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({
      status: 'domain_error',
      httpStatus: 422,
      error: { code: 'complimentary_grant_failed', detail: 'No se pudo otorgar el acceso bonificado.', field: null },
    });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo otorgar el acceso bonificado.');
  });

  it('handles a 401 using the existing expired-session redirect', async () => {
    const assignMock = vi.fn();
    Object.defineProperty(window, 'location', { value: { assign: assignMock }, writable: true });

    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({ status: 'session_expired' });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    await waitFor(() => expect(assignMock).toHaveBeenCalledWith('/admin/login'));
  });

  it('shows the canonical access-denied treatment on a 403 and stops the form', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({ status: 'forbidden' });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByText(/no ten[ée]s permisos para provisionar clientes/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /crear cliente/i })).not.toBeInTheDocument();
  });

  it('shows a generic safe message on a 500 without leaking internal details', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({ status: 'server_error', httpStatus: 500 });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));

    expect(await screen.findByText(/ocurri[óo] un error inesperado/i)).toBeInTheDocument();
  });

  it('keeps loaded values after a server error', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    provisionMock.mockResolvedValueOnce({ status: 'server_error', httpStatus: 500 });
    await renderForm();
    await fillRequiredFields();

    fireEvent.click(screen.getByRole('button', { name: /crear cliente/i }));
    await screen.findByText(/ocurri[óo] un error inesperado/i);

    expect((screen.getByLabelText('Nombre del negocio') as HTMLInputElement).value).toBe('Comercio Ejemplo');
    expect((screen.getByLabelText('Slug') as HTMLInputElement).value).toBe('comercio-ejemplo');
  });

  it('Cancelar links back to /admin/clientes without submitting', async () => {
    getOptionsMock.mockResolvedValueOnce({ status: 'ok', data: OPTIONS_FIXTURE });
    await renderForm();
    await screen.findByLabelText('Servicio');

    const cancelLink = screen.getByRole('link', { name: /cancelar/i });
    expect(cancelLink).toHaveAttribute('href', '/admin/clientes');
    expect(provisionMock).not.toHaveBeenCalled();
  });
});

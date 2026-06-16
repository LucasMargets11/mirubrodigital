import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Mocks ──────────────────────────────────────────────────────────────────

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

// Mock lucide-react icons to simple spans to avoid SVG rendering issues.
vi.mock('lucide-react', () => ({
  Star: () => <span data-testid="icon-star" />,
  Globe: () => <span data-testid="icon-globe" />,
  Building2: () => <span data-testid="icon-building2" />,
  AlertTriangle: () => <span data-testid="icon-alert" />,
  ExternalLink: () => <span data-testid="icon-external" />,
}));

// ── Fixtures ───────────────────────────────────────────────────────────────

const BASE_CONFIG = {
  business_id: 42,
  business_name: 'McDonaldas Test',
  business_slug: 'mcd-test',
  public_url: 'https://www.mirubro.com/r/mcd-test/',
  service_type: 'qr_reviews',
  review_config_exists: true,
  enabled: true,
  mode: 'direct',
  redirect_threshold: 4,
  google_place_id: 'ChIJOriginal',
  google_place_name: 'McDonaldas',
  google_place_formatted_address: 'Av. Corrientes 1234, CABA',
  google_review_url: 'https://search.google.com/local/writereview?placeid=ChIJOriginal',
  custom_redirect_url: '',
  google_place_updated_at: '2026-04-15T12:00:00Z',
};

function buildFetchOk(body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: () => Promise.resolve(body),
  });
}

function buildFetchError(detail: string, status = 400) {
  return vi.fn().mockResolvedValue({
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: () => Promise.resolve({ detail }),
  });
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('QRResenasCard', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetAllMocks();
  });

  it('shows loading state initially', async () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {}))); // never resolves
    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);
    expect(screen.getByText(/cargando/i)).toBeInTheDocument();
  });

  it('renders slug and live URL preview after load', async () => {
    vi.stubGlobal('fetch', buildFetchOk(BASE_CONFIG));
    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('mcd-test')).toBeInTheDocument();
    });
    // Preview URL
    expect(screen.getByText('https://www.mirubro.com/r/mcd-test/')).toBeInTheDocument();
  });

  it('renders Google Place ID after load', async () => {
    vi.stubGlobal('fetch', buildFetchOk(BASE_CONFIG));
    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => {
      expect(screen.getByDisplayValue('ChIJOriginal')).toBeInTheDocument();
    });
  });

  it('updates live slug preview as the user types', async () => {
    vi.stubGlobal('fetch', buildFetchOk(BASE_CONFIG));
    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => screen.getByDisplayValue('mcd-test'));

    const input = screen.getByDisplayValue('mcd-test');
    fireEvent.change(input, { target: { value: 'mcdonalds' } });

    await waitFor(() => {
      expect(screen.getByText('https://www.mirubro.com/r/mcdonalds/')).toBeInTheDocument();
    });
  });

  it('shows inline error for slug with spaces without calling PATCH', async () => {
    vi.stubGlobal('fetch', buildFetchOk(BASE_CONFIG));
    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => screen.getByDisplayValue('mcd-test'));

    const input = screen.getByDisplayValue('mcd-test');
    fireEvent.change(input, { target: { value: 'my slug' } });

    const saveBtn = screen.getByRole('button', { name: /guardar slug/i });
    fireEvent.click(saveBtn);

    expect(screen.getByText(/espacios/i)).toBeInTheDocument();
    // Only the initial GET was called — no PATCH.
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });

  it('shows inline error for slug with apostrophe', async () => {
    vi.stubGlobal('fetch', buildFetchOk(BASE_CONFIG));
    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => screen.getByDisplayValue('mcd-test'));

    fireEvent.change(screen.getByDisplayValue('mcd-test'), { target: { value: "mc'donalds" } });
    fireEvent.click(screen.getByRole('button', { name: /guardar slug/i }));

    expect(screen.getByText(/apóstrofe/i)).toBeInTheDocument();
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
  });

  it('shows inline error for slug with uppercase', async () => {
    vi.stubGlobal('fetch', buildFetchOk(BASE_CONFIG));
    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => screen.getByDisplayValue('mcd-test'));

    fireEvent.change(screen.getByDisplayValue('mcd-test'), { target: { value: 'McDONALDs' } });
    fireEvent.click(screen.getByRole('button', { name: /guardar slug/i }));

    // Uppercase fails the regex check.
    expect(screen.getByText(/minúsculas/i)).toBeInTheDocument();
  });

  it('calls PATCH and shows ✓ Guardado on valid slug save', async () => {
    const updatedConfig = { ...BASE_CONFIG, business_slug: 'mcdonalds', public_url: 'https://www.mirubro.com/r/mcdonalds/' };
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => 'application/json' }, json: () => Promise.resolve(BASE_CONFIG) })
      .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => 'application/json' }, json: () => Promise.resolve(updatedConfig) });
    vi.stubGlobal('fetch', mockFetch);

    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => screen.getByDisplayValue('mcd-test'));

    fireEvent.change(screen.getByDisplayValue('mcd-test'), { target: { value: 'mcdonalds' } });
    fireEvent.click(screen.getByRole('button', { name: /guardar slug/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /guardado/i })).toBeInTheDocument();
    });
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2);
  });

  it('shows server error when PATCH returns duplicate slug error', async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => 'application/json' }, json: () => Promise.resolve(BASE_CONFIG) })
      .mockResolvedValueOnce({ ok: false, status: 400, headers: { get: () => 'application/json' }, json: () => Promise.resolve({ detail: 'El slug "mcdonalds" ya está en uso por otro negocio.' }) });
    vi.stubGlobal('fetch', mockFetch);

    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => screen.getByDisplayValue('mcd-test'));

    fireEvent.change(screen.getByDisplayValue('mcd-test'), { target: { value: 'mcdonalds' } });
    fireEvent.click(screen.getByRole('button', { name: /guardar slug/i }));

    await waitFor(() => {
      expect(screen.getByText(/ya está en uso/i)).toBeInTheDocument();
    });
  });

  it('calls PATCH and shows ✓ Guardado on Google Place save', async () => {
    const updatedConfig = { ...BASE_CONFIG, google_place_id: 'ChIJNewPlace' };
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => 'application/json' }, json: () => Promise.resolve(BASE_CONFIG) })
      .mockResolvedValueOnce({ ok: true, status: 200, headers: { get: () => 'application/json' }, json: () => Promise.resolve(updatedConfig) });
    vi.stubGlobal('fetch', mockFetch);

    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => screen.getByDisplayValue('ChIJOriginal'));

    fireEvent.change(screen.getByDisplayValue('ChIJOriginal'), { target: { value: 'ChIJNewPlace' } });
    fireEvent.click(screen.getByRole('button', { name: /guardar configuración/i }));

    await waitFor(() => {
      // At least one button shows saved state
      expect(screen.getAllByText(/guardado/i).length).toBeGreaterThan(0);
    });
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2);
  });

  it('shows error state when initial load fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')));
    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => {
      expect(screen.getByText(/no se pudo cargar/i)).toBeInTheDocument();
    });
  });

  it('shows warning about URL change', async () => {
    vi.stubGlobal('fetch', buildFetchOk(BASE_CONFIG));
    const { QRResenasCard } = await import('@/components/admin/qr-reviews-card');
    render(<QRResenasCard businessId={42} />);

    await waitFor(() => screen.getByDisplayValue('mcd-test'));
    expect(screen.getByText(/modifica la URL pública/i)).toBeInTheDocument();
  });
});

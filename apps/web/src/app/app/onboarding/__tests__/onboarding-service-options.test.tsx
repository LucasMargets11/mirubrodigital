import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';

import OnboardingServicioPage from '../servicio/page';
import { buildBundlesPath, resolveSelectedProduct } from '../plan/page';

const getBillingProductsMock = vi.fn();

vi.mock('next/navigation', () => ({
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock('@/features/billing/api', () => ({
  getBillingProducts: () => getBillingProductsMock(),
}));

describe('onboarding catalog-driven flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders products from billing endpoint and hides Restaurante when not returned', async () => {
    getBillingProductsMock.mockResolvedValue([
      {
        code: 'gestion',
        vertical: 'commercial',
        name: 'Gestión Comercial',
        description: 'Ventas, stock y caja',
        is_active: true,
        order: 1,
      },
      {
        code: 'menu_qr',
        vertical: 'menu_qr',
        name: 'Menú QR',
        description: 'Carta digital',
        is_active: true,
        order: 2,
      },
      {
        code: 'qr_reviews',
        vertical: 'qr_reviews',
        name: 'QR de Reseñas',
        description: 'Feedback y reputación',
        is_active: true,
        order: 3,
      },
    ]);

    render(<OnboardingServicioPage />);

    expect(await screen.findByText('QR de Reseñas')).toBeInTheDocument();
    expect(screen.queryByText('Restaurante')).not.toBeInTheDocument();
  });

  it('persists service_type=qr_reviews when QR de Reseñas is selected', async () => {
    getBillingProductsMock.mockResolvedValue([
      {
        code: 'gestion',
        vertical: 'commercial',
        name: 'Gestión Comercial',
        description: 'Ventas, stock y caja',
        is_active: true,
        order: 1,
      },
      {
        code: 'qr_reviews',
        vertical: 'qr_reviews',
        name: 'QR de Reseñas',
        description: 'Feedback y reputación',
        is_active: true,
        order: 2,
      },
    ]);

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<OnboardingServicioPage />);

    const qrReviewsOption = (await screen.findByDisplayValue('qr_reviews')) as HTMLInputElement;
    fireEvent.click(qrReviewsOption);
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const [, requestInit] = fetchMock.mock.calls[0];
    const body = JSON.parse(String((requestInit as RequestInit).body));
    expect(body).toEqual({ service_type: 'qr_reviews' });
  });

  it('resolves qr_reviews product and uses vertical=qr_reviews for bundles query path', () => {
    const product = resolveSelectedProduct('qr_reviews', [
      {
        code: 'gestion',
        vertical: 'commercial',
        name: 'Gestión Comercial',
        description: '',
        is_active: true,
        order: 1,
      },
      {
        code: 'qr_reviews',
        vertical: 'qr_reviews',
        name: 'QR de Reseñas',
        description: '',
        is_active: true,
        order: 2,
      },
    ]);

    expect(product?.vertical).toBe('qr_reviews');
    expect(buildBundlesPath('qr_reviews')).toBe('/api/v1/billing/bundles/?vertical=qr_reviews');
  });

  it('keeps onboarding files free of hardcoded pricing literals', () => {
    const servicioPath = path.join(process.cwd(), 'src/app/app/onboarding/servicio/page.tsx');
    const planPath = path.join(process.cwd(), 'src/app/app/onboarding/plan/page.tsx');

    const servicioSource = readFileSync(servicioPath, 'utf8');
    const planSource = readFileSync(planPath, 'utf8');

    const pricingLiteralRegex = /\b(18000|20000|25000|28000|30000|36000|40000|50000|55000|75000)\b/;

    expect(servicioSource).not.toMatch(pricingLiteralRegex);
    expect(planSource).not.toMatch(pricingLiteralRegex);
  });
});

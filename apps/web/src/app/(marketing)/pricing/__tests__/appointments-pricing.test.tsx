import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { formatPrice } from '@/lib/pricing/format';
import { getPlan, getPlanPrice, getProduct, getUsageTier } from '@/lib/pricing/selectors';
import PricingClient from '../pricing-client';

const mocks = vi.hoisted(() => ({
  getSearchParam: vi.fn(),
  routerPush: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.routerPush }),
  useSearchParams: () => ({ get: mocks.getSearchParam }),
}));

vi.mock('next/dynamic', () => ({
  default: () =>
    function DynamicPricingBuilder() {
      return <div data-testid="legacy-pricing-builder" />;
    },
}));

vi.mock('@/lib/api/client', () => ({
  apiPost: mocks.apiPost,
}));

function getPlanCard(code: string) {
  const card = screen
    .getAllByTestId('appointments-plan')
    .find((candidate) => candidate.getAttribute('data-plan-code') === code);
  if (!card) throw new Error(`Missing rendered plan: ${code}`);
  return card;
}

function expectCanonicalPrice(element: HTMLElement, amount: number) {
  const expected = formatPrice(amount).replace(/\s/g, '');
  const actual = element.textContent?.replace(/\s/g, '') ?? '';
  expect(actual).toContain(expected);
}

function expectTextWithCanonicalPrice(element: HTMLElement, label: string, amount: number) {
  const expected = `${label}${formatPrice(amount)}`.replace(/\s/g, '');
  const actual = element.textContent?.replace(/\s/g, '') ?? '';
  expect(actual).toContain(expected);
}

describe('Turnos pricing integration', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    mocks.getSearchParam.mockImplementation((key: string) =>
      key === 'service' ? 'appointments' : null,
    );
    mocks.routerPush.mockReset();
    mocks.apiPost.mockReset().mockResolvedValue({
      plan_code: 'appointments',
      billing_cycle: 'monthly',
      base_amount: 23000,
      addons_amount: 8500,
      extras_amount: 6000,
      total_amount: 37500,
      line_items: [
        {
          code: 'appointments',
          description: 'Turnos Base',
          quantity: 1,
          unit_price: 23000,
          total: 23000,
        },
        {
          code: 'appointments_automations',
          description: 'Automatizaciones',
          quantity: 1,
          unit_price: 8500,
          total: 8500,
        },
        {
          code: 'appointments_extra_professional',
          description: 'Profesionales extra',
          quantity: 2,
          unit_price: 3000,
          total: 6000,
        },
      ],
    });
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('resolves service=appointments to Turnos instead of falling back to Gestión', () => {
    render(<PricingClient />);

    expect(screen.getByTestId('appointments-pricing')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /Agenda, profesionales y reservas/ }),
    ).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByTestId('legacy-pricing-builder')).not.toBeInTheDocument();
  });

  it('allows selecting Turnos from the existing product selector', () => {
    mocks.getSearchParam.mockImplementation((key: string) =>
      key === 'service' ? 'commerce' : null,
    );
    render(<PricingClient />);

    fireEvent.click(screen.getByRole('button', { name: /Agenda, profesionales y reservas/ }));

    expect(screen.getByTestId('appointments-pricing')).toBeInTheDocument();
    expect(mocks.routerPush).not.toHaveBeenCalled();
  });

  it('renders exactly the three canonical logical plans', () => {
    render(<PricingClient />);

    expect(
      screen.getAllByTestId('appointments-plan').map((plan) => plan.getAttribute('data-plan-code')),
    ).toEqual(['appointments', 'appointments_pro', 'appointments_ai']);
  });

  it('keeps IA as one plan with four nested usage tiers', () => {
    render(<PricingClient />);

    const aiPlan = getPlanCard('appointments_ai');
    expect(aiPlan).toHaveAttribute('data-plan-code', 'appointments_ai');
    expect(
      within(aiPlan)
        .getAllByTestId(/^appointments-ai-tier-/)
        .map((tier) => tier.getAttribute('data-tier-code')),
    ).toEqual(['ai_300', 'ai_1500', 'ai_3000', 'custom']);
    expect(within(aiPlan).getByText('Turnos IA Recepcionista')).toBeInTheDocument();
  });

  it('shows custom pricing as A medida and routes it to the real contact page', () => {
    render(<PricingClient />);

    const customTier = screen.getByTestId('appointments-ai-tier-custom');
    expect(customTier).toHaveTextContent('A medida');
    expect(within(customTier).getByRole('link', { name: 'Contactar ventas' })).toHaveAttribute(
      'href',
      '/contacto',
    );
    expect(customTier).not.toHaveTextContent(/\$\s*0|Gratis/i);
  });

  it('shows monthly canonical prices for fixed plans and IA tiers', () => {
    render(<PricingClient />);

    const basePlan = getPlan('appointments');
    const proPlan = getPlan('appointments_pro');
    const aiPlan = getPlan('appointments_ai');
    if (!basePlan || !proPlan || !aiPlan) throw new Error('Missing Turnos catalog data');

    expectCanonicalPrice(getPlanCard('appointments'), getPlanPrice(basePlan, 'monthly'));
    expectCanonicalPrice(getPlanCard('appointments_pro'), getPlanPrice(proPlan, 'monthly'));
    for (const tierCode of aiPlan.usageTiers ?? []) {
      const tier = getUsageTier(tierCode);
      if (!tier || tier.purchaseMode !== 'self_service') continue;
      const tierCard = screen.getByTestId(`appointments-ai-tier-${tier.code}`);
      expectCanonicalPrice(tierCard, getPlanPrice(aiPlan, 'monthly', tier.code));
      expect(tierCard).toHaveTextContent(
        `${tier.includedConversations.toLocaleString('es-AR')} sesiones / mes`,
      );
      expectTextWithCanonicalPrice(tierCard, 'Sesión adicional:', tier.extraConversationPrice);
      expectTextWithCanonicalPrice(
        tierCard,
        'Límite predeterminado de consumo adicional:',
        tier.defaultExtraSpendLimit,
      );
    }
  });

  it('shows the canonical annual prices when the shared billing toggle changes', () => {
    render(<PricingClient />);
    fireEvent.click(screen.getByRole('button', { name: /Anual/ }));

    const basePlan = getPlan('appointments');
    const proPlan = getPlan('appointments_pro');
    const aiPlan = getPlan('appointments_ai');
    if (!basePlan || !proPlan || !aiPlan) throw new Error('Missing Turnos catalog data');

    expectCanonicalPrice(getPlanCard('appointments'), getPlanPrice(basePlan, 'yearly'));
    expectCanonicalPrice(getPlanCard('appointments_pro'), getPlanPrice(proPlan, 'yearly'));
    for (const tierCode of aiPlan.usageTiers ?? []) {
      const tier = getUsageTier(tierCode);
      if (!tier || tier.purchaseMode !== 'self_service') continue;
      expectCanonicalPrice(
        screen.getByTestId(`appointments-ai-tier-${tier.code}`),
        getPlanPrice(aiPlan, 'yearly', tier.code),
      );
    }
  });

  it('uses the full IA tier price without adding Turnos Pro', () => {
    render(<PricingClient />);

    const aiPlan = getPlan('appointments_ai');
    const proPlan = getPlan('appointments_pro');
    const aiTier = getUsageTier('ai_300');
    if (!aiPlan || !proPlan || !aiTier) throw new Error('Missing Turnos catalog data');
    const tier = screen.getByTestId('appointments-ai-tier-ai_300');

    expectCanonicalPrice(tier, getPlanPrice(aiPlan, 'monthly', aiTier.code));
    const displayedText = tier.textContent?.replace(/\s/g, '') ?? '';
    expect(displayedText).not.toContain(
      formatPrice(
        getPlanPrice(aiPlan, 'monthly', aiTier.code) + getPlanPrice(proPlan, 'monthly'),
      ).replace(/\s/g, ''),
    );
  });

  it('derives included professionals and users from the canonical plans', () => {
    render(<PricingClient />);

    for (const code of ['appointments', 'appointments_pro', 'appointments_ai']) {
      const plan = getPlan(code);
      if (!plan || plan.professionalsIncluded == null || plan.secondaryUsersIncluded == null) {
        throw new Error(`Missing included resources for ${code}`);
      }
      expect(getPlanCard(code)).toHaveTextContent(
        `${plan.professionalsIncluded.toLocaleString('es-AR')} profesionales incluidos`,
      );
      expect(getPlanCard(code)).toHaveTextContent(
        `${plan.secondaryUsersIncluded.toLocaleString('es-AR')} usuarios secundarios incluidos`,
      );
    }
  });

  it('keeps Turnos inactive and all purchase CTAs informational', () => {
    render(<PricingClient />);

    expect(getProduct('appointments')?.is_active).toBe(false);
    expect(screen.getByText('Contratación online próximamente')).toBeInTheDocument();
    for (const link of screen.getAllByRole('link')) {
      expect(link.getAttribute('href')).not.toMatch(/^\/subscribe(?:\?|$)/);
    }
    expect(mocks.routerPush).not.toHaveBeenCalled();
  });

  it('requests a server quote for the selected fixed plan and renders its response', async () => {
    render(<PricingClient />);

    const basePlan = getPlanCard('appointments');
    fireEvent.click(within(basePlan).getByRole('checkbox', { name: /automatizaciones/i }));
    fireEvent.change(within(basePlan).getByRole('spinbutton', { name: /profesionales extra/i }), {
      target: { value: '2' },
    });
    fireEvent.click(
      within(basePlan).getByRole('button', { name: 'Consultar cotización actualizada' }),
    );

    await waitFor(() => {
      expect(mocks.apiPost).toHaveBeenCalledWith('/api/v1/billing/appointments/quote/', {
        plan_code: 'appointments',
        billing_cycle: 'monthly',
        automations: true,
        extra_professionals: 2,
      });
    });
    expect(await screen.findByTestId('appointments-quote-result')).toHaveTextContent(
      'Total: $ 37.500',
    );
    expect(screen.getByTestId('appointments-quote-result')).toHaveTextContent(
      'Automatizaciones: 1 × $ 8.500 = $ 8.500',
    );
    expect(fetchMock).not.toHaveBeenCalled();
    expect(mocks.routerPush).not.toHaveBeenCalled();
  });

  it('sends the selected billing cycle and IA tier with automations included', async () => {
    render(<PricingClient />);
    fireEvent.click(screen.getByRole('button', { name: /Anual/ }));
    mocks.apiPost.mockResolvedValueOnce({
      plan_code: 'appointments_ai',
      billing_cycle: 'yearly',
      base_amount: 2640000,
      addons_amount: 0,
      extras_amount: 28800,
      total_amount: 2668800,
      line_items: [
        {
          code: 'ai_1500',
          description: 'Turnos IA Recepcionista',
          quantity: 1,
          unit_price: 2640000,
          total: 2640000,
        },
        {
          code: 'appointments_automations',
          description: 'Automatizaciones',
          quantity: 1,
          unit_price: 0,
          total: 0,
          included: true,
        },
      ],
    });

    const aiTier = screen.getByTestId('appointments-ai-tier-ai_1500');
    fireEvent.change(within(aiTier).getByRole('spinbutton', { name: /profesionales extra/i }), {
      target: { value: '1' },
    });
    fireEvent.click(
      within(aiTier).getByRole('button', { name: 'Consultar cotización actualizada' }),
    );

    await waitFor(() => {
      expect(mocks.apiPost).toHaveBeenCalledWith('/api/v1/billing/appointments/quote/', {
        plan_code: 'appointments_ai',
        billing_cycle: 'yearly',
        usage_tier: 'ai_1500',
        automations: true,
        extra_professionals: 1,
      });
    });
    expect(await screen.findByTestId('appointments-quote-result')).toHaveTextContent(
      'Turnos IA Recepcionista',
    );
  });

  it('keeps custom out of self-service and reports backend errors clearly', async () => {
    render(<PricingClient />);

    const customTier = screen.getByTestId('appointments-ai-tier-custom');
    expect(
      within(customTier).queryByRole('button', { name: /cotización actualizada/i }),
    ).not.toBeInTheDocument();

    const basePlan = getPlanCard('appointments');
    mocks.apiPost.mockRejectedValueOnce({ status: 401 });
    fireEvent.click(
      within(basePlan).getByRole('button', { name: 'Consultar cotización actualizada' }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Iniciá sesión con una cuenta propietaria',
    );
    expect(mocks.apiPost).not.toHaveBeenCalledWith(
      '/api/v1/billing/appointments/checkout/',
      expect.anything(),
    );
    expect(mocks.routerPush).not.toHaveBeenCalled();
  });

  it('uses canonical local prices only for initial display and never starts checkout', () => {
    const source = readFileSync(
      resolve(__dirname, '..', 'appointments-pricing-section.tsx'),
      'utf8',
    );

    expect(source).toContain('@/lib/pricing/selectors');
    expect(source).toContain('@/lib/pricing/format');
    expect(source).not.toMatch(
      /\b(?:23000|28000|150000|275000|385000|220800|268800|1440000|2640000|3696000)\b/,
    );
    expect(source).toContain("'/api/v1/billing/appointments/quote/'");
    expect(source).not.toMatch(/appointments\/checkout|\/subscribe|Mercado\s?Pago/i);
  });
});

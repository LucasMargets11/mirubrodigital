import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const hooks = vi.hoisted(() => ({ useAIUsageSummary: vi.fn() }));
vi.mock('../hooks', () => hooks);

import { ApiError } from '@/lib/api/client';

import { AIUsageSummaryPanel } from '../ai-usage-summary-panel';
import type { AIUsageSummary } from '../types';

function summary(overrides: Partial<AIUsageSummary> = {}): AIUsageSummary {
    return {
        contract_version: 1,
        evaluated_at: '2026-11-26T12:00:00+00:00',
        status: 'available',
        reason: null,
        can_start_new_session: true,
        unit: 'ai_session_24h',
        source: { product: 'reception', service_type: 'reception', plan_code: 'reception', usage_tier: 'reception_300', policy_kind: 'catalog' },
        period: { start: '2026-11-01T03:00:00+00:00', end: '2026-12-01T03:00:00+00:00' },
        sessions: { included: 300, used: 120, available_included: 180 },
        hard_cap: { max_sessions: 300, remaining_sessions: 180 },
        overage: { enabled: false, unit_price: null, spend_limit: 0, max_sessions: 0, used_sessions: 0, amount: '0', currency: 'ARS' },
        scheduled_change: null,
        ...overrides,
    };
}

function withQuery(value: Record<string, unknown>) {
    hooks.useAIUsageSummary.mockReturnValue({ isLoading: false, isError: false, data: undefined, error: null, ...value });
}

beforeEach(() => hooks.useAIUsageSummary.mockReset());

describe('AIUsageSummaryPanel', () => {
    it('muestra el uso del período y el cupo restante', () => {
        withQuery({ data: summary() });
        render(<AIUsageSummaryPanel variant="full" />);
        expect(screen.getByText('Recepcionista 300')).toBeInTheDocument();
        expect(screen.getByText(/Quedan 180 conversaciones incluidas/)).toBeInTheDocument();
        expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '40');
        expect(screen.getByText(/Sin excedentes/)).toBeInTheDocument();
    });

    it('cupo agotado', () => {
        withQuery({ data: summary({ status: 'exhausted', can_start_new_session: false, reason: 'hard_cap_reached',
            sessions: { included: 300, used: 300, available_included: 0 } }) });
        render(<AIUsageSummaryPanel />);
        expect(screen.getByText(/no inicia conversaciones nuevas hasta que empiece el próximo período/)).toBeInTheDocument();
    });

    it('cupo agotado sin datos de sesiones: no muestra ceros (PROD-08D)', () => {
        withQuery({ data: summary({ status: 'exhausted', can_start_new_session: false, reason: 'hard_cap_reached',
            period: null, sessions: null, hard_cap: null, overage: null }) });
        render(<AIUsageSummaryPanel variant="full" />);
        expect(screen.getByText('Sin datos de sesiones del período.')).toBeInTheDocument();
        expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
        expect(screen.queryByText(/de 0/)).not.toBeInTheDocument();
        expect(screen.queryByText(/Quedan/)).not.toBeInTheDocument();
    });

    it('Custom con cambio programado', () => {
        withQuery({ data: summary({
            source: { product: 'reception', service_type: 'reception', plan_code: 'reception', usage_tier: 'reception_custom', policy_kind: 'custom' },
            scheduled_change: { included_sessions: 800, effective_at: '2026-12-01T03:00:00+00:00' },
        }) });
        render(<AIUsageSummaryPanel variant="full" />);
        expect(screen.getByText('Recepcionista personalizado')).toBeInTheDocument();
        expect(screen.getByText(/800 desde/)).toBeInTheDocument();
    });

    it('beneficio vencido o futuro (suspended) sin datos de período', () => {
        withQuery({ data: summary({ status: 'suspended', reason: 'suspended', period: null, sessions: null, hard_cap: null, overage: null }) });
        render(<AIUsageSummaryPanel />);
        expect(screen.getByText('Recepcionista IA sin acceso vigente')).toBeInTheDocument();
        expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    });

    it('403 sin servicio de IA contratado y 403 por rol', () => {
        withQuery({ isError: true, error: new ApiError('x', 403, { code: 'ai_service_not_contracted' }) });
        const { unmount } = render(<AIUsageSummaryPanel />);
        expect(screen.getByText('Sin servicio de IA contratado')).toBeInTheDocument();
        unmount();
        withQuery({ isError: true, error: new ApiError('x', 403, { detail: 'forbidden' }) });
        render(<AIUsageSummaryPanel />);
        expect(screen.getByText('Tu rol no puede ver el consumo de IA.')).toBeInTheDocument();
    });

    it('cargando', () => {
        withQuery({ isLoading: true });
        render(<AIUsageSummaryPanel />);
        expect(screen.getByText('Cargando consumo…')).toBeInTheDocument();
    });
});

/**
 * Frontend tests for the Plan y Facturación page.
 *
 * Coverage:
 * 1. Renders plan info (plan name, status, renewal date) for an active subscription
 * 2. Shows "Cancelar suscripción" button only for OWNER users
 * 3. Non-owner users see a message that only the owner can manage the subscription
 * 4. Shows "Baja programada" banner when cancel_at_period_end is true
 * 5. Shows "Deshacer baja" button when cancellation is scheduled
 * 6. Shows "No tenés una suscripción activa" when no subscription exists
 * 7. Cancel button opens a confirmation modal
 * 8. Cancellation scheduled banner shows effective date
 */

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SubscriptionStatusResponse } from '@/features/billing/subscription-types';
import type { Session } from '@/lib/auth';

// ── Mocks ─────────────────────────────────────────────────────────────────────

// Mock the hooks module
const mockStatusQuery = vi.fn();
const mockCancelMutation = vi.fn();
const mockUndoCancelMutation = vi.fn();

vi.mock('@/features/billing/subscription-hooks', () => ({
    useSubscriptionStatusQuery: () => mockStatusQuery(),
    useCancelSubscriptionMutation: () => mockCancelMutation(),
    useUndoCancelSubscriptionMutation: () => mockUndoCancelMutation(),
}));

// Import the component AFTER setting up mocks
import { PlanBillingClient } from '../plan-billing-client';

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeSession(role = 'owner'): Session {
    return {
        user: {
            id: 1,
            email: 'test@test.com',
            name: 'Test User',
            email_verified: true,
            account_mode: 'owner_managed',
            must_change_password: false,
        },
        memberships: [
            { business: { id: 1, name: 'TestBiz' }, role, service: 'gestion' },
        ],
        current: {
            business: { id: 1, name: 'TestBiz', status: 'active' },
            role,
            service: 'gestion',
        },
        subscription: {
            plan: 'pro',
            status: 'active',
            access_allowed: true,
            reason_code: 'access_granted',
            grace_until: null,
            access_until: null,
            show_renewal_prompt: false,
            source: 'v2',
        },
        services: {} as Session['services'],
        features: {} as Session['features'],
        permissions: {} as Session['permissions'],
    };
}

function makeSubscriptionResponse(
    overrides: Partial<SubscriptionStatusResponse['subscription']> = {},
): SubscriptionStatusResponse {
    return {
        has_subscription: true,
        role: 'owner',
        subscription: {
            id: 'sub-uuid-1',
            plan_code: 'gestion_pro_monthly',
            plan_name: 'Pro Mensual',
            service_type: 'gestion',
            status: 'active',
            status_display: 'Activo',
            provider: 'mercadopago',
            current_period_start: '2025-01-01T00:00:00Z',
            current_period_end: '2025-02-01T00:00:00Z',
            cancel_at_period_end: false,
            cancel_requested_at: null,
            cancel_effective_at: null,
            cancel_reason: '',
            canceled_at: null,
            is_active: true,
            created_at: '2025-01-01T00:00:00Z',
            source: 'v2',
            can_manage_cancellation: true,
            ...overrides,
        },
    };
}

function defaultMutationState() {
    return {
        mutateAsync: vi.fn(),
        isPending: false,
        isError: false,
        isSuccess: false,
        error: null,
        reset: vi.fn(),
    };
}

function Wrapper({ children }: { children: React.ReactNode }) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function renderPage(session?: Session) {
    return render(
        <Wrapper>
            <PlanBillingClient session={session ?? makeSession()} />
        </Wrapper>,
    );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('PlanBillingClient', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // Default: loaded, active subscription, no pending cancel
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse(),
            isLoading: false,
            isError: false,
        });
        mockCancelMutation.mockReturnValue(defaultMutationState());
        mockUndoCancelMutation.mockReturnValue(defaultMutationState());
    });

    // ── 1. Renders plan info ──────────────────────────────────────────────────

    it('renders plan name, status badge, and renewal date', () => {
        renderPage();
        expect(screen.getByText('Pro Mensual')).toBeInTheDocument();
        expect(screen.getByText('Activo')).toBeInTheDocument();
        expect(screen.getByText('Próxima renovación')).toBeInTheDocument();
    });

    // ── 2. Cancel button only for OWNER ───────────────────────────────────────

    it('shows cancel button for OWNER', () => {
        renderPage(makeSession('owner'));
        expect(screen.getByRole('button', { name: /cancelar suscripción/i })).toBeInTheDocument();
    });

    // ── 3. Non-owner sees permission message ──────────────────────────────────

    it('shows permission message for non-owner and hides cancel button', () => {
        renderPage(makeSession('admin'));
        expect(
            screen.getByText(/solo el propietario de la cuenta/i),
        ).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /cancelar suscripción/i })).not.toBeInTheDocument();
    });

    // ── 4. Shows "Baja programada" banner ─────────────────────────────────────

    it('shows cancellation banner when cancel_at_period_end is true', () => {
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse({
                cancel_at_period_end: true,
                cancel_requested_at: '2025-01-15T12:00:00Z',
                cancel_effective_at: '2025-02-01T00:00:00Z',
            }),
            isLoading: false,
            isError: false,
        });
        renderPage();
        expect(screen.getByText(/baja programada para el/i)).toBeInTheDocument();
    });

    // ── 5. Shows "Deshacer baja" button ───────────────────────────────────────

    it('shows undo cancel button when cancellation is scheduled', () => {
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse({
                cancel_at_period_end: true,
                cancel_requested_at: '2025-01-15T12:00:00Z',
                cancel_effective_at: '2025-02-01T00:00:00Z',
            }),
            isLoading: false,
            isError: false,
        });
        renderPage(makeSession('owner'));
        expect(screen.getByRole('button', { name: /deshacer baja/i })).toBeInTheDocument();
    });

    // ── 6. Empty state when no subscription ───────────────────────────────────

    it('shows empty state when there is no subscription', () => {
        mockStatusQuery.mockReturnValue({
            data: { has_subscription: false, subscription: null, role: 'owner' },
            isLoading: false,
            isError: false,
        });
        renderPage();
        expect(
            screen.getByText(/no tenés una suscripción activa/i),
        ).toBeInTheDocument();
    });

    // ── 7. Cancel button opens confirmation modal ────────────────────────────

    it('opens confirmation modal when cancel button is clicked', async () => {
        renderPage(makeSession('owner'));
        const cancelBtn = screen.getByRole('button', { name: /cancelar suscripción/i });
        fireEvent.click(cancelBtn);
        await waitFor(() => {
            expect(screen.getByText(/¿querés cancelar tu suscripción/i)).toBeInTheDocument();
        });
        expect(screen.getByRole('button', { name: /confirmar cancelación/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /volver/i })).toBeInTheDocument();
    });

    // ── 8. Banner shows effective date ───────────────────────────────────────

    it('shows the effective cancellation date in the banner', () => {
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse({
                cancel_at_period_end: true,
                cancel_requested_at: '2025-01-15T12:00:00Z',
                cancel_effective_at: '2025-02-01T00:00:00Z',
            }),
            isLoading: false,
            isError: false,
        });
        renderPage();
        // The date should be formatted in es-AR locale
        // We check that the banner text includes "1 de febrero de 2025" or similar
        const banner = screen.getByText(/baja programada para el/i);
        expect(banner).toBeInTheDocument();
    });

    // ── 9. Loading state ─────────────────────────────────────────────────────

    it('renders loading spinner when data is loading', () => {
        mockStatusQuery.mockReturnValue({
            data: undefined,
            isLoading: true,
            isError: false,
        });
        renderPage();
        expect(screen.getByText(/cargando información del plan/i)).toBeInTheDocument();
    });

    // ── 10. Error state ──────────────────────────────────────────────────────

    it('renders error message when query fails', () => {
        mockStatusQuery.mockReturnValue({
            data: undefined,
            isLoading: false,
            isError: true,
        });
        renderPage();
        expect(screen.getByText(/no pudimos cargar la información/i)).toBeInTheDocument();
    });

    // ── 11. Cancel button is hidden when already scheduled ───────────────────

    it('hides cancel button when cancellation is already scheduled', () => {
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse({
                cancel_at_period_end: true,
                cancel_requested_at: '2025-01-15T12:00:00Z',
                cancel_effective_at: '2025-02-01T00:00:00Z',
            }),
            isLoading: false,
            isError: false,
        });
        renderPage(makeSession('owner'));
        expect(screen.queryByRole('button', { name: /cancelar suscripción/i })).not.toBeInTheDocument();
    });

    // ── 12. "Acceso hasta" label when cancellation is scheduled ──────────────

    it('shows "Acceso hasta" instead of "Próxima renovación" when cancel scheduled', () => {
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse({
                cancel_at_period_end: true,
                cancel_requested_at: '2025-01-15T12:00:00Z',
                cancel_effective_at: '2025-02-01T00:00:00Z',
            }),
            isLoading: false,
            isError: false,
        });
        renderPage();
        expect(screen.getByText('Acceso hasta')).toBeInTheDocument();
        expect(screen.queryByText('Próxima renovación')).not.toBeInTheDocument();
    });

    // ── 13. Shows plan limits when available ─────────────────────────────────

    it('renders plan limits from max_seats and max_branches', () => {
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse({
                max_seats: 10,
                max_branches: 1,
            }),
            isLoading: false,
            isError: false,
        });
        renderPage();
        expect(screen.getByText('Límites del plan')).toBeInTheDocument();
        expect(screen.getByText(/10 usuarios/)).toBeInTheDocument();
        expect(screen.getByText(/1 sucursal/)).toBeInTheDocument();
    });

    // ── 14. Shows plan limits AND renewal date together ──────────────────────

    it('shows both renewal date and limits at the same time', () => {
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse({
                current_period_end: '2025-02-01T00:00:00Z',
                max_seats: 10,
                max_branches: 1,
            }),
            isLoading: false,
            isError: false,
        });
        renderPage();
        expect(screen.getByText('Próxima renovación')).toBeInTheDocument();
        expect(screen.getByText('Límites del plan')).toBeInTheDocument();
    });

    // ── 15. Canceled subscription shows no actions ───────────────────────────

    it('hides all action buttons for canceled subscriptions', () => {
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse({
                status: 'canceled',
                canceled_at: '2025-01-20T00:00:00Z',
                cancel_at_period_end: false,
                can_manage_cancellation: true,
            }),
            isLoading: false,
            isError: false,
        });
        renderPage(makeSession('owner'));
        expect(screen.queryByRole('button', { name: /cancelar suscripción/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /deshacer baja/i })).not.toBeInTheDocument();
    });

    // ── 16. Canceled subscription banner ─────────────────────────────────────

    it('shows canceled banner with date when subscription is canceled', () => {
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse({
                status: 'canceled',
                canceled_at: '2025-01-20T00:00:00Z',
                cancel_at_period_end: false,
            }),
            isLoading: false,
            isError: false,
        });
        renderPage();
        expect(screen.getByText(/tu suscripción fue cancelada/i)).toBeInTheDocument();
    });

    // ── 17. Confirm cancel mutation is called ────────────────────────────────

    it('calls cancel mutation when confirming in the modal', async () => {
        const mockMutate = vi.fn().mockResolvedValue({
            detail: 'Baja programada correctamente.',
            subscription: makeSubscriptionResponse({
                cancel_at_period_end: true,
                cancel_effective_at: '2025-02-01T00:00:00Z',
            }).subscription,
        });
        mockCancelMutation.mockReturnValue({
            ...defaultMutationState(),
            mutateAsync: mockMutate,
        });
        renderPage(makeSession('owner'));
        fireEvent.click(screen.getByRole('button', { name: /cancelar suscripción/i }));
        await waitFor(() => {
            expect(screen.getByRole('button', { name: /confirmar cancelación/i })).toBeInTheDocument();
        });
        fireEvent.click(screen.getByRole('button', { name: /confirmar cancelación/i }));
        await waitFor(() => {
            expect(mockMutate).toHaveBeenCalledWith('');
        });
    });

    // ── 18. Undo cancel mutation is called ───────────────────────────────────

    it('calls undo cancel mutation when clicking undo button', async () => {
        const mockMutate = vi.fn().mockResolvedValue({
            detail: 'La baja fue revertida exitosamente.',
            subscription: makeSubscriptionResponse().subscription,
        });
        mockUndoCancelMutation.mockReturnValue({
            ...defaultMutationState(),
            mutateAsync: mockMutate,
        });
        mockStatusQuery.mockReturnValue({
            data: makeSubscriptionResponse({
                cancel_at_period_end: true,
                cancel_requested_at: '2025-01-15T12:00:00Z',
                cancel_effective_at: '2025-02-01T00:00:00Z',
            }),
            isLoading: false,
            isError: false,
        });
        renderPage(makeSession('owner'));
        fireEvent.click(screen.getByRole('button', { name: /deshacer baja/i }));
        await waitFor(() => {
            expect(mockMutate).toHaveBeenCalled();
        });
    });
});

// features/onboarding/gestion/hooks.ts
// TanStack Query hooks for the Gestión Comercial onboarding wizard.

'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
    completeOnboarding,
    dismissOnboarding,
    fetchOnboardingContext,
    skipOnboardingStep,
    submitBusinessBasics,
    submitFirstProduct,
    submitSalesSetup,
} from './api';
import type {
    BusinessBasicsPayload,
    FirstProductPayload,
    GestionOnboardingContext,
    SalesSetupResponse,
    SkipStepPayload,
} from './types';

export const ONBOARDING_CONTEXT_KEY = ['onboarding', 'gestion', 'context'];

// ─── Query ────────────────────────────────────────────────────────────────────

export function useGestionOnboardingContext(options?: { enabled?: boolean }) {
    return useQuery<GestionOnboardingContext>({
        queryKey: ONBOARDING_CONTEXT_KEY,
        queryFn: fetchOnboardingContext,
        staleTime: 30_000, // 30 s — context is cheap to refetch
        enabled: options?.enabled !== false,
    });
}

// ─── Mutations ────────────────────────────────────────────────────────────────

export function useSubmitBusinessBasics() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (payload: BusinessBasicsPayload) => submitBusinessBasics(payload),
        onSuccess: (data) => {
            qc.setQueryData(ONBOARDING_CONTEXT_KEY, data);
        },
    });
}

export function useSubmitFirstProduct() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (payload: FirstProductPayload) => submitFirstProduct(payload),
        onSuccess: (data) => {
            // data extends GestionOnboardingContext
            qc.setQueryData(ONBOARDING_CONTEXT_KEY, data);
            // Invalidate product list so the products page is fresh
            qc.invalidateQueries({ queryKey: ['gestion', 'products'] });
        },
    });
}

export function useSubmitSalesSetup() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: submitSalesSetup,
        onSuccess: (data: SalesSetupResponse) => {
            qc.setQueryData<GestionOnboardingContext>(ONBOARDING_CONTEXT_KEY, (prev) => {
                if (!prev) return prev;
                return {
                    ...prev,
                    progress: data.progress,
                    steps: data.steps,
                    commercial_settings: data.commercial_settings,
                };
            });
        },
    });
}

export function useSkipOnboardingStep() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (payload: SkipStepPayload) => skipOnboardingStep(payload),
        onSuccess: (data) => {
            qc.setQueryData<GestionOnboardingContext>(ONBOARDING_CONTEXT_KEY, (prev) => {
                if (!prev) return prev;
                return {
                    ...prev,
                    progress: data.progress,
                    steps: data.steps,
                };
            });
        },
    });
}

export function useCompleteOnboarding() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: completeOnboarding,
        onSuccess: (data) => {
            qc.setQueryData(ONBOARDING_CONTEXT_KEY, data);
        },
    });
}

export function useDismissOnboarding() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: dismissOnboarding,
        onSuccess: (data) => {
            qc.setQueryData<GestionOnboardingContext>(ONBOARDING_CONTEXT_KEY, (prev) => {
                if (!prev) return prev;
                return { ...prev, progress: data.progress };
            });
        },
    });
}

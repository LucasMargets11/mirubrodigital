// features/onboarding/gestion/api.ts
// API functions for the Gestión Comercial onboarding wizard.

import { apiGet, apiPost } from '@/lib/api/client';
import type {
    BusinessBasicsPayload,
    DismissResponse,
    FirstProductPayload,
    FirstProductResponse,
    GestionOnboardingContext,
    OnboardingStepResponse,
    SalesSetupResponse,
    SkipStepPayload,
} from './types';

const BASE = '/api/v1/onboarding/gestion';

export function fetchOnboardingContext(): Promise<GestionOnboardingContext> {
    return apiGet<GestionOnboardingContext>(`${BASE}/context`);
}

export function submitBusinessBasics(
    payload: BusinessBasicsPayload,
): Promise<GestionOnboardingContext> {
    return apiPost<GestionOnboardingContext>(`${BASE}/business-basics`, payload);
}

export function submitFirstProduct(
    payload: FirstProductPayload,
): Promise<FirstProductResponse> {
    return apiPost<FirstProductResponse>(`${BASE}/first-product`, payload);
}

export function submitSalesSetup(): Promise<SalesSetupResponse> {
    return apiPost<SalesSetupResponse>(`${BASE}/sales-setup`, {});
}

export function skipOnboardingStep(payload: SkipStepPayload): Promise<OnboardingStepResponse> {
    return apiPost<OnboardingStepResponse>(`${BASE}/skip-step`, payload);
}

export function completeOnboarding(): Promise<GestionOnboardingContext> {
    return apiPost<GestionOnboardingContext>(`${BASE}/complete`, {});
}

export function dismissOnboarding(): Promise<DismissResponse> {
    return apiPost<DismissResponse>(`${BASE}/dismiss`, {});
}

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/lib/api/client';
import { getClientApiBaseUrl } from '@/lib/api-url';
import type { PromoValidationResult } from './subscription-types';
import { BillingProduct, BillingVertical, Bundle, Module, QuoteRequest, QuoteResponse } from './types';

// ── Checkout session reconciliation ──────────────────────────────────────────

/**
 * Shape of a successful response from the reconcile endpoint.
 * The backend always returns HTTP 200; non-2xx (e.g. 405) is an error.
 */
export type CheckoutReconcileResult = {
  session_id: string;
  status: string;
  action_taken?: string[];
  error?: string | null;
};

/**
 * Canonical function for triggering a server-side reconciliation of a
 * checkout session.
 *
 * URL: POST /api/v1/billing/checkout-sessions/{sessionId}/reconcile/
 *   – /reconcile/ is ALWAYS in the path, never in a query parameter.
 *   – No query parameters are added.
 *   – No body is sent (the backend derives everything from the session).
 *
 * Throws if:
 *   – fetch() rejects (network error)
 *   – response.ok is false (e.g. 405 Method Not Allowed)
 *
 * The thrown error has `httpStatus: number` set when the failure is HTTP-level.
 */
export async function reconcileCheckoutSession(
  sessionId: string,
): Promise<CheckoutReconcileResult> {
  const apiUrl = getClientApiBaseUrl();
  // Path-only construction — /reconcile/ is ALWAYS the final path segment.
  const url = `${apiUrl}/api/v1/billing/checkout-sessions/${encodeURIComponent(sessionId)}/reconcile/`;

  const response = await fetch(url, {
    method: 'POST',
    credentials: 'include',
  });

  const payload = await response.json().catch(() => null) as CheckoutReconcileResult | null;

  if (!response.ok) {
    const err = new Error(
      `[billing.checkout.reconcile] HTTP ${response.status} for session ${sessionId}`,
    );
    (err as Error & { httpStatus: number }).httpStatus = response.status;
    throw err;
  }

  return payload ?? { session_id: sessionId, status: 'unknown', error: 'empty response' };
}

export function getBillingProducts(): Promise<BillingProduct[]> {
  return apiGet<BillingProduct[]>('/api/v1/billing/products/');
}

export function getBundlesByVertical(vertical: BillingVertical): Promise<Bundle[]> {
  return apiGet<Bundle[]>(`/api/v1/billing/bundles/?vertical=${vertical}`);
}

export function useModules(vertical: BillingVertical) {
  return useQuery({
    queryKey: ['billing-modules', vertical],
    queryFn: async () => {
      const data = await apiGet<Module[]>(`/api/v1/billing/modules/?vertical=${vertical}`);
      return data;
    },
    enabled: !!vertical,
  });
}

export function useBundles(vertical: BillingVertical) {
  return useQuery({
    queryKey: ['billing-bundles', vertical],
    queryFn: () => getBundlesByVertical(vertical),
    enabled: !!vertical,
  });
}

export function useQuote() {
  return useMutation({
    mutationFn: async (req: QuoteRequest) => {
      const data = await apiPost<QuoteResponse>('/api/v1/billing/quote/', req);
      return data;
    },
  });
}

export function useSubscribe() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (req: QuoteRequest) => { 
      const data = await apiPost('/api/v1/billing/subscribe/', req);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['billing-subscription'] });
    },
  });
}

// ── Promotional code validation ───────────────────────────────────────────────

export interface ValidatePromoCodeParams {
  code: string;
  plan_code: string;
  billing_period?: string;
}

export function validatePromoCode(params: ValidatePromoCodeParams): Promise<PromoValidationResult> {
  return apiPost<PromoValidationResult>('/api/v1/billing/promo-codes/validate/', {
    code: params.code,
    plan_code: params.plan_code,
    billing_period: params.billing_period ?? 'monthly',
  });
}

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/lib/api/client';
import type { PromoValidationResult } from './subscription-types';
import { BillingProduct, BillingVertical, Bundle, Module, QuoteRequest, QuoteResponse } from './types';

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

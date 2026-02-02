import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/lib/api/client';
import { Bundle, Module, QuoteRequest, QuoteResponse } from './types';

export function useModules(vertical: string) {
  return useQuery({
    queryKey: ['billing-modules', vertical],
    queryFn: async () => {
      const data = await apiGet<Module[]>(`/api/v1/billing/modules/?vertical=${vertical}`);
      return data;
    },
    enabled: !!vertical,
  });
}

export function useBundles(vertical: string) {
  return useQuery({
    queryKey: ['billing-bundles', vertical],
    queryFn: async () => {
      const data = await apiGet<Bundle[]>(`/api/v1/billing/bundles/?vertical=${vertical}`);
      return data;
    },
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

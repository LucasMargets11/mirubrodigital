'use client';

/**
 * TanStack Query hooks for POS operative cash endpoints.
 *
 * All hooks read the employee token from EmployeeSessionContext and use
 * X-Employee-Token auth via the pos.ts API client. The admin cookie-based
 * client is never touched here.
 *
 * Key behaviours:
 * - Only enabled when there is an authenticated session without a pending PIN change.
 * - 401 responses invalidate the query; callers handle redirect via the layout guard.
 * - Mutations refetch the current session automatically on success.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { ApiError } from '@/lib/api/client';
import {
  posCloseCurrentCashSession,
  posCreateCashMovement,
  posCreateCustomer,
  posCreateSale,
  posGetCategories,
  posGetCurrentCashMovements,
  posGetCurrentCashSession,
  posGetProducts,
  posOpenCashSession,
  posSearchCustomers,
} from '@/lib/api/pos';
import type {
  PosCashCloseRequest,
  PosCashCurrentMovementsResponse,
  PosCashMovementRequest,
  PosCashOpenRequest,
  PosCashSession,
  PosCashSessionResponse,
  PosCategoriesResponse,
  PosCustomerCreatePayload,
  PosCustomersResponse,
  PosCustomerSummary,
  PosProductsResponse,
  PosSaleCreateResponse,
  PosSalePayload,
} from '@/types/pos-cash';
import { useEmployeeSession } from './context';

// ── Query keys ────────────────────────────────────────────────────────────────

export const posCashKeys = {
  /** Scoped to the employee token so different employees get different cache entries. */
  current: (token: string | null) => ['pos', 'cash', 'current', token] as const,
};

export const posCashMovementsKeys = {
  current: (token: string | null) => ['pos', 'cash', 'movements', token] as const,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function useTokenGuard(): { token: string | null; enabled: boolean } {
  const { session } = useEmployeeSession();
  const enabled =
    session.status === 'authenticated' && !session.mustChangePin;
  const token =
    session.status === 'authenticated' ? session.token : null;
  return { token, enabled };
}

// ── Current session query ─────────────────────────────────────────────────────

/**
 * GET /api/v1/pos/cash/current/
 *
 * Returns the employee's current open cash session, or null.
 * Refetches every 30 seconds while mounted.
 */
export function usePosCashCurrentSession() {
  const { token, enabled } = useTokenGuard();

  const query = useQuery<PosCashSessionResponse, ApiError>({
    queryKey: posCashKeys.current(token),
    queryFn: () => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posGetCurrentCashSession(token);
    },
    enabled,
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: false,
  });

  return {
    ...query,
    session: (query.data?.session ?? null) as PosCashSession | null,
  };
}

// ── Current session movements query ──────────────────────────────────────────

/**
 * GET /api/v1/pos/cash/current/movements/
 *
 * Returns movements for the employee's current open session, newest first.
 * Returns an empty array when no session is open (backend returns 200 + []).
 * Refetches every 30 seconds while mounted.
 */
export function usePosCashCurrentMovements() {
  const { token, enabled } = useTokenGuard();

  return useQuery<PosCashCurrentMovementsResponse, ApiError>({
    queryKey: posCashMovementsKeys.current(token),
    queryFn: () => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posGetCurrentCashMovements(token);
    },
    enabled,
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: false,
  });
}

// ── Open session mutation ─────────────────────────────────────────────────────

/**
 * POST /api/v1/pos/cash/open/
 *
 * Invalidates the current session query on success.
 * On 400 "already open" the caller should refetch /current/ instead.
 */
export function usePosOpenCashSession() {
  const { token } = useTokenGuard();
  const queryClient = useQueryClient();

  return useMutation<PosCashSessionResponse, ApiError, PosCashOpenRequest>({
    mutationFn: (payload) => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posOpenCashSession(token, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'cash'] });
    },
  });
}

// ── Close session mutation ────────────────────────────────────────────────────

/**
 * POST /api/v1/pos/cash/current/close/
 *
 * Invalidates the current session query on success.
 */
export function usePosCloseCashSession() {
  const { token } = useTokenGuard();
  const queryClient = useQueryClient();

  return useMutation<PosCashSessionResponse, ApiError, PosCashCloseRequest>({
    mutationFn: (payload) => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posCloseCurrentCashSession(token, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'cash'] });
    },
  });
}

// ── Create movement mutation ──────────────────────────────────────────────────

/**
 * POST /api/v1/pos/cash/current/movements/
 *
 * Invalidates the current session query on success so totals refresh.
 */
export function usePosCreateCashMovement() {
  const { token } = useTokenGuard();
  const queryClient = useQueryClient();

  return useMutation<{ movement: import('@/types/pos-cash').PosCashMovement }, ApiError, PosCashMovementRequest>({
    mutationFn: (payload) => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posCreateCashMovement(token, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'cash'] });
    },
  });
}

// ── Error router helper ───────────────────────────────────────────────────────

/**
 * Classifies an ApiError from a cash endpoint and returns a human-readable
 * message. Also performs redirects for 401/pin_change_required.
 */
export function usePosErrorHandler() {
  const router = useRouter();
  const { logout } = useEmployeeSession();

  return function handleCashError(err: unknown): string {
    if (!(err instanceof ApiError)) {
      return 'Error inesperado. Intentá de nuevo.';
    }

    if (err.status === 401) {
      logout();
      router.replace('/pos/login' as never);
      return 'Tu sesión expiró. Redirigiendo al login…';
    }

    const payload = err.payload as { code?: string; detail?: string; error?: string } | undefined;

    if (err.status === 403 && payload?.code === 'pin_change_required') {
      router.replace('/pos/change-pin' as never);
      return 'Debés cambiar tu PIN antes de operar.';
    }

    return payload?.detail ?? payload?.error ?? err.message ?? 'Error inesperado.';
  };
}

// ── POS Catalog — product search ──────────────────────────────────────────────

export const posProductKeys = {
  list: (token: string | null, search: string) =>
    ['pos', 'catalog', 'products', token, search] as const,
  browse: (
    token: string | null,
    categoryId: string | null,
    search: string,
    inStockOnly: boolean,
  ) => ['pos', 'catalog', 'products-browse', token, categoryId, search, inStockOnly] as const,
};

/**
 * GET /api/v1/pos/catalog/products/?search=<query>
 *
 * Fetches active products for the employee's business.
 * Enabled only when authenticated + no pending PIN change.
 * search is only applied to the query when it has at least 2 chars.
 */
export function usePosProducts(search: string = '') {
  const { token, enabled } = useTokenGuard();

  return useQuery<PosProductsResponse, ApiError>({
    queryKey: posProductKeys.list(token, search),
    queryFn: () => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posGetProducts(token, search);
    },
    enabled: enabled && search.length >= 2,
    staleTime: 60_000,
    retry: false,
  });
}

/**
 * Category browser query — supports category, text search, and in-stock filter.
 * Fetches all products in the selected category (or all if categoryId = null).
 * Enabled as soon as the employee is authenticated.
 */
export function usePosBrowseProducts(
  categoryId: string | null,
  search: string = '',
  inStockOnly: boolean = false,
) {
  const { token, enabled } = useTokenGuard();

  return useQuery<PosProductsResponse, ApiError>({
    queryKey: posProductKeys.browse(token, categoryId, search, inStockOnly),
    queryFn: () => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posGetProducts(token, {
        search: search.length >= 2 ? search : undefined,
        category_id: categoryId ?? undefined,
        in_stock_only: inStockOnly || undefined,
        limit: 200,
      });
    },
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}

// ── POS Catalog — categories ──────────────────────────────────────────────────

export const posCategoryKeys = {
  list: (token: string | null) => ['pos', 'catalog', 'categories', token] as const,
};

/**
 * GET /api/v1/pos/catalog/categories/
 *
 * Fetches active categories with product counts for the employee's business.
 * Cached for 5 minutes; categories change rarely during a sales session.
 */
export function usePosCategories() {
  const { token, enabled } = useTokenGuard();

  return useQuery<PosCategoriesResponse, ApiError>({
    queryKey: posCategoryKeys.list(token),
    queryFn: () => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posGetCategories(token);
    },
    enabled,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

// ── POS Sales — create sale mutation ──────────────────────────────────────────

/**
 * POST /api/v1/pos/sales/
 *
 * Creates a sale as the authenticated employee.
 * Invalidates the current cash session query on success so totals refresh.
 *
 * Throws ApiError 403 if capability 'can_create_sale' is missing.
 * Throws ApiError 400 on validation errors.
 */
export function usePosCreateSale() {
  const { token } = useTokenGuard();
  const queryClient = useQueryClient();

  return useMutation<PosSaleCreateResponse, ApiError, PosSalePayload>({
    mutationFn: (payload) => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posCreateSale(token, payload);
    },
    onSuccess: () => {
      // Refresh cash session totals after a sale is registered
      queryClient.invalidateQueries({ queryKey: ['pos', 'cash'] });
    },
  });
}

// ── POS Customers — search + create ──────────────────────────────────────────

export const posCustomerKeys = {
  list: (token: string | null, search: string) =>
    ['pos', 'customers', token, search] as const,
};

/**
 * GET /api/v1/pos/customers/?search=<query>
 *
 * Searches active customers for the employee's business.
 * Only enabled when search has at least 2 characters.
 */
export function usePosCustomers(search: string = '') {
  const { token, enabled } = useTokenGuard();

  return useQuery<PosCustomersResponse, ApiError>({
    queryKey: posCustomerKeys.list(token, search),
    queryFn: () => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posSearchCustomers(token, search);
    },
    enabled: enabled && search.length >= 2,
    staleTime: 30_000,
    retry: false,
  });
}

/**
 * POST /api/v1/pos/customers/
 *
 * Creates a minimal customer from the POS terminal.
 * Invalidates the customer search cache on success.
 */
export function usePosCreateCustomer() {
  const { token } = useTokenGuard();
  const queryClient = useQueryClient();

  return useMutation<PosCustomerSummary, ApiError, PosCustomerCreatePayload>({
    mutationFn: (payload) => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posCreateCustomer(token, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pos', 'customers'] });
    },
  });
}

// ── Unified product + category search ─────────────────────────────────────────

import type { UnifiedSearchResult } from './search-ranking';
import { rankSearchResults } from './search-ranking';

/**
 * Combines the remote product search with the locally-cached category list and
 * applies the `rankSearchResults` scoring so categories surface first when the
 * query strongly matches a category name.
 *
 * - Categories are served from the in-memory TanStack cache (staleTime 5 min).
 * - Products are fetched from the backend (same query as `usePosProducts`).
 * - Ranking is computed client-side via `useMemo` so it is synchronous.
 */
export function useUnifiedProductSearch(query: string): {
  results: UnifiedSearchResult[];
  isLoading: boolean;
  isError: boolean;
  topCategoryAnnouncement: string;
} {
  const categoriesQuery = usePosCategories();
  const productsQuery = usePosProducts(query);

  const categories = categoriesQuery.data?.results ?? [];
  const products = productsQuery.data?.results ?? [];

  const results = useMemo(
    () => (query.length >= 2 ? rankSearchResults(query, categories, products) : []),
    [query, categories, products],
  );

  // Announcement text for when the top result is a category.
  const topCategoryAnnouncement = useMemo(() => {
    if (results[0]?.type !== 'category') return '';
    const cat = results[0].data;
    return `Se encontró la categoría ${cat.name} como mejor coincidencia.`;
  }, [results]);

  return {
    results,
    isLoading:
      categoriesQuery.isLoading ||
      (query.length >= 2 && productsQuery.isLoading),
    isError: productsQuery.isError,
    topCategoryAnnouncement,
  };
}

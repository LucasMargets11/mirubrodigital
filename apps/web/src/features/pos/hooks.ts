'use client';

/**
 * Operative POS hooks.
 *
 * useEmployeeSession()   — reads the employee session context (re-exported for convenience)
 * usePinChangeGuard()    — returns whether the employee must change PIN before proceeding
 * usePosCapabilities()   — TanStack Query wrapper for GET /pos/capabilities/
 */

import { useQuery } from '@tanstack/react-query';
import { posGetCapabilities } from '@/lib/api/pos';
import type { EmployeeCapabilities } from '@/types/employees';
import { useEmployeeSession } from './context';

// Re-export the core hook so consumers only need to import from features/pos/hooks
export { useEmployeeSession } from './context';

// ── Pin change guard ──────────────────────────────────────────────────────────

/**
 * Returns whether the currently authenticated employee is required to
 * change their PIN before accessing any protected POS route.
 *
 * Returns false when there is no active session (unauthenticated).
 */
export function usePinChangeGuard(): { pinChangeRequired: boolean } {
  const { session } = useEmployeeSession();

  const pinChangeRequired =
    session.status === 'authenticated' && session.mustChangePin === true;

  return { pinChangeRequired };
}

// ── Capabilities query ────────────────────────────────────────────────────────

const CAPABILITIES_STALE_TIME = 5 * 60 * 1000; // 5 minutes

/**
 * TanStack Query wrapper for GET /pos/capabilities/.
 *
 * Only runs when there is an authenticated session without a pending PIN change
 * (the backend would return 403 pin_change_required otherwise).
 *
 * Returns standard QueryResult fields plus a convenience `capabilities` shortcut.
 */
export function usePosCapabilities() {
  const { session } = useEmployeeSession();

  const enabled =
    session.status === 'authenticated' && !session.mustChangePin;

  const token =
    session.status === 'authenticated' ? session.token : null;

  const query = useQuery<EmployeeCapabilities, Error>({
    queryKey: ['pos', 'capabilities', token],
    queryFn: () => {
      if (!token) throw new Error('No hay token de sesión operativa');
      return posGetCapabilities(token);
    },
    enabled,
    staleTime: CAPABILITIES_STALE_TIME,
    retry: false,
  });

  return {
    ...query,
    capabilities: query.data?.capabilities ?? null,
    roleType: query.data?.role_type ?? null,
  };
}

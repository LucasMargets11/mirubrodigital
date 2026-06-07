'use client';

/**
 * TanStack Query hooks for the POS offline bootstrap snapshot (PR-OFF-02B).
 *
 * - usePosOfflineSnapshot()        → reads the persisted snapshot from IndexedDB.
 * - usePosOfflineBootstrapDownload() → downloads the bootstrap from the API and
 *                                      persists it locally, replacing the prior
 *                                      snapshot. On error the previous snapshot
 *                                      is preserved.
 *
 * This PR persists data only. It does NOT enable offline sales.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api/client';
import { posGetOfflineBootstrap } from '@/lib/api/pos';
import { useEmployeeSession } from '../context';
import { loadBootstrapSnapshot, saveBootstrapSnapshot } from './bootstrap-store';
import type { StoredPosOfflineBootstrap } from './types';

// ── Query keys ────────────────────────────────────────────────────────────────

export const posOfflineKeys = {
  snapshot: (token: string | null) => ['pos', 'offline', 'snapshot', token] as const,
};

// ── Token guard ───────────────────────────────────────────────────────────────

function useOfflineToken(): { token: string | null; enabled: boolean } {
  const { session } = useEmployeeSession();
  const enabled = session.status === 'authenticated' && !session.mustChangePin;
  const token = session.status === 'authenticated' ? session.token : null;
  return { token, enabled };
}

// ── Snapshot read ─────────────────────────────────────────────────────────────

/**
 * Reads the locally-persisted offline snapshot (or null). Backed by IndexedDB;
 * does not hit the network.
 */
export function usePosOfflineSnapshot() {
  const { token, enabled } = useOfflineToken();
  return useQuery<StoredPosOfflineBootstrap | null>({
    queryKey: posOfflineKeys.snapshot(token),
    queryFn: () => loadBootstrapSnapshot(),
    enabled,
    staleTime: Infinity,
    // IndexedDB reads do not need the network — keep loading the local snapshot
    // even when the device is offline (when we need it most).
    networkMode: 'always',
  });
}

// ── Download + persist ──────────────────────────────────────────────────────

/**
 * Downloads the bootstrap snapshot from the API and persists it locally,
 * fully replacing any prior snapshot. On success the snapshot query is updated.
 * On failure the existing snapshot is left untouched.
 */
export function usePosOfflineBootstrapDownload() {
  const { token } = useOfflineToken();
  const queryClient = useQueryClient();

  return useMutation<StoredPosOfflineBootstrap, ApiError, void>({
    mutationFn: async () => {
      if (!token) {
        throw new ApiError('Sesión no disponible', 401, {});
      }
      const payload = await posGetOfflineBootstrap(token);
      return saveBootstrapSnapshot(payload);
    },
    onSuccess: (snapshot) => {
      queryClient.setQueryData(posOfflineKeys.snapshot(token), snapshot);
    },
  });
}

'use client';

import { useCallback, useEffect, useState } from 'react';

/**
 * Network connection status.
 *
 * - `offline`  → the browser reports no connection.
 * - `online`   → connected normally.
 * - `reconnecting` → connection just came back; cleared shortly after so the UI
 *   can briefly show a "reconnecting/reconnected" hint before settling.
 */
export type NetworkStatus = 'online' | 'offline' | 'reconnecting';

export interface UseNetworkStatusResult {
  /** True when the browser reports an active connection. */
  isOnline: boolean;
  /** Convenience inverse of {@link isOnline}. */
  isOffline: boolean;
  /** Coarse status for UI rendering. */
  status: NetworkStatus;
}

/**
 * SSR-safe initial value. We assume "online" on the server and during the first
 * client render to avoid hydration mismatches and a flash of the offline banner;
 * the real value is reconciled in `useEffect`.
 */
function getInitialOnline(): boolean {
  if (typeof navigator === 'undefined') return true;
  return navigator.onLine;
}

/**
 * Tracks the browser online/offline state.
 *
 * Exposes `isOnline`, a derived `status`, and reacts to the native `online` /
 * `offline` window events. On reconnection it momentarily reports
 * `reconnecting` so the POS can surface a transient "conectando…" state.
 *
 * This is purely a connectivity signal — it does NOT enable offline writes.
 */
export function useNetworkStatus(): UseNetworkStatusResult {
  const [isOnline, setIsOnline] = useState<boolean>(getInitialOnline);
  const [status, setStatus] = useState<NetworkStatus>(() =>
    getInitialOnline() ? 'online' : 'offline',
  );

  const handleOnline = useCallback(() => {
    setIsOnline(true);
    setStatus('reconnecting');
  }, []);

  const handleOffline = useCallback(() => {
    setIsOnline(false);
    setStatus('offline');
  }, []);

  useEffect(() => {
    // Reconcile with the real value on mount (covers the SSR default). This is a
    // deliberate one-shot hydration sync, not a cascading render loop.
    const online = navigator.onLine;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsOnline(online);
    setStatus(online ? 'online' : 'offline');

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [handleOnline, handleOffline]);

  // Settle the transient "reconnecting" state back to "online".
  useEffect(() => {
    if (status !== 'reconnecting') return;
    const timer = window.setTimeout(() => {
      setStatus((current) => (current === 'reconnecting' ? 'online' : current));
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [status]);

  return { isOnline, isOffline: !isOnline, status };
}

/**
 * Minimal alias that only exposes the boolean, for call sites that just need to
 * know whether the device is connected.
 */
export function useOnlineStatus(): boolean {
  return useNetworkStatus().isOnline;
}

'use client';

/**
 * PosConnectionBanner — connection-state indicator for the POS shell (PR-OFF-01).
 *
 * Renders a thin banner reflecting the device connectivity:
 * - online:        "Conectado" (subtle; auto-hidden after the reconnect hint).
 * - reconnecting:  "Reconectando…"
 * - offline:       contingency mode active/unavailable depending on the snapshot.
 *
 * IMPORTANT: this banner is informational only. Offline sales are captured and
 * queued locally (PR-OFF-04); syncing with the backend arrives in PR-OFF-05+.
 */

import { useEffect, useState } from 'react';
import { Wifi, WifiOff, RefreshCw } from 'lucide-react';
import { useNetworkStatus } from '@/hooks/use-network-status';
import { usePosOfflineCatalog } from '@/features/pos/offline/offline-catalog';
import { usePosOfflineGuard } from '@/features/pos/offline/offline-guard';

export function PosConnectionBanner() {
  const { status } = useNetworkStatus();
  const offlineCatalog = usePosOfflineCatalog();
  const offlineGuard = usePosOfflineGuard();

  // After settling back to "online", show a brief "Conectado" confirmation then
  // hide the banner so it does not take permanent screen space.
  const [showOnlineConfirmation, setShowOnlineConfirmation] = useState(false);

  useEffect(() => {
    if (status === 'reconnecting') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setShowOnlineConfirmation(true);
      return;
    }
    if (status === 'online' && showOnlineConfirmation) {
      const timer = window.setTimeout(() => setShowOnlineConfirmation(false), 2500);
      return () => window.clearTimeout(timer);
    }
  }, [status, showOnlineConfirmation]);

  // Nothing to show while stably online (and not in the post-reconnect window).
  if (status === 'online' && !showOnlineConfirmation) {
    return null;
  }

  if (status === 'offline') {
    // Contingency is only "active" when the snapshot is usable AND not blocked
    // by an expiry / pending-limit guardrail (PR-OFF-07).
    const contingencyActive =
      offlineCatalog.canBuildCart && offlineGuard.blockReason === null;
    return (
      <div
        role="status"
        aria-live="polite"
        data-testid="pos-connection-banner"
        data-status="offline"
        className="flex items-center justify-center gap-2 bg-amber-500 px-4 py-2 text-center text-sm font-medium text-white"
      >
        <WifiOff className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          {contingencyActive
            ? 'Sin conexión — modo contingencia activo'
            : 'Sin conexión — modo contingencia no disponible'}
        </span>
      </div>
    );
  }

  if (status === 'reconnecting') {
    return (
      <div
        role="status"
        aria-live="polite"
        data-testid="pos-connection-banner"
        data-status="reconnecting"
        className="flex items-center justify-center gap-2 bg-blue-500 px-4 py-2 text-center text-sm font-medium text-white"
      >
        <RefreshCw className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
        <span>Reconectando…</span>
      </div>
    );
  }

  // status === 'online' with a recent reconnection → brief confirmation.
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="pos-connection-banner"
      data-status="online"
      className="flex items-center justify-center gap-2 bg-emerald-600 px-4 py-2 text-center text-sm font-medium text-white"
    >
      <Wifi className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span>Conectado</span>
    </div>
  );
}

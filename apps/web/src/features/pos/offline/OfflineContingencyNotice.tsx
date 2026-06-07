'use client';

/**
 * OfflineContingencyNotice (PR-OFF-07)
 *
 * Security/awareness banner shown inside the quick-sale screen while the device
 * is offline with a usable snapshot. It surfaces:
 *  - "Modo contingencia activo"
 *  - "Usando datos guardados de HH:mm"
 *  - the snapshot expiry window ("Los datos vencen en X horas")
 *  - blocking (expired / too many pending) and warning (expiring soon) states
 *
 * Pure presentation: all data comes from {@link usePosOfflineGuard} via props
 * passed by the owner page so there is a single guard instance.
 */

import { ShieldAlert } from 'lucide-react';
import { formatSavedAtTime } from './offline-catalog';
import type { PosOfflineGuard } from './offline-guard';

export interface OfflineContingencyNoticeProps {
  guard: PosOfflineGuard;
}

export function OfflineContingencyNotice({ guard }: OfflineContingencyNoticeProps) {
  const { snapshot, savedAt, expiry, blockReason, warningMessage } = guard;

  // Nothing to show when there is no snapshot to operate on.
  if (!snapshot) return null;

  const tone = blockReason
    ? 'border-rose-200 bg-rose-50 text-rose-800'
    : warningMessage
      ? 'border-amber-200 bg-amber-50 text-amber-900'
      : 'border-indigo-200 bg-indigo-50 text-indigo-800';

  const expiryLine = expiry.isExpired
    ? 'Los datos offline están vencidos.'
    : expiry.hoursUntilExpiry !== null
      ? `Los datos vencen en ${expiry.hoursUntilExpiry} h.`
      : null;

  return (
    <div
      data-testid="offline-contingency-notice"
      className={`flex gap-2 rounded-2xl border px-3 py-2.5 text-xs ${tone}`}
    >
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="space-y-0.5">
        <p className="font-semibold">Modo contingencia activo</p>
        {savedAt ? (
          <p data-testid="offline-contingency-saved-at">
            Usando datos guardados de {formatSavedAtTime(savedAt)}
          </p>
        ) : null}
        {expiryLine ? (
          <p data-testid="offline-contingency-expiry">{expiryLine}</p>
        ) : null}
        {blockReason ? (
          <p data-testid="offline-contingency-block" className="font-medium">
            {blockReason}
          </p>
        ) : warningMessage ? (
          <p data-testid="offline-contingency-warning" className="font-medium">
            {warningMessage}
          </p>
        ) : null}
      </div>
    </div>
  );
}

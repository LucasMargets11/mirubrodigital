'use client';

import Link from 'next/link';
import type { SubscriptionReasonCode } from '@/lib/auth/types';

type SubscriptionBannerProps = {
  reasonCode: SubscriptionReasonCode;
  graceUntil?: string | null;
  showRenewalPrompt?: boolean;
};

/**
 * Shows a non-blocking top banner when the subscription state requires
 * user attention (e.g. PAST_DUE within grace period).
 *
 * This component is only rendered inside AppShell when access_allowed=true
 * but there is a warning condition.  Hard-blocked states redirect from the
 * layout before reaching AppShell.
 */
export function SubscriptionBanner({ reasonCode, graceUntil, showRenewalPrompt }: SubscriptionBannerProps) {
  if (reasonCode === 'access_granted') {
    return null;
  }

  const config = BANNER_CONFIG[reasonCode];
  if (!config) {
    return null;
  }

  const graceDate = graceUntil ? new Date(graceUntil).toLocaleDateString('es-AR') : null;

  return (
    <div className={`w-full px-4 py-2 text-sm font-medium flex items-center justify-between gap-4 ${config.className}`}>
      <span>
        {config.message}
        {graceDate && ` Fecha límite: ${graceDate}.`}
      </span>
      {showRenewalPrompt && (
        <Link
          href="/app/servicios"
          className="shrink-0 rounded-full bg-white/20 px-3 py-1 text-xs font-semibold hover:bg-white/30 transition-colors"
        >
          Regularizar →
        </Link>
      )}
    </div>
  );
}

const BANNER_CONFIG: Partial<Record<SubscriptionReasonCode, { message: string; className: string }>> = {
  grace_period_active: {
    message: 'Tu pago está vencido. Tenés un período de gracia activo; regularizá tu suscripción para evitar la suspensión.',
    className: 'bg-amber-500 text-amber-950',
  },
};

"use client";

import Link from 'next/link';
import { cn } from '@/lib/utils';
import { ExternalLink } from 'lucide-react';
import { StatusBadge } from '@/components/admin/status-badge';
import type { AdminNotification } from '@/lib/admin/types';

// ── Display helpers ───────────────────────────────────────────────────────

export const NOTIF_SEVERITY_LABEL: Record<string, string> = {
  critical: 'Crítico',
  warning: 'Advertencia',
  success: 'OK',
  info: 'Info',
};

export const NOTIF_SEVERITY_COLOR: Record<string, string> = {
  critical: 'bg-red-100 text-red-700',
  warning: 'bg-amber-100 text-amber-700',
  success: 'bg-emerald-100 text-emerald-700',
  info: 'bg-blue-100 text-blue-700',
};

export const NOTIF_STATUS_LABEL: Record<string, string> = {
  unread: 'No leída',
  read: 'Leída',
  resolved: 'Resuelta',
  archived: 'Archivada',
};

export const NOTIF_STATUS_COLOR: Record<string, string> = {
  unread: 'bg-brand-100 text-brand-700',
  read: 'bg-slate-100 text-slate-600',
  resolved: 'bg-emerald-100 text-emerald-700',
  archived: 'bg-slate-50 text-slate-400',
};

function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-AR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

// ── Component ─────────────────────────────────────────────────────────────

type NotificationItemProps = {
  notification: AdminNotification;
  /** When true, renders a compact version suitable for the dropdown */
  compact?: boolean;
  actions?: React.ReactNode;
};

export function NotificationItem({
  notification: n,
  compact = false,
  actions,
}: NotificationItemProps) {
  const isUnread = n.status === 'unread';
  const isArchived = n.status === 'archived';

  return (
    <div
      className={cn(
        'rounded-lg border px-4 py-3 transition-colors',
        isUnread
          ? 'border-brand-200 bg-brand-50'
          : isArchived
            ? 'border-slate-100 bg-slate-50 opacity-70'
            : 'border-slate-200 bg-white',
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 mb-1">
            <StatusBadge
              label={NOTIF_SEVERITY_LABEL[n.severity] ?? n.severity}
              colorClass={NOTIF_SEVERITY_COLOR[n.severity] ?? 'bg-slate-100 text-slate-600'}
            />
            <StatusBadge
              label={NOTIF_STATUS_LABEL[n.status] ?? n.status}
              colorClass={NOTIF_STATUS_COLOR[n.status] ?? 'bg-slate-100 text-slate-600'}
            />
          </div>
          <p
            className={cn(
              'font-semibold text-sm leading-tight',
              isUnread ? 'text-slate-900' : 'text-slate-700',
            )}
          >
            {n.title}
          </p>
        </div>
        <span className="shrink-0 text-xs text-slate-400 mt-0.5">
          {formatDateTime(n.created_at)}
        </span>
      </div>

      {/* Message */}
      {!compact && n.message && (
        <p className="mt-1.5 text-sm text-slate-600 line-clamp-3">{n.message}</p>
      )}
      {compact && n.message && (
        <p className="mt-1 text-xs text-slate-500 line-clamp-2">{n.message}</p>
      )}

      {/* Business + CTA */}
      {!compact && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
            {n.business_name && (
              <span>
                <span className="font-medium text-slate-700">{n.business_name}</span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {n.action_url && (
              <Link
                href={n.action_url as any}
                target={n.action_url.startsWith('http') ? '_blank' : undefined}
                rel={n.action_url.startsWith('http') ? 'noopener noreferrer' : undefined}
                className="inline-flex items-center gap-1 text-xs font-medium text-brand-600 hover:underline"
              >
                Ver detalle
                {n.action_url.startsWith('http') && <ExternalLink className="h-3 w-3" />}
              </Link>
            )}
            {actions}
          </div>
        </div>
      )}

      {compact && n.business_name && (
        <p className="mt-1 text-xs text-slate-400">{n.business_name}</p>
      )}
    </div>
  );
}

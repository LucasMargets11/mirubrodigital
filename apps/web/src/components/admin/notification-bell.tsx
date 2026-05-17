"use client";

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Bell, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fetchAdminUnreadCountClient, fetchAdminNotificationsClient } from '@/lib/admin/notifications.client';
import { NotificationItem } from './notification-item';
import type { AdminNotification, AdminNotificationUnreadCount } from '@/lib/admin/types';

const POLL_INTERVAL_MS = 60_000; // 60 s
const DROPDOWN_PREVIEW_COUNT = 6;

type NotificationBellProps = {
  /** Initial unread count hydrated from SSR */
  initialCount?: AdminNotificationUnreadCount | null;
};

export function NotificationBell({ initialCount }: NotificationBellProps) {
  const [counts, setCounts] = useState<AdminNotificationUnreadCount>(
    initialCount ?? { count: 0, critical_count: 0 },
  );
  const [open, setOpen] = useState(false);
  const [previews, setPreviews] = useState<AdminNotification[]>([]);
  const [loadingPreviews, setLoadingPreviews] = useState(false);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // ── Polling ─────────────────────────────────────────────────────────────
  const refreshCount = useCallback(async () => {
    const data = await fetchAdminUnreadCountClient();
    if (data) setCounts(data);
  }, []);

  useEffect(() => {
    refreshCount();
    const timer = setInterval(refreshCount, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refreshCount]);

  // ── Load dropdown previews ───────────────────────────────────────────────
  const loadPreviews = useCallback(async () => {
    setLoadingPreviews(true);
    const data = await fetchAdminNotificationsClient({ page_size: DROPDOWN_PREVIEW_COUNT });
    setPreviews(data?.results ?? []);
    setLoadingPreviews(false);
  }, []);

  const toggleDropdown = useCallback(() => {
    setOpen((prev) => {
      if (!prev) loadPreviews();
      return !prev;
    });
  }, [loadPreviews]);

  // ── Close on outside click ───────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        !buttonRef.current?.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  const displayCount = Math.min(counts.count, 99);
  const showBadge = counts.count > 0;

  return (
    <div className="relative">
      {/* Bell button */}
      <button
        ref={buttonRef}
        type="button"
        onClick={toggleDropdown}
        aria-label={`Notificaciones${showBadge ? ` (${counts.count} sin leer)` : ''}`}
        className={cn(
          'relative flex h-9 w-9 items-center justify-center rounded-lg text-slate-300 transition-colors',
          'hover:bg-slate-800 hover:text-white',
          open && 'bg-slate-800 text-white',
        )}
      >
        <Bell className="h-5 w-5" />
        {showBadge && (
          <span
            aria-hidden="true"
            className={cn(
              'absolute -right-1 -top-1 flex h-4.5 min-w-[1.125rem] items-center justify-center rounded-full px-1',
              'text-[10px] font-bold leading-none text-white',
              counts.critical_count > 0 ? 'bg-red-500' : 'bg-brand-500',
            )}
          >
            {counts.count > 99 ? '99+' : displayCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div
          ref={dropdownRef}
          role="dialog"
          aria-label="Notificaciones recientes"
          className="absolute left-0 top-full z-50 mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-xl"
        >
          {/* Dropdown header */}
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-800">Notificaciones</p>
            {showBadge && (
              <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700">
                {counts.count} sin leer
              </span>
            )}
          </div>

          {/* Previews */}
          <div className="max-h-96 overflow-y-auto">
            {loadingPreviews ? (
              <div className="px-4 py-8 text-center text-xs text-slate-400">
                Cargando...
              </div>
            ) : previews.length === 0 ? (
              <div className="px-4 py-8 text-center text-xs text-slate-400">
                Sin notificaciones recientes
              </div>
            ) : (
              <ul className="divide-y divide-slate-50">
                {previews.map((n) => (
                  <li key={n.id} className="px-3 py-2">
                    <NotificationItem notification={n} compact />
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Footer link */}
          <div className="border-t border-slate-100 px-4 py-3">
            <Link
              href="/admin/notificaciones"
              onClick={() => setOpen(false)}
              className="flex items-center justify-center gap-1.5 text-xs font-medium text-brand-600 hover:underline"
            >
              Ver todas las notificaciones
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

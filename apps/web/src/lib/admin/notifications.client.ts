/**
 * Admin notifications — CLIENT-SAFE helpers only.
 *
 * No import from 'next/headers' or '@/lib/api/server'.
 * Safe to import from Client Components ("use client").
 */

import { getClientApiBaseUrl } from '@/lib/api-url';

import type {
  AdminNotification,
  AdminNotificationList,
  AdminNotificationSeverity,
  AdminNotificationStatus,
  AdminNotificationType,
  AdminNotificationUnreadCount,
} from './types';

const API_URL = getClientApiBaseUrl();

async function notifPost(path: string): Promise<AdminNotification> {
  const response = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error((payload as { detail?: string }).detail ?? `Request failed: ${response.status}`);
  }

  return response.json() as Promise<AdminNotification>;
}

export async function markAdminNotificationRead(id: string): Promise<AdminNotification> {
  return notifPost(`/api/v1/platform-admin/notifications/${id}/read/`);
}

export async function archiveAdminNotification(id: string): Promise<AdminNotification> {
  return notifPost(`/api/v1/platform-admin/notifications/${id}/archive/`);
}

export async function resolveAdminNotification(id: string): Promise<AdminNotification> {
  return notifPost(`/api/v1/platform-admin/notifications/${id}/resolve/`);
}

export async function fetchAdminNotificationsClient(params?: {
  status?: AdminNotificationStatus;
  severity?: AdminNotificationSeverity;
  type?: AdminNotificationType;
  page?: number;
  page_size?: number;
}): Promise<AdminNotificationList | null> {
  try {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.severity) qs.set('severity', params.severity);
    if (params?.type) qs.set('type', params.type);
    if (params?.page) qs.set('page', String(params.page));
    if (params?.page_size) qs.set('page_size', String(params.page_size));
    const query = qs.toString();
    const response = await fetch(
      `${API_URL}/api/v1/platform-admin/notifications/${query ? `?${query}` : ''}`,
      { credentials: 'include', cache: 'no-store' },
    );
    if (!response.ok) return null;
    return response.json() as Promise<AdminNotificationList>;
  } catch {
    return null;
  }
}

export async function fetchAdminUnreadCountClient(): Promise<AdminNotificationUnreadCount | null> {
  try {
    const response = await fetch(
      `${API_URL}/api/v1/platform-admin/notifications/unread-count/`,
      { credentials: 'include', cache: 'no-store' },
    );
    if (!response.ok) return null;
    return response.json() as Promise<AdminNotificationUnreadCount>;
  } catch {
    return null;
  }
}

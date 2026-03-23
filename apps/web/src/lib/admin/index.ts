import { serverApiFetch } from '@/lib/api/server';

import type { AdminSession, AdminDashboardMetrics } from './types';

/**
 * Fetch the current platform admin session (server-side only).
 * Returns null if the user is not authenticated or not platform staff.
 */
export async function getAdminSession(): Promise<AdminSession | null> {
  try {
    return await serverApiFetch<AdminSession>('/api/v1/platform-admin/me/');
  } catch {
    return null;
  }
}

/**
 * Fetch admin dashboard metrics (server-side only).
 */
export async function getAdminDashboardMetrics(): Promise<AdminDashboardMetrics | null> {
  try {
    return await serverApiFetch<AdminDashboardMetrics>('/api/v1/platform-admin/dashboard/metrics/');
  } catch {
    return null;
  }
}

export type { AdminSession, AdminDashboardMetrics };

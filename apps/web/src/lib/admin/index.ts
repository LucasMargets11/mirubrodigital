import { serverApiFetch } from '@/lib/api/server';

import type {
  AdminSession,
  AdminDashboardMetrics,
  AdminClientList,
  AdminClientDetail,
  AdminClientKPIs,
  AdminSubscriptionList,
  AdminSubscriptionDetail,
  AdminSubscriptionKPIs,
  AdminInternalNote,
  AdminTicketList,
  AdminTicketDetail,
  AdminTicketKPIs,
  AdminStaffMember,
  AdminReportingOverview,
  AdminReportingAlertsResponse,
  AdminBlogPostList,
  AdminBlogPostDetail,
  AdminBlogPostKPIs,
  AdminBlogCategory,
  AdminPromoCodeList,
  AdminPromoCodeRow,
  AdminPromoCodeRedemptionList,
  AdminPromoOptions,
  AdminPlanOption,
} from './types';

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

// ── Phase 2: Clients ─────────────────────────────────────────────────────────

export async function getAdminClients(params: Record<string, string> = {}): Promise<AdminClientList | null> {
  try {
    const qs = new URLSearchParams(params).toString();
    return await serverApiFetch<AdminClientList>(`/api/v1/platform-admin/clients/?${qs}`);
  } catch {
    return null;
  }
}

export async function getAdminClientDetail(id: number): Promise<AdminClientDetail | null> {
  try {
    return await serverApiFetch<AdminClientDetail>(`/api/v1/platform-admin/clients/${id}/`);
  } catch {
    return null;
  }
}

export async function getAdminClientKPIs(): Promise<AdminClientKPIs | null> {
  try {
    return await serverApiFetch<AdminClientKPIs>('/api/v1/platform-admin/clients/kpis/');
  } catch {
    return null;
  }
}

// ── Phase 2: Subscriptions ───────────────────────────────────────────────────

export async function getAdminSubscriptions(params: Record<string, string> = {}): Promise<AdminSubscriptionList | null> {
  try {
    const qs = new URLSearchParams(params).toString();
    return await serverApiFetch<AdminSubscriptionList>(`/api/v1/platform-admin/subscriptions/?${qs}`);
  } catch {
    return null;
  }
}

export async function getAdminSubscriptionDetail(id: string): Promise<AdminSubscriptionDetail | null> {
  try {
    return await serverApiFetch<AdminSubscriptionDetail>(`/api/v1/platform-admin/subscriptions/${id}/`);
  } catch {
    return null;
  }
}

export async function getAdminSubscriptionKPIs(): Promise<AdminSubscriptionKPIs | null> {
  try {
    return await serverApiFetch<AdminSubscriptionKPIs>('/api/v1/platform-admin/subscriptions/kpis/');
  } catch {
    return null;
  }
}

// ── Phase 2: Notes ───────────────────────────────────────────────────────────

export async function getAdminNotes(targetType: string, targetId: string): Promise<{ results: AdminInternalNote[] } | null> {
  try {
    return await serverApiFetch<{ results: AdminInternalNote[] }>(
      `/api/v1/platform-admin/notes/?target_type=${encodeURIComponent(targetType)}&target_id=${encodeURIComponent(targetId)}`
    );
  } catch {
    return null;
  }
}

// ── Phase 3: Tickets ─────────────────────────────────────────────────────────

export async function getAdminTickets(params: Record<string, string> = {}): Promise<AdminTicketList | null> {
  try {
    const qs = new URLSearchParams(params).toString();
    return await serverApiFetch<AdminTicketList>(`/api/v1/platform-admin/tickets/?${qs}`);
  } catch {
    return null;
  }
}

export async function getAdminTicketDetail(id: string): Promise<AdminTicketDetail | null> {
  try {
    return await serverApiFetch<AdminTicketDetail>(`/api/v1/platform-admin/tickets/${id}/`);
  } catch {
    return null;
  }
}

export async function getAdminTicketKPIs(): Promise<AdminTicketKPIs | null> {
  try {
    return await serverApiFetch<AdminTicketKPIs>('/api/v1/platform-admin/tickets/kpis/');
  } catch {
    return null;
  }
}

export async function getAdminStaff(): Promise<{ results: AdminStaffMember[] } | null> {
  try {
    return await serverApiFetch<{ results: AdminStaffMember[] }>('/api/v1/platform-admin/staff/');
  } catch {
    return null;
  }
}

// ── Phase 4: Reports ─────────────────────────────────────────────────────────

export async function getAdminReportingOverview(): Promise<AdminReportingOverview | null> {
  try {
    return await serverApiFetch<AdminReportingOverview>('/api/v1/platform-admin/reports/overview/');
  } catch {
    return null;
  }
}

export async function getAdminReportingAlerts(severity?: string): Promise<AdminReportingAlertsResponse | null> {
  try {
    const qs = severity ? `?severity=${encodeURIComponent(severity)}` : '';
    return await serverApiFetch<AdminReportingAlertsResponse>(`/api/v1/platform-admin/reports/alerts/${qs}`);
  } catch {
    return null;
  }
}

// ── Phase 5: Blog CMS ───────────────────────────────────────────────────────

export async function getAdminBlogPosts(params: Record<string, string> = {}): Promise<AdminBlogPostList | null> {
  try {
    const qs = new URLSearchParams(params).toString();
    return await serverApiFetch<AdminBlogPostList>(`/api/v1/platform-admin/blog/posts/?${qs}`);
  } catch {
    return null;
  }
}

export async function getAdminBlogPostDetail(id: string): Promise<AdminBlogPostDetail | null> {
  try {
    return await serverApiFetch<AdminBlogPostDetail>(`/api/v1/platform-admin/blog/posts/${encodeURIComponent(id)}/`);
  } catch {
    return null;
  }
}

export async function getAdminBlogPostKPIs(): Promise<AdminBlogPostKPIs | null> {
  try {
    return await serverApiFetch<AdminBlogPostKPIs>('/api/v1/platform-admin/blog/posts/kpis/');
  } catch {
    return null;
  }
}

export async function getAdminBlogCategories(): Promise<{ results: AdminBlogCategory[] } | null> {
  try {
    return await serverApiFetch<{ results: AdminBlogCategory[] }>('/api/v1/platform-admin/blog/categories/');
  } catch {
    return null;
  }
}

// ── Promo Codes ──────────────────────────────────────────────────

export async function getAdminPromoCodes(params: Record<string, string> = {}): Promise<AdminPromoCodeList | null> {
  try {
    const qs = new URLSearchParams(params).toString();
    return await serverApiFetch<AdminPromoCodeList>(`/api/v1/platform-admin/promo-codes/?${qs}`);
  } catch {
    return null;
  }
}

export async function getAdminPromoCodeDetail(id: number): Promise<AdminPromoCodeRow | null> {
  try {
    return await serverApiFetch<AdminPromoCodeRow>(`/api/v1/platform-admin/promo-codes/${id}/`);
  } catch {
    return null;
  }
}

export async function getAdminPromoCodeRedemptions(
  id: number,
  params: Record<string, string> = {},
): Promise<AdminPromoCodeRedemptionList | null> {
  try {
    const qs = new URLSearchParams(params).toString();
    return await serverApiFetch<AdminPromoCodeRedemptionList>(
      `/api/v1/platform-admin/promo-codes/${id}/redemptions/?${qs}`,
    );
  } catch {
    return null;
  }
}

export async function getAdminPromoOptions(): Promise<AdminPromoOptions | null> {
  try {
    return await serverApiFetch<AdminPromoOptions>('/api/v1/platform-admin/promo-codes/options/');
  } catch {
    return null;
  }
}

// ── Notifications (PR-ADMIN-10C/10D) ────────────────────────────────────────

export { getAdminNotifications, getAdminUnreadCount } from './notifications';

export type {
  AdminSession,
  AdminDashboardMetrics,
  AdminClientList,
  AdminClientDetail,
  AdminClientKPIs,
  AdminSubscriptionList,
  AdminSubscriptionDetail,
  AdminSubscriptionKPIs,
  AdminInternalNote,
  AdminTicketList,
  AdminTicketDetail,
  AdminTicketKPIs,
  AdminStaffMember,
  AdminReportingOverview,
  AdminReportingAlertsResponse,
  AdminBlogPostList,
  AdminBlogPostDetail,
  AdminBlogPostKPIs,
  AdminBlogCategory,
  AdminPromoCodeList,
  AdminPromoCodeRow,
  AdminPromoCodeRedemptionList,
  AdminPromoOptions,
  AdminPlanOption,
};

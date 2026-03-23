/**
 * Types for the internal admin panel (platform backoffice).
 * Completely separate from the tenant Session type in lib/auth/types.ts.
 */

export type AdminUser = {
  id: number;
  email: string;
  name: string;
};

export type AdminSession = {
  user: AdminUser;
  internal_role: InternalRole;
  authorized_sections: AdminSection[];
};

export type InternalRole = 'superadmin' | 'operations' | 'support_agent' | 'content_admin';

export type AdminSection =
  | 'dashboard'
  | 'clientes'
  | 'suscripciones'
  | 'soporte'
  | 'blog'
  | 'reportes'
  | 'configuracion';

export type AdminKPIs = {
  active_businesses: number;
  trial_businesses: number;
  past_due_businesses: number;
  total_users: number;
};

export type AdminAlert = {
  type: 'info' | 'warning' | 'error';
  message: string;
};

export type AdminActivityEntry = {
  id: number;
  action: string;
  actor_email: string;
  business_name: string;
  entity_type: string;
  entity_id: string;
  created_at: string | null;
};

export type AdminDashboardMetrics = {
  kpis: AdminKPIs;
  alerts: AdminAlert[];
  recent_activity: AdminActivityEntry[];
  recent_activity_count_24h: number;
};

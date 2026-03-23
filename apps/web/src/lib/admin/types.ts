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

// ── Phase 2: Clients ───────────────────────────────────────────────────────

export type AdminClientRow = {
  id: number;
  name: string;
  slug: string;
  email: string;
  status: string;
  plan: string | null;
  subscription_status: string;
  created_at: string | null;
  next_renewal: string | null;
  user_count: number;
  branch_count: number;
  risk_badges: string[];
  service_type: string;
};

export type AdminClientList = {
  results: AdminClientRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type AdminClientKPIs = {
  total_clients: number;
  active: number;
  trialing: number;
  past_due: number;
  canceled: number;
  scheduled_cancel: number;
  payment_issues_30d: number;
  plan_distribution: { plan: string; count: number }[];
};

export type AdminInternalNote = {
  id: string;
  body: string;
  author_email: string;
  author_name: string;
  created_at: string | null;
};

export type AdminPayment = {
  id: string;
  amount: string;
  currency: string;
  status: string;
  failure_reason: string;
  attempt_at: string | null;
  external_payment_id?: string;
  resolved_at?: string | null;
};

export type AdminBillingEvent = {
  id: string;
  event_type: string;
  status: string;
  received_at: string | null;
  processed_at?: string | null;
  error_message: string;
};

export type AdminAuditEntry = {
  id: number;
  action: string;
  actor_email: string;
  created_at: string | null;
  entity_type: string;
};

export type AdminMember = {
  user_id: number;
  email: string;
  name: string;
  role: string;
};

export type AdminSubscriptionSummary = {
  id: string;
  plan_code: string;
  status: string;
  admin_status: string;
  provider: string;
  provider_sub_id: string;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  cancel_requested_at: string | null;
  canceled_at: string | null;
  cancel_reason: string;
  trial_starts_at: string | null;
  trial_ends_at: string | null;
  is_active: boolean;
  created_at: string | null;
};

export type AdminBillingProfile = {
  legal_name: string;
  tax_id: string;
  vat_condition: string;
  email: string;
  phone: string;
};

export type AdminClientDetail = {
  id: number;
  name: string;
  slug: string;
  status: string;
  service_type: string;
  country: string;
  currency: string;
  created_at: string | null;
  activated_at: string | null;
  trial_starts_at: string | null;
  trial_ends_at: string | null;
  owner: AdminMember | null;
  members: AdminMember[];
  member_count: number;
  branch_count: number;
  subscription: AdminSubscriptionSummary | null;
  risk_badges: string[];
  recent_payments: AdminPayment[];
  recent_events: AdminBillingEvent[];
  recent_audit: AdminAuditEntry[];
  notes: AdminInternalNote[];
  billing_profile: AdminBillingProfile | null;
};

// ── Phase 2: Subscriptions ─────────────────────────────────────────────────

export type AdminSubscriptionRow = {
  id: string;
  business_id: number;
  business_name: string;
  plan_code: string;
  status: string;
  admin_status: string;
  provider: string;
  provider_sub_id: string;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  cancel_requested_at: string | null;
  canceled_at: string | null;
  is_active: boolean;
  retry_count: number;
  created_at: string | null;
  risk_badges: string[];
  last_event: { event_type: string; received_at: string | null } | null;
};

export type AdminSubscriptionList = {
  results: AdminSubscriptionRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type AdminSubscriptionKPIs = {
  total: number;
  active: number;
  trialing: number;
  past_due: number;
  suspended: number;
  canceled: number;
  checkout_pending: number;
  scheduled_cancel: number;
};

export type AdminWebhookError = {
  id: string;
  topic: string;
  action: string;
  processing_status: string;
  error_message: string;
  received_at: string | null;
};

export type AdminInvoiceEvent = {
  id: string;
  amount: string;
  currency: string;
  provider_status: string;
  paid_at: string | null;
  created_at: string | null;
};

export type AdminSubscriptionDetail = {
  id: string;
  business: { id: number; name: string; slug: string; status: string } | null;
  plan_code: string;
  service_type: string;
  status: string;
  admin_status: string;
  provider: string;
  provider_sub_id: string;
  external_reference: string;
  is_active: boolean;
  trial_starts_at: string | null;
  trial_ends_at: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  grace_until: string | null;
  retry_count: number;
  cancel_at_period_end: boolean;
  cancel_requested_at: string | null;
  cancel_reason: string;
  canceled_at: string | null;
  price_snapshot: Record<string, unknown> | null;
  created_at: string | null;
  updated_at: string | null;
  risk_badges: string[];
  payments: AdminPayment[];
  events: AdminBillingEvent[];
  invoice_events: AdminInvoiceEvent[];
  webhook_errors: AdminWebhookError[];
  notes: AdminInternalNote[];
};

// ── Phase 3: Support Tickets ────────────────────────────────────────────────

export type AdminTicketRow = {
  id: string;
  reference: string;
  subject: string;
  status: string;
  priority: string;
  category: string;
  business_id: number;
  business_name: string;
  assigned_to_email: string | null;
  assigned_to_name: string | null;
  contact_email: string;
  message_count: number;
  last_message_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type AdminTicketList = {
  results: AdminTicketRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type AdminTicketKPIs = {
  total: number;
  open: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  unassigned: number;
};

export type AdminTicketMessage = {
  id: string;
  body: string;
  is_system: boolean;
  author_email: string;
  author_name: string;
  created_at: string | null;
};

export type AdminTicketDetail = {
  id: string;
  reference: string;
  subject: string;
  status: string;
  priority: string;
  category: string;
  contact_email: string;
  created_at: string | null;
  updated_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  business: { id: number; name: string; slug: string; status: string } | null;
  subscription: {
    id: string;
    plan_code: string;
    status: string;
    provider: string;
    current_period_end: string | null;
  } | null;
  assigned_to: { id: number; email: string; name: string } | null;
  created_by: { id: number; email: string; name: string } | null;
  messages: AdminTicketMessage[];
  recent_payments: AdminPayment[];
  recent_billing_events: AdminBillingEvent[];
  business_notes: AdminInternalNote[];
};

export type AdminStaffMember = {
  id: number;
  email: string;
  name: string;
  role: string;
};

// ── Phase 4: Reports & Monitoring ───────────────────────────────────────────

export type AdminReportingKPIs = {
  clients: {
    total: number;
    active: number;
    trialing: number;
    past_due: number;
    suspended: number;
    canceled: number;
    onboarding: number;
  };
  subscriptions: {
    total: number;
    active: number;
    trialing: number;
    past_due: number;
    suspended: number;
    canceled: number;
    checkout_pending: number;
    scheduled_cancel: number;
  };
  tickets: {
    total: number;
    open: number;
    unassigned: number;
    by_status: Record<string, number>;
  };
  payments_30d: {
    approved: number;
    rejected: number;
    chargeback: number;
    refunded: number;
    total_attempts: number;
    revenue: string;
  };
  total_users: number;
};

export type AdminDistributionItem = {
  plan_code?: string;
  service_type?: string;
  category?: string;
  provider?: string;
  count: number;
};

export type AdminReportingDistributions = {
  plan_distribution: AdminDistributionItem[];
  service_type_distribution: AdminDistributionItem[];
  ticket_category_distribution: AdminDistributionItem[];
  provider_distribution: AdminDistributionItem[];
};

export type AdminOperationalAlert = {
  severity: 'critical' | 'warning';
  category: string;
  title: string;
  description: string;
  count: number;
  link: string;
};

export type AdminReportingOverview = {
  kpis: AdminReportingKPIs;
  distributions: AdminReportingDistributions;
  alerts: AdminOperationalAlert[];
  recent_activity: AdminActivityEntry[];
};

export type AdminReportingAlertsResponse = {
  alerts: AdminOperationalAlert[];
  total: number;
  critical_count: number;
  warning_count: number;
};

// ── Phase 5: Blog CMS ──────────────────────────────────────────────────────

export type BlogPostStatus = 'draft' | 'published' | 'scheduled' | 'archived';

export type AdminBlogPostRow = {
  id: string;
  title: string;
  slug: string;
  status: BlogPostStatus;
  category_slug: string | null;
  category_label: string | null;
  author_email: string | null;
  author_name: string | null;
  excerpt: string;
  cover_image_url: string;
  tags: string[];
  seo_complete: boolean;
  seo_missing: string[];
  created_at: string | null;
  updated_at: string | null;
  published_at: string | null;
  scheduled_publish_at: string | null;
};

export type AdminBlogPostList = {
  results: AdminBlogPostRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type AdminBlogPostKPIs = {
  total: number;
  draft: number;
  published: number;
  scheduled: number;
  archived: number;
};

export type AdminBlogPostDetail = AdminBlogPostRow & {
  body_content: unknown[];
  reading_time: string;
  source_label: string;
  meta_title: string;
  meta_description: string;
  og_title: string;
  og_description: string;
  og_image_url: string;
  canonical_url: string;
  last_editor_email: string | null;
  last_editor_name: string | null;
  publish_errors: string[];
  preview_url: string | null;
  is_publicly_visible: boolean;
};

export type AdminBlogCategory = {
  id: number;
  slug: string;
  label: string;
  post_count: number;
  created_at: string | null;
};

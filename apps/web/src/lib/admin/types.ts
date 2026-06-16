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
  | 'configuracion'
  | 'promociones'
  | 'notificaciones';

// ── Notifications (PR-ADMIN-10B/10C/10D) ──────────────────────────────────

export type AdminNotificationStatus =
  | 'unread'
  | 'read'
  | 'resolved'
  | 'archived';

export type AdminNotificationSeverity =
  | 'info'
  | 'success'
  | 'warning'
  | 'critical';

export type AdminNotificationType =
  | 'support_ticket_created'
  | 'support_ticket_urgent'
  | 'support_ticket_stale'
  | 'support_ticket_reopened'
  | 'billing_payment_failure'
  | 'billing_cancel_request'
  | 'billing_suspended'
  | 'billing_payment_ok'
  | 'review_negative'
  | 'review_spike'
  | 'security_mfa_reset'
  | 'security_role_changed'
  | 'security_login_failed'
  | 'security_staff_changed'
  | 'system_webhook_failed'
  | 'system_email_failed';

export type AdminNotification = {
  id: string;
  notif_type: AdminNotificationType;
  severity: AdminNotificationSeverity;
  title: string;
  message: string;
  status: AdminNotificationStatus;
  action_url: string;
  business_id: string | null;
  business_name: string | null;
  related_object_type: string;
  related_object_id: string;
  created_at: string | null;
  read_at: string | null;
  resolved_at: string | null;
  archived_at: string | null;
};

export type AdminNotificationList = {
  results: AdminNotification[];
  total: number;
  unread_count: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type AdminNotificationUnreadCount = {
  count: number;
  critical_count: number;
};

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

export type AdminTicketKPIsDashboard = {
  open_tickets: number;
  waiting_on_client: number;
  urgent_unassigned: number;
  new_last_7_days: number;
};

export type AdminDashboardMetrics = {
  kpis: AdminKPIs;
  ticket_kpis: AdminTicketKPIsDashboard;
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

export type AdminSupportTicketSummary = {
  id: string;
  reference: string;
  subject: string;
  status: string;
  priority: string;
  created_at: string | null;
  updated_at: string | null;
};

export type AdminSupportSummary = {
  total_tickets: number;
  open_tickets: number;
  resolved_tickets: number;
  last_ticket_at: string | null;
  last_ticket_reference: string | null;
  recent_tickets: AdminSupportTicketSummary[];
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
  support_summary: AdminSupportSummary;
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

// ── Promo Codes ────────────────────────────────────────────────────────────

export type AdminPromoCodeRow = {
  id: number;
  code: string;
  name: string;
  description: string;
  discount_type: 'percent' | 'fixed_amount';
  discount_value: string;
  duration_cycles: number;
  applies_to_plan_codes: string[];
  applies_to_service: string;
  applies_to_billing_periods: string[];
  starts_at: string | null;
  ends_at: string | null;
  max_redemptions: number | null;
  max_redemptions_per_business: number;
  active: boolean;
  redemptions_count: number;
  created_by_email: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type AdminPromoCodeList = {
  results: AdminPromoCodeRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type AdminPromoCodeRedemptionRow = {
  id: number;
  business_id: number;
  business_name: string | null;
  user_email: string | null;
  status: string;
  original_amount: string;
  discounted_amount: string;
  cycles_total: number;
  cycles_used: number;
  price_restored: boolean;
  price_restored_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type AdminPromoCodeRedemptionList = {
  results: AdminPromoCodeRedemptionRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type AdminPlanOption = {
  code: string;
  label: string;
  service: string;
  service_label: string;
  billing_period: string;
  price: string;
};

export type AdminPromoOptions = {
  services: { value: string; label: string }[];
  plans: AdminPlanOption[];
  billing_periods: { value: string; label: string }[];
  discount_types: { value: string; label: string }[];
};

// ── QR de Reseñas admin config ─────────────────────────────────────────────

export type AdminQRReviewsConfig = {
  business_id: number;
  business_name: string;
  business_slug: string;
  public_url: string;
  service_type: string;
  review_config_exists: boolean;
  enabled: boolean;
  mode: string;
  redirect_threshold: number;
  google_place_id: string;
  google_place_name: string;
  google_place_formatted_address: string;
  google_review_url: string;
  custom_redirect_url: string;
  google_place_updated_at: string | null;
};

export type AdminQRReviewsConfigPatch = {
  slug?: string;
  google_place_id?: string;
  google_place_name?: string;
  google_place_formatted_address?: string;
  google_review_url?: string;
  custom_redirect_url?: string;
};

/**
 * Admin display helpers — status badges, labels, formatters.
 * Shared across Clients and Subscriptions modules.
 */

// ── Status labels (Spanish) ─────────────────────────────────────────────────

const STATUS_LABELS: Record<string, string> = {
  onboarding: 'Onboarding',
  trialing: 'En prueba',
  active: 'Activo',
  past_due: 'Pago vencido',
  suspended: 'Suspendido',
  canceled: 'Cancelado',
  scheduled_cancel: 'Cancelación programada',
  checkout_pending: 'Checkout pendiente',
  none: 'Sin suscripción',
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

// ── Status badge colors ─────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700',
  trialing: 'bg-blue-100 text-blue-700',
  past_due: 'bg-amber-100 text-amber-700',
  suspended: 'bg-red-100 text-red-700',
  canceled: 'bg-slate-100 text-slate-500',
  scheduled_cancel: 'bg-orange-100 text-orange-700',
  checkout_pending: 'bg-violet-100 text-violet-700',
  onboarding: 'bg-sky-100 text-sky-700',
  none: 'bg-slate-100 text-slate-400',
};

export function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? 'bg-slate-100 text-slate-500';
}

// ── Risk badge labels ───────────────────────────────────────────────────────

const RISK_LABELS: Record<string, string> = {
  pago_atrasado: 'Pago atrasado',
  cancelacion_programada: 'Cancelación programada',
  suspendido: 'Suspendido',
  reintentos_cobro: 'Reintentos de cobro',
};

const RISK_COLORS: Record<string, string> = {
  pago_atrasado: 'bg-amber-100 text-amber-700',
  cancelacion_programada: 'bg-orange-100 text-orange-700',
  suspendido: 'bg-red-100 text-red-700',
  reintentos_cobro: 'bg-rose-100 text-rose-700',
};

export function riskLabel(badge: string): string {
  return RISK_LABELS[badge] ?? badge;
}

export function riskColor(badge: string): string {
  return RISK_COLORS[badge] ?? 'bg-slate-100 text-slate-500';
}

// ── Plan labels ─────────────────────────────────────────────────────────────

const PLAN_LABELS: Record<string, string> = {
  gestion_start_monthly: 'Starter (mensual)',
  gestion_pro_monthly: 'Pro (mensual)',
  gestion_business_monthly: 'Business (mensual)',
  gestion_start_yearly: 'Starter (anual)',
  gestion_pro_yearly: 'Pro (anual)',
  gestion_business_yearly: 'Business (anual)',
  start: 'Starter',
  starter: 'Starter',
  plus: 'Business',
  pro: 'Pro',
  business: 'Business',
  enterprise: 'Enterprise',
  menu_qr: 'Menú QR',
  menu_qr_visual: 'Menú QR Visual',
  menu_qr_marca: 'Menú QR Marca',
  menu_qr_lite: 'Menú QR Lite',
  menu_qr_pro: 'Menú QR Pro',
  menu_qr_premium: 'Menú QR Premium',
};

export function planLabel(planCode: string | null): string {
  if (!planCode) return '—';
  return PLAN_LABELS[planCode] ?? planCode;
}

// ── Provider labels ─────────────────────────────────────────────────────────

export function providerLabel(provider: string): string {
  const map: Record<string, string> = {
    mercadopago: 'Mercado Pago',
    stripe: 'Stripe',
    manual: 'Manual',
  };
  return map[provider] ?? provider;
}

// ── Payment status labels ───────────────────────────────────────────────────

const PAYMENT_STATUS_COLORS: Record<string, string> = {
  approved: 'bg-emerald-100 text-emerald-700',
  pending: 'bg-amber-100 text-amber-700',
  processing: 'bg-blue-100 text-blue-700',
  rejected: 'bg-red-100 text-red-700',
  refunded: 'bg-violet-100 text-violet-700',
  chargeback: 'bg-rose-100 text-rose-700',
};

export function paymentStatusColor(status: string): string {
  return PAYMENT_STATUS_COLORS[status] ?? 'bg-slate-100 text-slate-500';
}

export function paymentStatusLabel(status: string): string {
  const map: Record<string, string> = {
    approved: 'Aprobado',
    pending: 'Pendiente',
    processing: 'Procesando',
    rejected: 'Rechazado',
    refunded: 'Reembolsado',
    chargeback: 'Contracargo',
  };
  return map[status] ?? status;
}

// ── Billing event type labels ───────────────────────────────────────────────

export function eventTypeLabel(type: string): string {
  const map: Record<string, string> = {
    subscription_created: 'Suscripción creada',
    payment_approved: 'Pago aprobado',
    payment_rejected: 'Pago rechazado',
    subscription_cancelled: 'Suscripción cancelada',
    preapproval_updated: 'Preapproval actualizado',
    reconciliation_check: 'Reconciliación',
    unknown: 'Desconocido',
  };
  return map[type] ?? type;
}

// ── Ticket labels (Phase 3) ─────────────────────────────────────────────────

const TICKET_STATUS_LABELS: Record<string, string> = {
  open: 'Abierto',
  in_progress: 'En curso',
  waiting_on_client: 'Esperando cliente',
  resolved: 'Resuelto',
  closed: 'Cerrado',
};

const TICKET_STATUS_COLORS: Record<string, string> = {
  open: 'bg-blue-100 text-blue-700',
  in_progress: 'bg-amber-100 text-amber-700',
  waiting_on_client: 'bg-violet-100 text-violet-700',
  resolved: 'bg-emerald-100 text-emerald-700',
  closed: 'bg-slate-100 text-slate-500',
};

export function ticketStatusLabel(status: string): string {
  return TICKET_STATUS_LABELS[status] ?? status;
}

export function ticketStatusColor(status: string): string {
  return TICKET_STATUS_COLORS[status] ?? 'bg-slate-100 text-slate-500';
}

const TICKET_PRIORITY_LABELS: Record<string, string> = {
  low: 'Baja',
  medium: 'Media',
  high: 'Alta',
  urgent: 'Urgente',
};

const TICKET_PRIORITY_COLORS: Record<string, string> = {
  low: 'bg-slate-100 text-slate-500',
  medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-700',
  urgent: 'bg-red-100 text-red-700',
};

export function ticketPriorityLabel(priority: string): string {
  return TICKET_PRIORITY_LABELS[priority] ?? priority;
}

export function ticketPriorityColor(priority: string): string {
  return TICKET_PRIORITY_COLORS[priority] ?? 'bg-slate-100 text-slate-500';
}

const TICKET_CATEGORY_LABELS: Record<string, string> = {
  billing: 'Facturación / Pagos',
  technical: 'Problema técnico',
  account: 'Cuenta / Acceso',
  feature_request: 'Solicitud de funcionalidad',
  other: 'Otro',
};

export function ticketCategoryLabel(category: string): string {
  return TICKET_CATEGORY_LABELS[category] ?? category;
}

// ── Blog post status ────────────────────────────────────────────────────────

const BLOG_STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador',
  published: 'Publicado',
  scheduled: 'Programado',
  archived: 'Archivado',
};

export function blogStatusLabel(status: string): string {
  return BLOG_STATUS_LABELS[status] ?? status;
}

const BLOG_STATUS_COLORS: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600',
  published: 'bg-emerald-100 text-emerald-700',
  scheduled: 'bg-blue-100 text-blue-700',
  archived: 'bg-amber-100 text-amber-700',
};

export function blogStatusColor(status: string): string {
  return BLOG_STATUS_COLORS[status] ?? 'bg-slate-100 text-slate-500';
}

// ── Date formatting ─────────────────────────────────────────────────────────

/**
 * Normalise invisible Unicode whitespace that differs between Node.js ICU
 * and browser Intl (e.g. U+202F narrow no-break space before "a.\u00a0m.").
 * Prevents React hydration mismatches.
 */
function normaliseIntlSpaces(s: string): string {
  return s.replace(/[\u00a0\u202f]/g, ' ');
}

export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  return normaliseIntlSpaces(
    new Date(dateStr).toLocaleDateString('es-AR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      timeZone: 'America/Argentina/Buenos_Aires',
    }),
  );
}

export function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '—';
  return normaliseIntlSpaces(
    new Date(dateStr).toLocaleString('es-AR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'America/Argentina/Buenos_Aires',
    }),
  );
}

export function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'ahora';
  if (diffMin < 60) return `hace ${diffMin}m`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `hace ${diffHours}h`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `hace ${diffDays}d`;
  return formatDate(dateStr);
}

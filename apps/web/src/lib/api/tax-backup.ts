import { apiDelete, apiGet, apiGetBlob, apiPatch, apiPost } from './client';

// ── Types ────────────────────────────────────────────────────────────────────

export type TaxStatus =
  | 'registrado'
  | 'respaldado'
  | 'potencialmente_deducible'
  | 'a_revisar'
  | 'no_respaldado_fiscalmente';

export type AllocationType = 'business' | 'mixed' | 'personal';

export type DocumentType =
  | 'factura'
  | 'recibo'
  | 'ticket'
  | 'nota_credito'
  | 'nota_debito'
  | 'otro';

export type PaymentMethod =
  | 'cash'
  | 'transfer'
  | 'card'
  | 'mercadopago'
  | 'check'
  | 'other';

export type DuplicateStatus = 'pending' | 'confirmed_duplicate' | 'dismissed';

export type SourceType = 'expense' | 'fixed_expense_period';

export type FiscalStatus =
  | 'sin_comprobante'
  | 'incompleto'
  | 'requiere_revision'
  | 'valido_con_observaciones'
  | 'valido';

export type EvaluationSource = 'manual' | 'extracted' | 'mixed';

// ── Interfaces ───────────────────────────────────────────────────────────────

export interface FiscalProfile {
  id: number;
  expense: number | null;
  fixed_expense_period: number | null;
  source_type: SourceType;
  source_name: string;
  source_amount: string | null;
  source_due_date: string | null;
  source_period_label: string | null;
  source_status: string | null;
  allocation_type: AllocationType;
  tax_status: TaxStatus;
  tax_status_display: string;
  fiscal_status: FiscalStatus;
  fiscal_status_display: string;
  review_required: boolean;
  is_capital_asset: boolean;
  doc_count: number;
  created_at: string;
}

export interface FiscalProfileDetail {
  id: number;
  expense: number | null;
  fixed_expense_period: number | null;
  business: number;
  source_type: SourceType;
  source_name: string;
  source_amount: string | null;
  source_due_date: string | null;
  source_period_label: string | null;
  source_status: string | null;
  allocation_type: AllocationType;
  tax_status: TaxStatus;
  amount_net: string;
  amount_vat: string;
  is_capital_asset: boolean;
  review_reason: string | null;
  created_by: number | null;
  created_at: string;
  updated_at: string;
  documents: FiscalDocument[];
  payment_details: PaymentDetail[];
  status_logs: StatusLog[];
  tax_status_display: string;
  allocation_type_display: string;
  // Sprint 4 — Fiscal validation fields
  fiscal_status: FiscalStatus;
  fiscal_status_display: string;
  fiscal_status_label: string;
  review_required: boolean;
  missing_fields: string[];
  missing_fields_labels: { key: string; label: string }[];
  validation_issues: { code: string; message: string }[];
  evaluated_at: string | null;
  evaluation_source: EvaluationSource | null;
  // UX enrichment fields
  human_status_title: string;
  human_status_description: string;
  next_recommended_action: string | null;
  completion_items: CompletionItem[];
}

export interface CompletionItem {
  key: string;
  label: string;
  done: boolean;
  applicable: boolean;
  hint: string | null;
}

export interface FiscalDocument {
  id: number;
  document_type: DocumentType;
  document_subtype: string | null;
  issuer_name: string;
  issuer_tax_id: string;
  invoice_number: string;
  issue_date: string | null;
  total: string | null;
  is_fiscal_document: boolean;
  file: string;
  parse_status: 'manual' | 'pending' | 'parsed' | 'failed';
  processing_error: string | null;
  point_of_sale: string | null;
  buyer_tax_id: string | null;
  buyer_name: string | null;
  currency: string;
  created_at: string;
}

export interface PaymentDetail {
  id: number;
  payment_method: PaymentMethod;
  payment_date: string;
  amount: string;
  reference: string | null;
  proof_file: string | null;
  created_at: string;
}

export interface StatusLog {
  id: number;
  previous_status: TaxStatus;
  new_status: TaxStatus;
  rule_code: string;
  note: string;
  created_at: string;
}

export interface DuplicateFlag {
  id: number;
  fiscal_profile: number;
  matched_profile: number;
  match_type: string;
  status: DuplicateStatus;
  created_at: string;
  fiscal_profile_source_name: string;
  matched_profile_source_name: string;
}

export interface TaxBackupSummary {
  total: number;
  by_status: Partial<Record<TaxStatus, number>>;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── Query key factory ────────────────────────────────────────────────────────

export const taxBackupKeys = {
  all: ['tax-backup'] as const,
  profiles: (filters?: Record<string, string>) =>
    ['tax-backup', 'profiles', filters ?? {}] as const,
  profile: (id: number) => ['tax-backup', 'profiles', id] as const,
  summary: () => ['tax-backup', 'summary'] as const,
  duplicates: (profileId?: number) =>
    ['tax-backup', 'duplicates', profileId] as const,
};

// ── Helpers ──────────────────────────────────────────────────────────────────

const BASE = '/api/v1/tax-backup';

function toQueryString(params: Record<string, string | number | undefined>) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') qs.append(k, String(v));
  });
  return qs.toString();
}

// ── Profiles ─────────────────────────────────────────────────────────────────

export interface ProfileListParams {
  tax_status?: string;
  allocation_type?: string;
  source_type?: SourceType;
  search?: string;
  limit?: number;
  offset?: number;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Safe parse for source_amount — returns 0 when null/undefined/empty. */
export function safeAmount(raw: string | null | undefined): number {
  if (raw == null || raw === '') return 0;
  const n = parseFloat(raw);
  return Number.isFinite(n) ? n : 0;
}

export function listProfiles(params: ProfileListParams = {}) {
  const qs = toQueryString(params as Record<string, string | number | undefined>);
  return apiGet<PaginatedResponse<FiscalProfile>>(
    `${BASE}/profiles/${qs ? `?${qs}` : ''}`,
  );
}

export function getProfile(id: number) {
  return apiGet<FiscalProfileDetail>(`${BASE}/profiles/${id}/`);
}

export function createProfile(data: {
  expense?: number;
  fixed_expense_period?: number;
  allocation_type: AllocationType;
  amount_net?: string;
  amount_vat?: string;
  is_capital_asset?: boolean;
  review_reason?: string;
}) {
  return apiPost<FiscalProfileDetail>(`${BASE}/profiles/`, data);
}

export function updateProfile(
  id: number,
  data: Partial<{
    allocation_type: AllocationType;
    amount_net: string;
    amount_vat: string;
    is_capital_asset: boolean;
    review_reason: string;
  }>,
) {
  return apiPatch<FiscalProfileDetail>(`${BASE}/profiles/${id}/`, data);
}

export function getProfileSummary() {
  return apiGet<TaxBackupSummary>(`${BASE}/profiles/summary/`);
}

export function reEvaluateProfile(id: number) {
  return apiPost<{
    tax_status: string;
    tax_status_display: string;
    duplicates_found: number;
  }>(`${BASE}/profiles/${id}/re-evaluate/`, {});
}

// ── Documents ────────────────────────────────────────────────────────────────

export function listDocuments(profileId: number) {
  return apiGet<FiscalDocument[]>(
    `${BASE}/profiles/${profileId}/documents/`,
  );
}

export function uploadDocument(profileId: number, formData: FormData) {
  return apiPost<FiscalDocument>(
    `${BASE}/profiles/${profileId}/documents/`,
    formData,
  );
}

export function deleteDocument(profileId: number, docId: number) {
  return apiDelete(`${BASE}/profiles/${profileId}/documents/${docId}/`);
}

// ── Payments ─────────────────────────────────────────────────────────────────

export function listPayments(profileId: number) {
  return apiGet<PaymentDetail[]>(
    `${BASE}/profiles/${profileId}/payments/`,
  );
}

export function addPayment(profileId: number, data: FormData) {
  return apiPost<PaymentDetail>(
    `${BASE}/profiles/${profileId}/payments/`,
    data,
  );
}

// ── Status Log ───────────────────────────────────────────────────────────────

export function getStatusLog(profileId: number) {
  return apiGet<StatusLog[]>(`${BASE}/profiles/${profileId}/status-log/`);
}


// ── Duplicates ───────────────────────────────────────────────────────────────

export function listDuplicates() {
  return apiGet<PaginatedResponse<DuplicateFlag>>(`${BASE}/duplicates/`);
}

export function resolveDuplicate(
  id: number,
  status: 'confirmed_duplicate' | 'dismissed',
) {
  return apiPatch<DuplicateFlag>(`${BASE}/duplicates/${id}/`, { status });
}

// ── Monthly Report ───────────────────────────────────────────────────────────

export interface MonthlyReport {
  period: { month: number | null; year: number | null };
  profiles: {
    total: number;
    by_status: Partial<Record<TaxStatus, number>>;
    by_allocation: Partial<Record<AllocationType, number>>;
  };
  amounts: {
    total_expense: string;
    total_net: string;
    total_vat: string;
  };
  documents: {
    total: number;
    fiscal: number;
    non_fiscal: number;
  };
}

export interface ExportParams {
  month?: number;
  year?: number;
  tax_status?: TaxStatus;
}

export const taxBackupExportKeys = {
  monthlyReport: (params: ExportParams) =>
    ['tax-backup', 'monthly-report', params] as const,
};

function exportQueryString(params: ExportParams) {
  const qs = toQueryString(params as Record<string, string | number | undefined>);
  return qs ? `?${qs}` : '';
}

export function getMonthlyReport(params: ExportParams = {}) {
  return apiGet<MonthlyReport>(
    `${BASE}/profiles/monthly-report/${exportQueryString(params)}`,
  );
}

export function downloadExportCsv(params: ExportParams = {}) {
  return apiGetBlob(
    `${BASE}/profiles/export-csv/${exportQueryString(params)}`,
  );
}

export function downloadExportZip(params: ExportParams = {}) {
  return apiGetBlob(
    `${BASE}/profiles/export-zip/${exportQueryString(params)}`,
  );
}

// ── Checklist ────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  key: string;
  label: string;
  passed: boolean;
  detail: string;
  profile_ids?: number[];
}

export interface ChecklistResult {
  period: string | null;
  ready: boolean;
  score: number;
  total: number;
  items: ChecklistItem[];
}

export const taxBackupChecklistKeys = {
  checklist: (params: ExportParams) =>
    ['tax-backup', 'checklist', params] as const,
};

export function getChecklist(params: ExportParams = {}) {
  return apiGet<ChecklistResult>(
    `${BASE}/profiles/checklist/${exportQueryString(params)}`,
  );
}

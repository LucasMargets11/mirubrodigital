import { apiDelete, apiGet, apiPatch, apiPost } from './client';

export type AccountType = 'cash' | 'bank' | 'mercadopago' | 'card_float' | 'other';
export type TransactionDirection = 'IN' | 'OUT' | 'ADJUST';
export type ExpenseStatus = 'pending' | 'paid' | 'cancelled';
export type PayFrequency = 'monthly' | 'weekly';

export interface Account {
  id: number;
  name: string;
  type: AccountType;
  currency: string;
  opening_balance: string;
  balance: number;
  is_active: boolean;
  opening_balance_date?: string;
}

export interface TransactionCategory {
  id: number;
  name: string;
  direction: 'income' | 'expense';
  is_active: boolean;
}

export interface TreasuryTransaction {
  id: number;
  account_name: string;
  category_name?: string;
  created_by_name?: string;
  direction: TransactionDirection;
  amount: string;
  occurred_at: string;
  description: string;
  status: 'posted' | 'voided';
  reference_type?: string;
  reference_id?: string;
  transfer_group_id?: string;
  account: number;
  category?: number;
  transaction_type?: 'transfer' | 'expense' | 'fixed_expense' | 'payroll' | 'sale' | 'reconciliation' | 'other';
  reference_details?: any;
  related_account_name?: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ExpenseSourceDetails {
  type: 'stock_replenishment';
  id: string;
  label: string;
  supplier_name: string;
  invoice_number: string;
  occurred_at: string;
  status: string;
  route_hint: string;
}

export interface Expense {
  id: number;
  template_name?: string;
  category_name?: string;
  paid_account_name?: string;
  name: string;
  amount: string;
  due_date: string;
  status: ExpenseStatus;
  paid_at?: string;
  paid_account?: number;
  payment_transaction?: number | null;
  category?: number;
  notes?: string;
  attachment?: string;
  // Auto-generation fields
  source_type?: string | null;
  source_id?: string | null;
  is_auto_generated: boolean;
  source_details?: ExpenseSourceDetails | null;
}

export interface Employee {
  id: number;
  full_name: string;
  identifier?: string;
  pay_frequency: PayFrequency;
  base_salary: string;
  is_active: boolean;
}

export interface PayrollPayment {
  id: number;
  employee_name: string;
  account_name: string;
  amount: string;
  paid_at: string;
  transaction: number | null;
  employee: number;
  account: number;
  notes?: string;
  status?: 'paid' | 'reverted';
}

export interface FixedExpense {
  id: number;
  name: string;
  category?: number;
  category_name?: string;
  default_amount?: string;
  due_day?: number;
  frequency: 'weekly' | 'monthly' | 'quarterly' | 'yearly';
  is_active: boolean;
  current_period_status?: {
    status: string;
    amount: string;
    paid_at?: string;
    id?: number;
  };
  created_at: string;
  updated_at: string;
}

export interface FixedExpensePeriod {
  id: number;
  fixed_expense: number;
  fixed_expense_name: string;
  period: string;
  period_display: string;
  amount: string;
  status: 'pending' | 'paid' | 'skipped';
  due_date?: string;
  paid_at?: string;
  paid_account?: number;
  paid_account_name?: string;
  payment_transaction?: number;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface TreasurySettings {
  id: number;
  business: number;
  default_cash_account?: number;
  default_bank_account?: number;
  default_mercadopago_account?: number;
  default_card_account?: number;
  default_other_account?: number;
  default_income_account?: number;
  default_expense_account?: number;
  default_payroll_account?: number;
}

export interface Budget {
  id: number;
  category: number;
  category_name: string;
  year: number;
  month: number;
  limit_amount: string;
  spent: number;
  percentage: number | null;
}

export interface MonthlyReport {
  year: number;
  month: number;
  label: string;
  income: number;
  expense: number;
  result: number;
}

// Params
export interface TransactionParams {
  account?: string;
  direction?: string;
  category?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export interface PayrollParams {
  employee?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

// ─── ACCOUNTS ────────────────────────────────────────────────────────────────
export function listAccounts() {
  return apiGet<Account[]>('/api/v1/treasury/accounts/');
}

export function createAccount(data: any) {
  return apiPost<Account>('/api/v1/treasury/accounts/', data);
}

export function updateAccount(id: number, data: any) {
  return apiPatch<Account>(`/api/v1/treasury/accounts/${id}/`, data);
}

export function reconcileAccount(id: number, real_balance: number | string, occurred_at: string) {
  return apiPost<any>(`/api/v1/treasury/accounts/${id}/reconcile/`, { real_balance, occurred_at });
}

// ─── CATEGORIES ──────────────────────────────────────────────────────────────
export function listCategories() {
  return apiGet<TransactionCategory[]>('/api/v1/treasury/categories/');
}

export function createCategory(data: { name: string; direction: 'income' | 'expense' }) {
  return apiPost<TransactionCategory>('/api/v1/treasury/categories/', data);
}

// ─── TRANSACTIONS ─────────────────────────────────────────────────────────────
export function listTransactions(params: TransactionParams = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') qs.append(k, String(v));
  });
  return apiGet<PaginatedResponse<TreasuryTransaction>>(`/api/v1/treasury/transactions/?${qs.toString()}`);
}

export function createTransaction(data: {
  account: number;
  direction: TransactionDirection;
  amount: number | string;
  occurred_at: string;
  description?: string;
  category?: number;
}) {
  return apiPost<TreasuryTransaction>('/api/v1/treasury/transactions/', data);
}

export function voidTransaction(id: number, reason?: string) {
  return apiPost<TreasuryTransaction>(`/api/v1/treasury/transactions/${id}/void/`, { reason: reason ?? '' });
}

export function transferFunds(data: { from_account: number; to_account: number; amount: number | string; occurred_at: string; description?: string }) {
  return apiPost('/api/v1/treasury/transactions/transfer/', data);
}

export function getTransactionsCsvUrl(params: TransactionParams = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') qs.append(k, String(v));
  });
  return `/api/v1/treasury/transactions/export-csv/?${qs.toString()}`;
}

export function getMonthlyReport() {
  return apiGet<MonthlyReport[]>('/api/v1/treasury/transactions/monthly-report/');
}

// ─── EXPENSES ─────────────────────────────────────────────────────────────────
export function listExpenses(params: { status?: string; category?: string; date_from?: string; date_to?: string; limit?: number; offset?: number; source_type?: string; is_auto_generated?: boolean } = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') qs.append(k, String(v));
  });
  return apiGet<PaginatedResponse<Expense>>(`/api/v1/treasury/expenses/?${qs.toString()}`);
}

export function createExpense(data: any) {
  return apiPost<Expense>('/api/v1/treasury/expenses/', data);
}

export function payExpense(id: number, data: { account_id: number }) {
  return apiPost<Expense>(`/api/v1/treasury/expenses/${id}/pay/`, data);
}

// ─── EMPLOYEES ────────────────────────────────────────────────────────────────
export function listEmployees() {
  return apiGet<Employee[]>('/api/v1/treasury/employees/');
}

export function createEmployee(data: any) {
  return apiPost<Employee>('/api/v1/treasury/employees/', data);
}

export function updateEmployee(id: number, data: Partial<Employee>) {
  return apiPatch<Employee>(`/api/v1/treasury/employees/${id}/`, data);
}

export function deleteEmployee(id: number) {
  return apiDelete(`/api/v1/treasury/employees/${id}/`);
}

// ─── PAYROLL ──────────────────────────────────────────────────────────────────
export function listPayrollPayments(params: PayrollParams = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') qs.append(k, String(v));
  });
  return apiGet<PaginatedResponse<PayrollPayment>>(`/api/v1/treasury/payroll-payments/?${qs.toString()}`);
}

export function createPayrollPayment(data: any) {
  return apiPost<PayrollPayment>('/api/v1/treasury/payroll-payments/', data);
}

export function revertPayrollPayment(id: number, reason?: string) {
  return apiPost<PayrollPayment>(`/api/v1/treasury/payroll-payments/${id}/revert/`, { reason: reason ?? '' });
}

// ─── FIXED EXPENSES ───────────────────────────────────────────────────────────
export function listFixedExpenses() {
  return apiGet<FixedExpense[]>('/api/v1/treasury/fixed-expenses/');
}

export function createFixedExpense(data: { name: string; default_amount?: number; due_day?: number; frequency?: string; category?: number }) {
  return apiPost<FixedExpense>('/api/v1/treasury/fixed-expenses/', data);
}

export function updateFixedExpense(id: number, data: Partial<FixedExpense>) {
  return apiPatch<FixedExpense>(`/api/v1/treasury/fixed-expenses/${id}/`, data);
}

export function getFixedExpensePeriods(fixedExpenseId: number, params?: { from?: string; to?: string }) {
  const qs = new URLSearchParams();
  if (params?.from) qs.append('from', params.from);
  if (params?.to) qs.append('to', params.to);
  const query = qs.toString();
  return apiGet<FixedExpensePeriod[]>(`/api/v1/treasury/fixed-expenses/${fixedExpenseId}/periods/${query ? '?' + query : ''}`);
}

export function ensureCurrentPeriod(fixedExpenseId: number) {
  return apiPost<{ created: boolean; period: FixedExpensePeriod }>(`/api/v1/treasury/fixed-expenses/${fixedExpenseId}/ensure-current/`, {});
}

export function generateFixedExpensePeriods(fixedExpenseId: number, n: number) {
  return apiPost<{ created: string[]; total_requested: number }>(
    `/api/v1/treasury/fixed-expenses/${fixedExpenseId}/generate-periods/`,
    { n }
  );
}

export function ensureAllCurrentPeriods() {
  return apiPost<{ message: string; total: number }>('/api/v1/treasury/fixed-expenses/ensure-all-current/', {});
}

export function payFixedExpensePeriod(periodId: number, data: { account_id: number; paid_at?: string; amount?: number }) {
  return apiPost<FixedExpensePeriod>(`/api/v1/treasury/fixed-expense-periods/${periodId}/pay/`, data);
}

export function skipFixedExpensePeriod(periodId: number, notes?: string) {
  return apiPost<FixedExpensePeriod>(`/api/v1/treasury/fixed-expense-periods/${periodId}/skip/`, { notes: notes ?? '' });
}

// ─── TREASURY SETTINGS ────────────────────────────────────────────────────────
export function getTreasurySettings() {
  return apiGet<TreasurySettings>('/api/v1/treasury/settings/');
}

export function updateTreasurySettings(data: Partial<TreasurySettings>) {
  return apiPatch<TreasurySettings>('/api/v1/treasury/settings/update/', data);
}

// ─── BUDGETS ──────────────────────────────────────────────────────────────────
export function listBudgets(year?: number, month?: number) {
  const qs = new URLSearchParams();
  if (year) qs.append('year', String(year));
  if (month) qs.append('month', String(month));
  return apiGet<Budget[]>(`/api/v1/treasury/budgets/?${qs.toString()}`);
}

export function createBudget(data: { category: number; year: number; month: number; limit_amount: number }) {
  return apiPost<Budget>('/api/v1/treasury/budgets/', data);
}

export function updateBudget(id: number, data: { limit_amount: number }) {
  return apiPatch<Budget>(`/api/v1/treasury/budgets/${id}/`, data);
}

export function deleteBudget(id: number) {
  return apiDelete(`/api/v1/treasury/budgets/${id}/`);
}

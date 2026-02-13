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
  // Enhanced fields for better UI
  transaction_type?: 'transfer' | 'expense' | 'payroll' | 'sale' | 'reconciliation' | 'other';
  reference_details?: any;
}

export interface Expense {
  id: number;
  template_name?: string;
  category_name?: string;
  name: string;
  amount: string;
  due_date: string;
  status: ExpenseStatus;
  paid_at?: string;
  paid_account?: number;
  category?: number;
  notes?: string;
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
  transaction: number;
  employee: number;
  account: number;
}

export interface FixedExpense {
  id: number;
  name: string;
  default_amount?: string;
  due_day?: number;
  frequency: 'monthly';
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
  period: string; // YYYY-MM-DD
  period_display: string; // YYYY-MM
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

// Params
export interface TransactionParams {
  account?: string;
  direction?: string;
  category?: string;
  date_from?: string;
  date_to?: string;
  search?: string;
}

// ACCOUNTS
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

// CATEGORIES
export function listCategories() {
  return apiGet<TransactionCategory[]>('/api/v1/treasury/categories/');
}

export function createCategory(data: { name: string; direction: 'income' | 'expense' }) {
  return apiPost<TransactionCategory>('/api/v1/treasury/categories/', data);
}

// TRANSACTIONS
export function listTransactions(params: TransactionParams = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v) qs.append(k, v);
  });
  return apiGet<TreasuryTransaction[]>(`/api/v1/treasury/transactions/?${qs.toString()}`);
}

export function transferFunds(data: { from_account: number; to_account: number; amount: number; occurred_at: string; description?: string }) {
  return apiPost('/api/v1/treasury/transactions/transfer/', data);
}

// EXPENSES
export function listExpenses() {
  return apiGet<Expense[]>('/api/v1/treasury/expenses/');
}

export function createExpense(data: any) {
  return apiPost<Expense>('/api/v1/treasury/expenses/', data);
}

export function payExpense(id: number, data: { account_id: number }) {
  return apiPost<Expense>(`/api/v1/treasury/expenses/${id}/pay/`, data);
}

// EMPLOYEES
export function listEmployees() {
  return apiGet<Employee[]>('/api/v1/treasury/employees/');
}

export function createEmployee(data: any) {
  return apiPost<Employee>('/api/v1/treasury/employees/', data);
}

// PAYROLL
export function listPayrollPayments() {
  return apiGet<PayrollPayment[]>('/api/v1/treasury/payroll-payments/');
}

export function createPayrollPayment(data: any) {
  return apiPost<PayrollPayment>('/api/v1/treasury/payroll-payments/', data);
}

// FIXED EXPENSES
export function listFixedExpenses() {
  return apiGet<FixedExpense[]>('/api/v1/treasury/fixed-expenses/');
}

export function createFixedExpense(data: { name: string; default_amount?: number; due_day?: number }) {
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
  return apiPost<{ created: boolean; period: FixedExpensePeriod }>(`/api/v1/treasury/fixed-expenses/${fixedExpenseId}/ensure-current/`);
}

export function payFixedExpensePeriod(periodId: number, data: { account_id: number; paid_at?: string; amount?: number }) {
  return apiPost<FixedExpensePeriod>(`/api/v1/treasury/fixed-expense-periods/${periodId}/pay/`, data);
}

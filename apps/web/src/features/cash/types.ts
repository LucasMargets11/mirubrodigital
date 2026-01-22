import type { Sale } from '@/features/gestion/types';

export type CashRegister = {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type UserSummary = {
  id: string;
  name: string;
  email: string;
};

export type CashSessionTotals = {
  payments_total: string;
  payments_by_method: Record<string, string>;
  cash_payments_total: string;
  movements_in_total: string;
  movements_out_total: string;
  cash_expected_total: string;
  sales_count: number;
};

export type CashSession = {
  id: string;
  status: 'open' | 'closed';
  register: CashRegister | null;
  opening_cash_amount: string;
  closing_cash_counted: string | null;
  expected_cash_total: string | null;
  difference_amount: string | null;
  closing_note: string;
  opened_by: UserSummary | null;
  closed_by: UserSummary | null;
  opened_at: string;
  closed_at: string | null;
  totals: CashSessionTotals;
};

export type CashSessionResponse = {
  session: CashSession | null;
};

export type OpenCashSessionPayload = {
  register_id?: string | null;
  opening_cash_amount: number;
};

export type CloseCashSessionPayload = {
  closing_cash_counted: number;
  note?: string;
};

export type CashPaymentMethod = 'cash' | 'debit' | 'credit' | 'transfer' | 'wallet' | 'account';

export type CashPayment = {
  id: string;
  sale_id: string;
  sale_number: number;
  sale_total: string;
  session_id: string;
  method: CashPaymentMethod;
  amount: string;
  reference: string;
  created_at: string;
};

export type CashPaymentPayload = {
  sale_id: string;
  session_id?: string | null;
  method: CashPaymentMethod;
  amount: number;
  reference?: string;
};

export type CashPaymentFilters = {
  sessionId?: string;
  saleId?: string;
  dateFrom?: string;
  dateTo?: string;
};

export type CashMovementType = 'in' | 'out';
export type CashMovementCategory = 'expense' | 'withdraw' | 'deposit' | 'other';

export type CashMovement = {
  id: string;
  session: CashSession;
  movement_type: CashMovementType;
  category: CashMovementCategory;
  method: CashPaymentMethod;
  amount: string;
  note: string;
  created_by: UserSummary | null;
  created_at: string;
};

export type CashMovementPayload = {
  session_id?: string | null;
  movement_type: CashMovementType;
  category?: CashMovementCategory;
  method?: CashPaymentMethod;
  amount: number;
  note?: string;
};

export type CashMovementFilters = {
  sessionId?: string;
  movementType?: CashMovementType;
};

export type SalesWithBalance = Sale & {
  paid_total?: string;
  balance?: string;
};

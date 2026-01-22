import { apiGet, apiPost } from '@/lib/api/client';

import type {
  CashMovement,
  CashMovementFilters,
  CashMovementPayload,
  CashPayment,
  CashPaymentFilters,
  CashPaymentPayload,
  CashRegister,
  CashSession,
  CashSessionResponse,
  CloseCashSessionPayload,
  OpenCashSessionPayload,
} from './types';

function buildQuery(params: Record<string, string | undefined>) {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      searchParams.append(key, value);
    }
  });
  const serialized = searchParams.toString();
  return serialized ? `?${serialized}` : '';
}

export function getRegisters() {
  return apiGet<CashRegister[]>('/api/v1/cash/registers/');
}

export function getCurrentSession(params: { registerId?: string | null } = {}) {
  const query = buildQuery({ register_id: params.registerId ?? undefined });
  return apiGet<CashSessionResponse>(`/api/v1/cash/sessions/active/${query}`);
}

export function getCashSummary(params: { sessionId?: string } = {}) {
  const query = buildQuery({ session_id: params.sessionId });
  return apiGet<CashSessionResponse>(`/api/v1/cash/summary/${query}`);
}

export function openSession(payload: OpenCashSessionPayload) {
  return apiPost<CashSession>('/api/v1/cash/sessions/', payload);
}

export function closeSession(sessionId: string, payload: CloseCashSessionPayload) {
  return apiPost<CashSession>(`/api/v1/cash/sessions/${sessionId}/close/`, payload);
}

export function createPayment(payload: CashPaymentPayload) {
  return apiPost<CashPayment>('/api/v1/cash/payments/', payload);
}

export function listPayments(filters: CashPaymentFilters = {}) {
  const query = buildQuery({
    session_id: filters.sessionId,
    sale_id: filters.saleId,
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
  });
  return apiGet<CashPayment[]>(`/api/v1/cash/payments/${query}`);
}

export function createMovement(payload: CashMovementPayload) {
  return apiPost<CashMovement>('/api/v1/cash/movements/', payload);
}

export function listMovements(filters: CashMovementFilters = {}) {
  const query = buildQuery({
    session_id: filters.sessionId,
    movement_type: filters.movementType,
  });
  return apiGet<CashMovement[]>(`/api/v1/cash/movements/${query}`);
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  closeSession,
  createMovement,
  createPayment,
  getCashSummary,
  getCurrentSession,
  getRegisters,
  listMovements,
  listPayments,
  openSession,
} from './api';
import type {
  CashMovementFilters,
  CashMovementPayload,
  CashPaymentFilters,
  CashPaymentPayload,
  CloseCashSessionPayload,
  OpenCashSessionPayload,
} from './types';

const cashBaseKey = ['cash'] as const;
const sessionBaseKey = [...cashBaseKey, 'session'] as const;
const summaryBaseKey = [...cashBaseKey, 'summary'] as const;
const registersBaseKey = [...cashBaseKey, 'registers'] as const;
const paymentsBaseKey = [...cashBaseKey, 'payments'] as const;
const movementsBaseKey = [...cashBaseKey, 'movements'] as const;

export const cashKeys = {
  base: cashBaseKey,
  registers: registersBaseKey,
  session: (registerId?: string | null) => [...sessionBaseKey, registerId ?? 'default'] as const,
  summary: (sessionId?: string | null) => [...summaryBaseKey, sessionId ?? 'current'] as const,
  payments: (filters: CashPaymentFilters) => [...paymentsBaseKey, filters] as const,
  movements: (filters: CashMovementFilters) => [...movementsBaseKey, filters] as const,
};

function invalidateCashData(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: cashBaseKey });
  queryClient.invalidateQueries({ queryKey: ['gestion', 'sales'] });
}

export function useCashRegisters(enabled = true) {
  return useQuery({
    queryKey: registersBaseKey,
    queryFn: () => getRegisters(),
    enabled,
  });
}

export function useActiveCashSession(registerId?: string | null) {
  return useQuery({
    queryKey: cashKeys.session(registerId ?? null),
    queryFn: () => getCurrentSession({ registerId }),
    refetchInterval: 30000,
  });
}

export function useCashSummary(sessionId?: string | null) {
  return useQuery({
    queryKey: cashKeys.summary(sessionId ?? null),
    queryFn: () => getCashSummary(sessionId ? { sessionId } : {}),
    refetchInterval: 30000,
  });
}

export function useCashPayments(filters: CashPaymentFilters, enabled = true) {
  return useQuery({
    queryKey: cashKeys.payments(filters),
    queryFn: () => listPayments(filters),
    enabled,
  });
}

export function useCashMovements(filters: CashMovementFilters, enabled = true) {
  return useQuery({
    queryKey: cashKeys.movements(filters),
    queryFn: () => listMovements(filters),
    enabled,
  });
}

export function useOpenCashSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OpenCashSessionPayload) => openSession(payload),
    onSuccess: () => {
      invalidateCashData(queryClient);
    },
  });
}

export function useCloseCashSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, payload }: { sessionId: string; payload: CloseCashSessionPayload }) =>
      closeSession(sessionId, payload),
    onSuccess: () => {
      invalidateCashData(queryClient);
    },
  });
}

export function useCreateCashPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CashPaymentPayload) => createPayment(payload),
    onSuccess: () => {
      invalidateCashData(queryClient);
    },
  });
}

export function useCreateCashMovement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CashMovementPayload) => createMovement(payload),
    onSuccess: () => {
      invalidateCashData(queryClient);
    },
  });
}

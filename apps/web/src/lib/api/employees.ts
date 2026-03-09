/**
 * API client for Operative Employee (EmployeeProfile) endpoints.
 */
import { apiGet, apiPost, apiPatch } from '@/lib/api/client';
import type {
  CreateEmployeePayload,
  EmployeeProfile,
  EmployeeStatusResponse,
  ResetPinPayload,
  ResetPinResponse,
  UpdateEmployeePayload,
} from '@/types/employees';

const BASE = '/api/v1/owner/access/employees';

export const employeesApi = {
  /** List all operative employees in the business. */
  list: () => apiGet<EmployeeProfile[]>(`${BASE}/`),

  /** Get a single employee by ID. */
  get: (id: string) => apiGet<EmployeeProfile>(`${BASE}/${id}/`),

  /**
   * Create a new operative employee.
   * Response includes `initial_pin` (shown once, never returned again).
   */
  create: (payload: CreateEmployeePayload) =>
    apiPost<EmployeeProfile>(`${BASE}/`, payload),

  /** Update employee profile fields (PATCH). */
  update: (id: string, payload: UpdateEmployeePayload) =>
    apiPatch<EmployeeProfile>(`${BASE}/${id}/`, payload),

  /**
   * Reset employee PIN.
   * If `new_pin` is not supplied, a random PIN is generated server-side.
   * Response includes `temporary_pin` (shown once).
   */
  resetPin: (id: string, payload: ResetPinPayload = {}) =>
    apiPost<ResetPinResponse>(`${BASE}/${id}/reset-pin/`, payload),

  /** Suspend an employee (blocks operative login). */
  suspend: (id: string) =>
    apiPost<EmployeeStatusResponse>(`${BASE}/${id}/suspend/`, {}),

  /** Reactivate a suspended employee. */
  reactivate: (id: string) =>
    apiPost<EmployeeStatusResponse>(`${BASE}/${id}/reactivate/`, {}),
};

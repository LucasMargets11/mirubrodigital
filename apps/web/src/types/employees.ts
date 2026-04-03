/**
 * TypeScript types for the Operative Employee (EmployeeProfile) module.
 */

export type EmployeeRoleType =
  | 'cashier'
  | 'server'
  | 'kitchen'
  | 'delivery'
  | 'manager_op';

export type EmployeeStatus = 'active' | 'inactive' | 'suspended';

export type EmployeeCredentialType = 'pin' | 'qr_code' | 'nfc_tag';

export interface EmployeeProfile {
  id: string;
  first_name: string;
  last_name: string;
  alias: string;
  employee_code: string;
  role_type: EmployeeRoleType;
  role_type_display: string;
  credential_type: EmployeeCredentialType;
  credential_type_display: string;
  must_change_pin: boolean;
  status: EmployeeStatus;
  status_display: string;
  branch: number | null;
  branch_name: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
  /** Returned only on create — never stored server-side after creation. */
  initial_pin?: string;
  pin_was_generated?: boolean;
  /** Business slug — used for POS login. */
  business_code?: string;
}

export interface CreateEmployeePayload {
  first_name: string;
  last_name: string;
  alias?: string;
  role_type: EmployeeRoleType;
  credential_type?: EmployeeCredentialType;
  employee_code?: string;
  initial_pin?: string;
  branch?: number | null;
}

export interface UpdateEmployeePayload {
  first_name?: string;
  last_name?: string;
  alias?: string;
  role_type?: EmployeeRoleType;
  credential_type?: EmployeeCredentialType;
  branch?: number | null;
}

export interface ResetPinPayload {
  new_pin?: string;
}

export interface ResetPinResponse {
  success: boolean;
  message: string;
  employee_code: string;
  temporary_pin: string;
  must_change_pin: true;
  pin_was_generated: boolean;
}

export interface EmployeeStatusResponse {
  success: boolean;
  message: string;
  id: string;
  status: EmployeeStatus;
  status_display: string;
}

export const ROLE_TYPE_LABELS: Record<EmployeeRoleType, string> = {
  cashier:    'Cajero',
  server:     'Mozo / Salón',
  kitchen:    'Cocina',
  delivery:   'Delivery',
  manager_op: 'Encargado Operativo',
};

export const STATUS_LABELS: Record<EmployeeStatus, string> = {
  active:    'Activo',
  inactive:  'Inactivo',
  suspended: 'Suspendido',
};

// ── Operative POS types (X-Employee-Token flows) ──────────────────────────────

/**
 * Response from POST /api/v1/auth/employee-login/
 * Token must be stored client-side and sent as X-Employee-Token header.
 */
export interface EmployeeLoginResponse {
  token: string;
  actor_type: 'employee';
  employee_id: string;
  employee_code: string;
  display_name: string;
  business_id: number;
  business_name: string;
  role_type: EmployeeRoleType;
  must_change_pin: boolean;
  /** Sparse dict — only granted permissions are included (value always true). */
  permissions: Record<string, true>;
}

/**
 * Response from GET /api/v1/pos/me/
 * Refreshable identity without re-login.
 */
export interface EmployeeMe {
  id: string;
  employee_code: string;
  display_name: string;
  full_name: string;
  role_type: EmployeeRoleType;
  branch: number | null;
  branch_name: string | null;
  status: EmployeeStatus;
  must_change_pin: boolean;
  business_id: number;
  business_name: string;
}

/** POS capability keys returned by GET /api/v1/pos/capabilities/ */
export interface PosCapabilitySet {
  can_open_pos: boolean;
  can_view_assigned_branch: boolean;
  can_create_sale: boolean;
  can_refund_sale: boolean;
  can_manage_cash: boolean;
  can_view_reports: boolean;
  can_manage_employees_pos: boolean;
  // Cash session granular capabilities (cashier + manager_op only)
  can_open_cash: boolean;
  can_close_cash: boolean;
  can_register_cash_movement: boolean;
}

/**
 * Response from GET /api/v1/pos/capabilities/
 */
export interface EmployeeCapabilities {
  role_type: EmployeeRoleType;
  service: string;
  /** Sparse dict — only granted permissions (value always true). */
  permissions: Record<string, true>;
  /** Complete dict — all capability keys with explicit true/false. */
  capabilities: PosCapabilitySet;
}

/**
 * Response from GET /api/v1/pos/health/
 */
export interface PosHealthResponse {
  status: 'ok';
  employee_code: string;
  business_id: number;
  must_change_pin: boolean;
}

/** Request body for POST /api/v1/auth/employee-change-pin/ */
export interface ChangePinRequest {
  current_pin: string;
  new_pin: string;
  confirm_new_pin: string;
}

/** Success response from POST /api/v1/auth/employee-change-pin/ */
export interface ChangePinResponse {
  success: true;
  must_change_pin: false;
}

/**
 * Generic POS API error payload.
 * Backend sends { error, code? } for operative errors.
 */
export interface PosApiErrorPayload {
  error?: string;
  code?: 'pin_change_required' | 'bad_current_pin' | string;
  detail?: string;
}

/** Request body for POST /api/v1/auth/employee-login/ */
export interface EmployeeLoginRequest {
  business_code: string;
  employee_code: string;
  pin: string;
}


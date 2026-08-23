'use client';

import { getClientApiBaseUrl } from '../api-url';
import type {
  AdminClientProvisioningOptions,
  AdminClientProvisioningInput,
  AdminClientProvisioningResult,
  AdminClientProvisioningError,
} from './types';

const API_URL = getClientApiBaseUrl();

export type AdminLoginResult =
  | { status: 'ok'; mfa_required: false; mfa_enrolled: boolean }
  | { status: 'mfa_required'; mfa_required: true; mfa_token: string }
  | { status: 'error'; message: string; retry_after?: number };

export type AdminMFAResult =
  | { status: 'ok'; recovery_codes_remaining?: number }
  | { status: 'error'; message: string; retry_after?: number };

export type AdminMFAEnrollResult =
  | { status: 'ok'; secret: string; provisioning_uri: string; recovery_codes: string[] }
  | { status: 'error'; message: string };

async function request(path: string, body?: Record<string, unknown>): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  });
}

export async function adminLogin(email: string, password: string): Promise<AdminLoginResult> {
  try {
    const response = await request('/api/v1/platform-admin/auth/login/', { email, password });

    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After');
      return {
        status: 'error',
        message: 'Demasiados intentos. Esperá un momento antes de reintentar.',
        retry_after: retryAfter ? parseInt(retryAfter, 10) : undefined,
      };
    }

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      return {
        status: 'error',
        message: data?.detail ?? 'Credenciales inválidas o acceso temporalmente restringido.',
      };
    }

    if (data.mfa_required) {
      return {
        status: 'mfa_required',
        mfa_required: true,
        mfa_token: data.mfa_token,
      };
    }

    return {
      status: 'ok',
      mfa_required: false,
      mfa_enrolled: data.mfa_enrolled ?? false,
    };
  } catch {
    return { status: 'error', message: 'Error de red al iniciar sesión.' };
  }
}

export async function adminMFAVerify(mfaToken: string, otpCode: string): Promise<AdminMFAResult> {
  try {
    const response = await request('/api/v1/platform-admin/auth/mfa-verify/', {
      mfa_token: mfaToken,
      otp_code: otpCode,
    });

    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After');
      return {
        status: 'error',
        message: 'Demasiados intentos de verificación.',
        retry_after: retryAfter ? parseInt(retryAfter, 10) : undefined,
      };
    }

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      return { status: 'error', message: data?.detail ?? 'Código incorrecto.' };
    }

    return { status: 'ok' };
  } catch {
    return { status: 'error', message: 'Error de red.' };
  }
}

export async function adminMFARecovery(mfaToken: string, recoveryCode: string): Promise<AdminMFAResult> {
  try {
    const response = await request('/api/v1/platform-admin/auth/mfa-recovery/', {
      mfa_token: mfaToken,
      recovery_code: recoveryCode,
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      return { status: 'error', message: data?.detail ?? 'Código de recuperación inválido.' };
    }

    return { status: 'ok', recovery_codes_remaining: data.recovery_codes_remaining };
  } catch {
    return { status: 'error', message: 'Error de red.' };
  }
}

export async function adminMFAEnroll(): Promise<AdminMFAEnrollResult> {
  try {
    const response = await request('/api/v1/platform-admin/auth/mfa-enroll/');
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      return { status: 'error', message: data?.detail ?? 'Error al iniciar enrollment MFA.' };
    }

    return {
      status: 'ok',
      secret: data.secret,
      provisioning_uri: data.provisioning_uri,
      recovery_codes: data.recovery_codes,
    };
  } catch {
    return { status: 'error', message: 'Error de red.' };
  }
}

export async function adminMFAConfirm(otpCode: string): Promise<AdminMFAResult> {
  try {
    const response = await request('/api/v1/platform-admin/auth/mfa-confirm/', {
      otp_code: otpCode,
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      return { status: 'error', message: data?.detail ?? 'Código OTP incorrecto.' };
    }

    return { status: 'ok' };
  } catch {
    return { status: 'error', message: 'Error de red.' };
  }
}

export async function adminLogout(): Promise<void> {
  try {
    await request('/api/v1/platform-admin/auth/logout/');
  } finally {
    window.location.assign('/admin/login');
  }
}

// ── ADMIN-CLIENTES 03C: Client provisioning (client-safe, browser fetch) ──

export type AdminClientProvisioningOptionsResult =
  | { status: 'ok'; data: AdminClientProvisioningOptions }
  | { status: 'session_expired' }
  | { status: 'error'; message: string };

/**
 * GET /api/v1/platform-admin/clients/provisioning-options/
 * Used by the "Nuevo cliente" form to load services/plans, with retry.
 */
export async function getAdminClientProvisioningOptions(): Promise<AdminClientProvisioningOptionsResult> {
  try {
    const response = await fetch(`${API_URL}/api/v1/platform-admin/clients/provisioning-options/`, {
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
    });

    if (response.status === 401) {
      return { status: 'session_expired' };
    }

    if (!response.ok) {
      return { status: 'error', message: 'No pudimos cargar los servicios y planes disponibles.' };
    }

    const data = (await response.json()) as AdminClientProvisioningOptions;
    return { status: 'ok', data };
  } catch {
    return { status: 'error', message: 'Error de red al cargar las opciones de alta.' };
  }
}

export type AdminClientProvisioningResponse =
  | { status: 'ok'; data: AdminClientProvisioningResult }
  | { status: 'session_expired' }
  | { status: 'forbidden' }
  | {
      status: 'domain_error';
      httpStatus: number;
      error: AdminClientProvisioningError;
    }
  | {
      status: 'field_errors';
      httpStatus: number;
      fieldErrors: Record<string, string>;
    }
  | { status: 'server_error'; httpStatus: number };

/**
 * POST /api/v1/platform-admin/clients/ — sends exactly the ten allowed
 * provisioning fields. Distinguishes DRF structural 400s (field -> [msgs])
 * from the domain error envelope ({code, detail, field}) so the caller can
 * map either shape onto the right form control.
 */
export async function provisionAdminClient(
  input: AdminClientProvisioningInput,
): Promise<AdminClientProvisioningResponse> {
  const payload: AdminClientProvisioningInput = {
    business_name: input.business_name,
    business_slug: input.business_slug,
    service_type: input.service_type,
    country: input.country,
    currency: input.currency,
    owner_email: input.owner_email,
    plan_code: input.plan_code,
    complimentary_start: input.complimentary_start,
    complimentary_end: input.complimentary_end,
    grant_reason: input.grant_reason,
  };

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1/platform-admin/clients/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    return { status: 'server_error', httpStatus: 0 };
  }

  if (response.status === 201) {
    // Includes the 04E access-delivery fields. In particular, login_url is
    // consumed verbatim by the confirmation UI and is never rebuilt here.
    const data = (await response.json()) as AdminClientProvisioningResult;
    return { status: 'ok', data };
  }

  if (response.status === 401) {
    return { status: 'session_expired' };
  }

  if (response.status === 403) {
    return { status: 'forbidden' };
  }

  const data = await response.json().catch(() => ({}));

  // Domain envelope: {code, detail, field}.
  if (data && typeof data === 'object' && 'code' in data && 'detail' in data) {
    return {
      status: 'domain_error',
      httpStatus: response.status,
      error: data as AdminClientProvisioningError,
    };
  }

  // DRF structural validation errors: { field: [msg, ...] }.
  if (data && typeof data === 'object') {
    const fieldErrors: Record<string, string> = {};
    for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
      fieldErrors[key] = Array.isArray(value) ? value.join(' ') : String(value);
    }
    if (Object.keys(fieldErrors).length > 0) {
      return { status: 'field_errors', httpStatus: response.status, fieldErrors };
    }
  }

  return { status: 'server_error', httpStatus: response.status };
}

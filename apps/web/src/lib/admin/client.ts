'use client';

import { getClientApiBaseUrl } from '../api-url';

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

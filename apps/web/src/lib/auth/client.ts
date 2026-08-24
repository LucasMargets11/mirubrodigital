'use client';

import { getClientApiBaseUrl } from '../api-url';

const API_URL = getClientApiBaseUrl();

type AuthResult = {
  success: boolean;
  message?: string;
};

async function request<T>(path: string, body?: T): Promise<Response> {
  const url = `${API_URL}${path}`;
  console.log(`[Auth] Requesting ${url} (POST)`);
  return fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  });
}

export async function login(identifier: string, password: string, nextUrl?: string): Promise<AuthResult> {
  try {
    // Send identifier as both email and username fields for backward compatibility.
    // Backend accepts either field and resolves the user accordingly.
    const body: Record<string, string> = { password };
    if (identifier.includes('@')) {
      body.email = identifier;
    } else {
      body.username = identifier;
    }

    const response = await request('/api/v1/auth/login/', body);
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      return { success: false, message: errorPayload?.detail ?? 'No pudimos iniciar sesión' };
    }

    const data = await response.json().catch(() => ({}));

    // If the business is in onboarding state, send the user to the smart
    // onboarding index (/app/onboarding) which determines the correct step
    // server-side and redirects accordingly.  This provides resume semantics
    // for users who partially completed onboarding in a previous session.
    // When `nextUrl` is provided (e.g. coming from /subscribe with plan params),
    // use it as the onboarding destination so the plan context is preserved.
    if (data?.onboarding) {
      window.location.assign(nextUrl ?? '/app/onboarding');
    } else {
      window.location.assign('/app/dashboard');
    }

    return { success: true };
  } catch {
    return { success: false, message: 'Error de red al iniciar sesión' };
  }
}

export async function register(email: string, password: string): Promise<AuthResult> {
  try {
    const response = await request('/api/v1/auth/register/', { email, password });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      return { success: false, message: errorPayload?.detail ?? 'No pudimos crear la cuenta' };
    }
    return { success: true };
  } catch {
    return { success: false, message: 'Error de red al crear la cuenta' };
  }
}

export async function logout(): Promise<void> {
  try {
    await request('/api/v1/auth/logout/');
  } finally {
    window.location.assign('/entrar');
  }
}

export async function forgotPassword(email: string): Promise<AuthResult> {
  try {
    const response = await request('/api/v1/auth/forgot-password/', { email });
    if (!response.ok) {
      return { success: false, message: 'No pudimos procesar tu solicitud' };
    }
    return { success: true };
  } catch {
    return { success: false, message: 'Error de red' };
  }
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<AuthResult> {
  try {
    const response = await request('/api/v1/auth/reset-password/', {
      token,
      new_password: newPassword,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      return { success: false, message: payload?.detail ?? 'No pudimos restablecer tu contraseña' };
    }
    return { success: true };
  } catch {
    return { success: false, message: 'Error de red' };
  }
}

export async function verifyEmail(token: string): Promise<AuthResult> {
  try {
    const response = await request('/api/v1/auth/verify-email/', { token });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      return { success: false, message: payload?.detail ?? 'Token inválido o expirado' };
    }
    return { success: true };
  } catch {
    return { success: false, message: 'Error de red' };
  }
}

export async function resendVerification(): Promise<AuthResult> {
  try {
    const response = await request('/api/v1/auth/resend-verification/');
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      return { success: false, message: payload?.detail ?? 'No pudimos enviar el email' };
    }
    return { success: true };
  } catch {
    return { success: false, message: 'Error de red' };
  }
}

// ── Google OAuth ────────────────────────────────────────────────────────────

export type GoogleAuthResult = AuthResult & {
  onboarding?: boolean;
  code?: string;
};

const GOOGLE_ACCOUNT_NOT_AUTHORIZED_MESSAGE =
  'Esta cuenta de Google no tiene un acceso habilitado. Verificá que estés usando el correo registrado por el administrador.';

export async function googleAuth(credential: string): Promise<GoogleAuthResult> {
  try {
    const response = await request('/api/v1/auth/google/', { credential });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      return { success: false, message: payload?.detail ?? 'No pudimos autenticar con Google' };
    }
    const data = await response.json().catch(() => ({}));
    return {
      success: true,
      onboarding: data?.onboarding ?? false,
    };
  } catch {
    return { success: false, message: 'Error de red al autenticar con Google' };
  }
}

const GOOGLE_BUSINESS_REQUIRED_MESSAGE =
  'Usá el enlace de acceso específico de tu comercio para ingresar.';

export async function googlePreauthorizedLogin(
  credential: string,
  businessId?: number | null,
): Promise<GoogleAuthResult> {
  try {
    const body: { credential: string; business_id?: number } = { credential };
    if (typeof businessId === 'number' && Number.isInteger(businessId) && businessId > 0) {
      body.business_id = businessId;
    }
    const response = await request('/api/v1/auth/google/preauthorized/', body);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      if (response.status === 401 && payload?.code === 'google_account_not_authorized') {
        return {
          success: false,
          code: payload.code,
          message: GOOGLE_ACCOUNT_NOT_AUTHORIZED_MESSAGE,
        };
      }
      if (
        response.status === 400 &&
        payload?.code === 'google_preauthorized_business_required'
      ) {
        return {
          success: false,
          code: payload.code,
          message: GOOGLE_BUSINESS_REQUIRED_MESSAGE,
        };
      }
      return {
        success: false,
        code: payload?.code,
        message: payload?.detail ?? 'No pudimos autenticar con Google',
      };
    }
    const data = await response.json().catch(() => ({}));
    return {
      success: true,
      onboarding: data?.onboarding ?? false,
    };
  } catch {
    return { success: false, message: 'Error de red al autenticar con Google' };
  }
}

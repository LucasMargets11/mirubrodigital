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

export async function login(email: string, password: string): Promise<AuthResult> {
  try {
    const response = await request('/api/v1/auth/login/', { email, password });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      return { success: false, message: errorPayload?.detail ?? 'No pudimos iniciar sesión' };
    }
    window.location.assign('/app/dashboard');
    return { success: true };
  } catch (error) {
    return { success: false, message: 'Error de red al iniciar sesión' };
  }
}

export async function logout(): Promise<void> {
  try {
    await request('/api/v1/auth/logout/');
  } finally {
    window.location.assign('/entrar');
  }
}

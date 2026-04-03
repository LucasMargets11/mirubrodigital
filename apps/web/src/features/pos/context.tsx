'use client';

/**
 * Operative employee session context.
 *
 * Architecture notes:
 * - Token stored in sessionStorage (tab-isolated, not persisted to disk).
 * - On mount, reads token from sessionStorage and rehydrates employee state
 *   via GET /pos/me/.
 * - must_change_pin guard is evaluated in context: any navigation hook or
 *   layout can read it and force redirect to /pos/change-pin.
 * - Owner/admin cookie auth is never touched here.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { ApiError } from '@/lib/api/client';
import {
  employeeLogin,
  posGetMe,
} from '@/lib/api/pos';
import type {
  EmployeeLoginRequest,
  EmployeeMe,
} from '@/types/employees';

// ── Storage key ───────────────────────────────────────────────────────────────

const TOKEN_KEY = 'pos_employee_token';

function readStoredToken(): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem(TOKEN_KEY);
}

function persistToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

// ── Context types ─────────────────────────────────────────────────────────────

export type EmployeeSessionState =
  | { status: 'loading' }
  | { status: 'unauthenticated' }
  | {
      status: 'authenticated';
      token: string;
      employee: EmployeeMe;
      mustChangePin: boolean;
    }
  | { status: 'error'; message: string };

interface EmployeeSessionContextValue {
  session: EmployeeSessionState;
  /** Authenticate with business credentials + PIN. */
  login: (payload: EmployeeLoginRequest) => Promise<void>;
  /** Clear session token and reset state. */
  logout: () => void;
  /** Re-fetch /pos/me/ with current token and refresh state. */
  refreshMe: () => Promise<void>;
}

// ── Context ───────────────────────────────────────────────────────────────────

export const EmployeeSessionContext =
  createContext<EmployeeSessionContextValue | null>(null);

// ── Provider ──────────────────────────────────────────────────────────────────

export function EmployeeSessionProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [session, setSession] = useState<EmployeeSessionState>({
    status: 'loading',
  });

  // ── Hydrate from storage on mount ──────────────────────────────────────────

  const hydrateFromToken = useCallback(async (token: string) => {
    try {
      const employee = await posGetMe(token);
      setSession({
        status: 'authenticated',
        token,
        employee,
        mustChangePin: employee.must_change_pin,
      });
    } catch (err) {
      clearToken();
      if (err instanceof ApiError && err.status === 401) {
        setSession({ status: 'unauthenticated' });
      } else {
        const message =
          err instanceof Error ? err.message : 'Error de conexión';
        setSession({ status: 'error', message });
      }
    }
  }, []);

  useEffect(() => {
    const stored = readStoredToken();
    if (stored) {
      hydrateFromToken(stored);
    } else {
      setSession({ status: 'unauthenticated' });
    }
  }, [hydrateFromToken]);

  // ── Actions ────────────────────────────────────────────────────────────────

  const login = useCallback(
    async (payload: EmployeeLoginRequest) => {
      setSession({ status: 'loading' });
      try {
        const resp = await employeeLogin(payload);
        persistToken(resp.token);
        await hydrateFromToken(resp.token);
      } catch (err) {
        setSession({ status: 'unauthenticated' });
        throw err;
      }
    },
    [hydrateFromToken],
  );

  const logout = useCallback(() => {
    clearToken();
    setSession({ status: 'unauthenticated' });
  }, []);

  const refreshMe = useCallback(async () => {
    const stored = readStoredToken();
    if (!stored) {
      setSession({ status: 'unauthenticated' });
      return;
    }
    await hydrateFromToken(stored);
  }, [hydrateFromToken]);

  const value = useMemo<EmployeeSessionContextValue>(
    () => ({ session, login, logout, refreshMe }),
    [session, login, logout, refreshMe],
  );

  return (
    <EmployeeSessionContext.Provider value={value}>
      {children}
    </EmployeeSessionContext.Provider>
  );
}

// ── Consumer hook ─────────────────────────────────────────────────────────────

export function useEmployeeSession(): EmployeeSessionContextValue {
  const ctx = useContext(EmployeeSessionContext);
  if (!ctx) {
    throw new Error(
      'useEmployeeSession must be used inside <EmployeeSessionProvider>',
    );
  }
  return ctx;
}

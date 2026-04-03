/**
 * Frontend tests for the POS operative module.
 *
 * Coverage:
 * 1. POS API client — error helpers (isPosAuthError, isPinChangeRequired)
 * 2. EmployeeSessionContext — login, logout, mustChangePin flag
 * 3. POS type contract — EmployeeLoginResponse, PosCapabilitySet
 * 4. Login page — form submission, 401/429 error messages
 * 5. (removed — change-pin page disabled)
 * 6. Cash POS API — posGetCurrentCashSession, posOpenCashSession, posCloseCurrentCashSession, posCreateCashMovement
 * 7. usePosCashCurrentSession — session data, null session, 401 rejection
 */

import React from 'react';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api/client';
import {
  isPinChangeRequired,
  isPosAuthError,
  posGetCurrentCashSession,
  posOpenCashSession,
  posCloseCurrentCashSession,
  posCreateCashMovement,
  posCreateSale,
  posGetProducts,
} from '@/lib/api/pos';
import {
  EmployeeSessionProvider,
  useEmployeeSession,
} from '@/features/pos/context';
import { usePosCashCurrentSession, usePosCreateSale } from '@/features/pos/cash-hooks';
import type {
  EmployeeLoginResponse,
  EmployeeMe,
  PosCapabilitySet,
} from '@/types/employees';
import type { PosCashSession, PosProduct } from '@/types/pos-cash';

// ── Helpers & fixtures ────────────────────────────────────────────────────────

function makeEmployee(overrides: Partial<EmployeeMe> = {}): EmployeeMe {
  return {
    id: 'uuid-test-1',
    employee_code: 'EMP-001',
    display_name: 'Ana López',
    full_name: 'Ana María López',
    role_type: 'cashier',
    branch: 1,
    branch_name: 'Sucursal Centro',
    status: 'active',
    must_change_pin: false,
    business_id: 5,
    business_name: 'Café Aurora',
    ...overrides,
  };
}

function makeLoginResponse(overrides: Partial<EmployeeLoginResponse> = {}): EmployeeLoginResponse {
  return {
    token: 'test-jwt-token',
    actor_type: 'employee',
    employee_id: 'uuid-test-1',
    employee_code: 'EMP-001',
    display_name: 'Ana López',
    business_id: 5,
    business_name: 'Café Aurora',
    role_type: 'cashier',
    must_change_pin: false,
    permissions: {},
    ...overrides,
  };
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <EmployeeSessionProvider>{children}</EmployeeSessionProvider>
    </QueryClientProvider>
  );
}

// ── 1. Error helper functions ─────────────────────────────────────────────────

describe('POS error helpers', () => {
  it('isPosAuthError returns true for 401', () => {
    expect(isPosAuthError(new ApiError('unauth', 401))).toBe(true);
  });

  it('isPosAuthError returns true for 403', () => {
    expect(isPosAuthError(new ApiError('forbidden', 403))).toBe(true);
  });

  it('isPosAuthError returns false for non-ApiError', () => {
    expect(isPosAuthError(new Error('generic'))).toBe(false);
  });

  it('isPosAuthError returns false for 500', () => {
    expect(isPosAuthError(new ApiError('server', 500))).toBe(false);
  });

  it('isPinChangeRequired returns true for 403 + pin_change_required code', () => {
    const err = new ApiError('forbidden', 403, { code: 'pin_change_required' });
    expect(isPinChangeRequired(err)).toBe(true);
  });

  it('isPinChangeRequired returns false for 403 without code', () => {
    expect(isPinChangeRequired(new ApiError('forbidden', 403))).toBe(false);
  });

  it('isPinChangeRequired returns false for non-403 with code', () => {
    const err = new ApiError('bad', 400, { code: 'pin_change_required' });
    expect(isPinChangeRequired(err)).toBe(false);
  });
});

// ── 2. EmployeeSessionContext ─────────────────────────────────────────────────

describe('EmployeeSessionContext', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('starts as loading then transitions to unauthenticated when no stored token', async () => {
    function Inspector() {
      const { session } = useEmployeeSession();
      return <div data-testid="status">{session.status}</div>;
    }

    render(<Inspector />, { wrapper: Wrapper });

    // jsdom flushes effects synchronously in tests, so the initial 'loading'
    // state may already have resolved. We only assert the final stable state.
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('unauthenticated');
    });
  });

  it('restores session from sessionStorage on mount', async () => {
    const employee = makeEmployee();
    sessionStorage.setItem('pos_employee_token', 'stored-token');

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(employee), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    function Inspector() {
      const { session } = useEmployeeSession();
      if (session.status !== 'authenticated') return <div data-testid="status">{session.status}</div>;
      return <div data-testid="name">{session.employee.display_name}</div>;
    }

    render(<Inspector />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('name').textContent).toBe('Ana López');
    });
  });

  it('clears stored token and goes unauthenticated on 401 from /pos/me/', async () => {
    sessionStorage.setItem('pos_employee_token', 'expired-token');

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'Invalid token' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    function Inspector() {
      const { session } = useEmployeeSession();
      return <div data-testid="status">{session.status}</div>;
    }

    render(<Inspector />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('unauthenticated');
    });
    expect(sessionStorage.getItem('pos_employee_token')).toBeNull();
  });

  it('login() stores token and authenticates', async () => {
    const loginResp = makeLoginResponse();
    const employee = makeEmployee();

    const fetchSpy = vi
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        // employeeLogin call
        new Response(JSON.stringify(loginResp), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        // posGetMe hydration call
        new Response(JSON.stringify(employee), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

    function Inspector() {
      const { session, login } = useEmployeeSession();
      return (
        <>
          <div data-testid="status">{session.status}</div>
          <button onClick={() => login({ business_code: 'cafe-aurora', employee_code: 'EMP-001', pin: '1234' })}>
            Login
          </button>
        </>
      );
    }

    render(<Inspector />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('unauthenticated'));

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Login' }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('authenticated');
    });

    expect(sessionStorage.getItem('pos_employee_token')).toBe('test-jwt-token');
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it('logout() clears token and resets state', async () => {
    const employee = makeEmployee();
    sessionStorage.setItem('pos_employee_token', 'valid-token');

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(employee), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    function Inspector() {
      const { session, logout } = useEmployeeSession();
      return (
        <>
          <div data-testid="status">{session.status}</div>
          <button onClick={logout}>Logout</button>
        </>
      );
    }

    render(<Inspector />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('authenticated'));

    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Logout' }));
    });

    expect(screen.getByTestId('status').textContent).toBe('unauthenticated');
    expect(sessionStorage.getItem('pos_employee_token')).toBeNull();
  });

  it('mustChangePin is true when employee.must_change_pin=true', async () => {
    const employee = makeEmployee({ must_change_pin: true });
    sessionStorage.setItem('pos_employee_token', 'valid-token');

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(employee), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    function Inspector() {
      const { session } = useEmployeeSession();
      if (session.status !== 'authenticated') return null;
      return <div data-testid="must-change">{String(session.mustChangePin)}</div>;
    }

    render(<Inspector />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('must-change').textContent).toBe('true');
    });
  });
});

// ── 3. Type alignment with backend contract ───────────────────────────────────

describe('POS type contract—EmployeeLoginResponse', () => {
  it('has all required fields matching backend response', () => {
    const resp: EmployeeLoginResponse = makeLoginResponse();

    // Verify the shape is structurally sound
    expect(typeof resp.token).toBe('string');
    expect(typeof resp.actor_type).toBe('string');
    expect(typeof resp.employee_id).toBe('string');
    expect(typeof resp.employee_code).toBe('string');
    expect(typeof resp.display_name).toBe('string');
    expect(typeof resp.business_id).toBe('number');
    expect(typeof resp.business_name).toBe('string');
    expect(typeof resp.role_type).toBe('string');
    expect(typeof resp.must_change_pin).toBe('boolean');
    // permissions is Record<string, true> — an object, not an array
    expect(typeof resp.permissions).toBe('object');
    expect(Array.isArray(resp.permissions)).toBe(false);
  });
});

describe('POS type contract—PosCapabilitySet', () => {
  it('has all ten capability keys including granular cash capabilities', () => {
    const caps: PosCapabilitySet = {
      can_open_pos: true,
      can_view_assigned_branch: true,
      can_create_sale: false,
      can_refund_sale: false,
      can_manage_cash: false,
      can_view_reports: false,
      can_manage_employees_pos: false,
      can_open_cash: true,
      can_close_cash: true,
      can_register_cash_movement: true,
    };

    expect(Object.keys(caps)).toHaveLength(10);
  });
});

// ── 4. Login page smoke test ──────────────────────────────────────────────────

// Dynamic import to avoid next/navigation issues in tests
describe('Login page — field rendering', () => {
  it('renders all form fields', async () => {
    // Lazy load after mocking next/navigation
    vi.mock('next/navigation', () => ({
      useRouter: () => ({ replace: vi.fn() }),
      usePathname: () => '/pos/login',
    }));

    const { default: PosLoginPage } = await import('@/app/pos/login/page');

    render(<PosLoginPage />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByLabelText(/id de negocio/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/código de empleado/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^pin$/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /ingresar/i })).toBeInTheDocument();
    });
  });

  it('shows error message on 401 login failure', async () => {
    vi.mock('next/navigation', () => ({
      useRouter: () => ({ replace: vi.fn() }),
      usePathname: () => '/pos/login',
    }));

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'Invalid credentials' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const { default: PosLoginPage } = await import('@/app/pos/login/page');

    render(<PosLoginPage />, { wrapper: Wrapper });

    await waitFor(() => screen.getByRole('button', { name: /ingresar/i }));

    fireEvent.change(screen.getByLabelText(/id de negocio/i), {
      target: { value: '5' },
    });
    fireEvent.change(screen.getByLabelText(/código de empleado/i), {
      target: { value: 'EMP-001' },
    });
    fireEvent.change(screen.getByLabelText(/^pin$/i), {
      target: { value: '1234' },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /ingresar/i }));
    });

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByRole('alert').textContent).toMatch(/incorrecto/i);
    });
  });

  it('shows rate-limit error on 429', async () => {
    vi.mock('next/navigation', () => ({
      useRouter: () => ({ replace: vi.fn() }),
      usePathname: () => '/pos/login',
    }));

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Rate limited' }), {
        status: 429,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const { default: PosLoginPage } = await import('@/app/pos/login/page');

    render(<PosLoginPage />, { wrapper: Wrapper });

    await waitFor(() => screen.getByRole('button', { name: /ingresar/i }));

    fireEvent.change(screen.getByLabelText(/id de negocio/i), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText(/código de empleado/i), { target: { value: 'EMP-001' } });
    fireEvent.change(screen.getByLabelText(/^pin$/i), { target: { value: '1234' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /ingresar/i }));
    });

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/demasiados intentos/i);
    });
  });
});

// ── 7. Cash POS API client ────────────────────────────────────────────────────

function makePosCashSession(overrides: Partial<PosCashSession> = {}): PosCashSession {
  return {
    id: 'session-uuid-1',
    status: 'open',
    opening_cash_amount: '500.00',
    closing_cash_counted: null,
    expected_cash_total: null,
    difference_amount: null,
    closing_note: '',
    opened_by_name: 'Ana López',
    opened_at: '2026-03-09T12:00:00Z',
    closed_at: null,
    opened_by_employee: {
      id: 'uuid-test-1',
      employee_code: 'EMP-001',
      display_name: 'Ana López',
    },
    totals: {
      total_sales: '0.00',
      total_in: '0.00',
      total_out: '0.00',
      cash_expected_total: '500.00',
      cash_in_from_sales: '0.00',
    },
    ...overrides,
  };
}

describe('Cash POS API — posGetCurrentCashSession', () => {
  it('returns { session } when a session is open', async () => {
    const session = makePosCashSession();
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ session }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const result = await posGetCurrentCashSession('test-token');

    expect(result.session).not.toBeNull();
    expect(result.session?.id).toBe('session-uuid-1');
    expect(result.session?.status).toBe('open');
  });

  it('returns { session: null } when no session is open', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ session: null }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const result = await posGetCurrentCashSession('test-token');
    expect(result.session).toBeNull();
  });

  it('throws ApiError 401 when token is invalid', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'Invalid token' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(posGetCurrentCashSession('bad-token')).rejects.toMatchObject({
      status: 401,
    });
  });
});

describe('Cash POS API — posOpenCashSession', () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it('sends X-Employee-Token header and returns created session', async () => {
    const session = makePosCashSession();
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ session }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const result = await posOpenCashSession('tok-abc', { opening_cash_amount: '200.00' });

    expect(result.session?.status).toBe('open');
    // The spy wraps a fresh global.fetch — it should have exactly one call
    const lastCall = fetchSpy.mock.calls.at(-1)!;
    expect(lastCall[1]?.headers).toMatchObject({ 'X-Employee-Token': 'tok-abc' });
    expect(lastCall[1]?.method).toBe('POST');
  });

  it('throws ApiError 400 when session already open', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: 'Ya tenés una sesión de caja abierta.' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await expect(posOpenCashSession('tok', {})).rejects.toMatchObject({ status: 400 });
  });

  it('throws ApiError 403 when can_open_cash capability missing', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: 'No tenés permiso para abrir caja.', code: 'capability_required' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await expect(posOpenCashSession('tok', {})).rejects.toMatchObject({ status: 403 });
  });
});

describe('Cash POS API — posCloseCurrentCashSession', () => {
  it('returns closed session with difference_amount', async () => {
    const session = makePosCashSession({
      status: 'closed',
      closing_cash_counted: '480.00',
      expected_cash_total: '500.00',
      difference_amount: '-20.00',
      closed_at: '2026-03-09T20:00:00Z',
    });

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ session }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const result = await posCloseCurrentCashSession('tok', { closing_cash_counted: '480.00' });

    expect(result.session?.status).toBe('closed');
    expect(result.session?.difference_amount).toBe('-20.00');
  });
});

describe('Cash POS API — posCreateCashMovement', () => {
  it('returns movement object on success', async () => {
    const movement = {
      id: 'mov-uuid-1',
      movement_type: 'in',
      category: 'deposit',
      method: 'cash',
      amount: '200.00',
      note: 'Fondo adicional',
      created_at: '2026-03-09T14:00:00Z',
      session_id: 'session-uuid-1',
    };

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ movement }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const result = await posCreateCashMovement('tok', {
      movement_type: 'in',
      category: 'deposit',
      method: 'cash',
      amount: '200.00',
    });

    expect(result.movement.id).toBe('mov-uuid-1');
    expect(result.movement.amount).toBe('200.00');
  });

  it('throws ApiError 400 when no open session', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: 'No hay una sesión de caja abierta.' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await expect(
      posCreateCashMovement('tok', { movement_type: 'out', amount: '50.00' }),
    ).rejects.toMatchObject({ status: 400 });
  });
});

// ── Helpers for sale tests ────────────────────────────────────────────────────

function makePosProduct(overrides: Partial<PosProduct> = {}): PosProduct {
  return {
    id: 'prod-uuid-1',
    name: 'Café Americano',
    sku: 'CAF-001',
    price: '150.00',
    stock_quantity: '50',
    is_active: true,
    ...overrides,
  };
}

// ── 8. usePosCashCurrentSession hook ─────────────────────────────────────────

describe('usePosCashCurrentSession', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('returns null session when not authenticated', async () => {
    // No token in sessionStorage → context is unauthenticated → query disabled
    function Inspector() {
      const { session, isLoading } = usePosCashCurrentSession();
      return (
        <div>
          <span data-testid="loading">{String(isLoading)}</span>
          <span data-testid="session">{session === null ? 'null' : 'session'}</span>
        </div>
      );
    }

    render(<Inspector />, { wrapper: Wrapper });

    await waitFor(() => {
      // query disabled — session stays null, isLoading false
      expect(screen.getByTestId('session').textContent).toBe('null');
    });
  });

  it('returns session data when authenticated and backend responds', async () => {
    const employee = makeEmployee();
    const cashSession = makePosCashSession();

    sessionStorage.setItem('pos_employee_token', 'auth-tok');

    vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        // posGetMe hydration
        new Response(JSON.stringify(employee), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        // GET /pos/cash/current/
        new Response(JSON.stringify({ session: cashSession }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

    function Inspector() {
      const { session } = usePosCashCurrentSession();
      return (
        <div data-testid="session-id">
          {session ? session.id : 'null'}
        </div>
      );
    }

    render(<Inspector />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('session-id').textContent).toBe('session-uuid-1');
    });
  });
});

// ── 9. Sales POS API — posCreateSale ─────────────────────────────────────────

describe('Sales POS API — posCreateSale', () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it('sends POST to /api/v1/pos/sales/ with X-Employee-Token', async () => {
    const responseBody = {
      sale: {
        id: 'sale-uuid-1',
        number: 'VNT-0001',
        status: 'completed',
        total: '300.00',
        payment_method: 'cash',
        created_at: '2026-03-09T15:00:00Z',
      },
    };

    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(responseBody), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const result = await posCreateSale('tok-sale', {
      payment_method: 'cash',
      items: [{ product_id: 'prod-uuid-1', quantity: 2 }],
    });

    expect(result.sale.id).toBe('sale-uuid-1');
    expect(result.sale.number).toBe('VNT-0001');
    expect(result.sale.total).toBe('300.00');

    const lastCall = fetchSpy.mock.calls.at(-1)!;
    expect((lastCall[1]?.headers as Record<string, string>)['X-Employee-Token']).toBe('tok-sale');
    expect(lastCall[1]?.method).toBe('POST');
    expect(lastCall[0]).toContain('/pos/sales/');
  });

  it('throws ApiError 403 when can_create_sale capability missing', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: 'No tenés permiso para crear ventas.', code: 'capability_required' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await expect(
      posCreateSale('tok', { payment_method: 'cash', items: [] }),
    ).rejects.toMatchObject({ status: 403 });
  });

  it('throws ApiError 400 when no open cash session', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: 'No hay una sesión de caja abierta.' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await expect(
      posCreateSale('tok', { payment_method: 'cash', items: [] }),
    ).rejects.toMatchObject({ status: 400 });
  });

  it('serialises payload as JSON body', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ sale: { id: 'x', number: 'VNT-0002', status: 'completed', total: '50.00' } }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const payload = {
      payment_method: 'card' as const,
      items: [{ product_id: 'p1', quantity: 1, unit_price: '50.00' }],
      notes: 'Con leche',
    };

    await posCreateSale('tok', payload);

    const lastCall = fetchSpy.mock.calls.at(-1)!;
    expect(JSON.parse(lastCall[1]?.body as string)).toMatchObject(payload);
  });
});

// ── 10. Catalog POS API — posGetProducts ─────────────────────────────────────

describe('Catalog POS API — posGetProducts', () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it('fetches products and returns results array', async () => {
    const product = makePosProduct();
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ results: [product], count: 1 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const result = await posGetProducts('tok-catalog', 'café');

    expect(result.results).toHaveLength(1);
    expect(result.results[0].name).toBe('Café Americano');
    expect(result.count).toBe(1);
  });

  it('appends ?search= param when search string provided', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ results: [], count: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await posGetProducts('tok', 'ame');

    const url = fetchSpy.mock.calls.at(-1)![0] as string;
    expect(url).toContain('search=ame');
  });

  it('sends request without search param when search is undefined', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ results: [], count: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await posGetProducts('tok');

    const url = fetchSpy.mock.calls.at(-1)![0] as string;
    expect(url).not.toContain('search=');
  });

  it('sends X-Employee-Token header', async () => {
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ results: [], count: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await posGetProducts('my-special-token', 'test');

    const lastCall = fetchSpy.mock.calls.at(-1)!;
    expect((lastCall[1]?.headers as Record<string, string>)['X-Employee-Token']).toBe('my-special-token');
  });

  it('throws ApiError 401 when token invalid', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'Invalid token' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(posGetProducts('bad-tok', 'test')).rejects.toMatchObject({ status: 401 });
  });
});

// ── 11. usePosCreateSale hook ─────────────────────────────────────────────────

describe('usePosCreateSale', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('mutation is available when session is authenticated', async () => {
    const employee = makeEmployee();
    sessionStorage.setItem('pos_employee_token', 'tok-hook');

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(employee), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    function Inspector() {
      const mutation = usePosCreateSale();
      return (
        <div data-testid="status">
          {mutation.status}
        </div>
      );
    }

    render(<Inspector />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('idle');
    });
  });

  it('transitions to error state when backend returns 403', async () => {
    const employee = makeEmployee();
    sessionStorage.setItem('pos_employee_token', 'tok-hook');

    vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        // hydrate /pos/me/
        new Response(JSON.stringify(employee), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        // POST /pos/sales/ → 403
        new Response(
          JSON.stringify({ detail: 'No permission', code: 'capability_required' }),
          { status: 403, headers: { 'Content-Type': 'application/json' } },
        ),
      );

    function Inspector() {
      const mutation = usePosCreateSale();
      return (
        <>
          <div data-testid="status">{mutation.status}</div>
          <button
            onClick={() =>
              mutation.mutate({ payment_method: 'cash', items: [] })
            }
          >
            Mutate
          </button>
        </>
      );
    }

    render(<Inspector />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('idle'));

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Mutate' }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toBe('error');
    });
  });
});

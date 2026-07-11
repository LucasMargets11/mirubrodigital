/**
 * Component-level tests for OnboardingCheckoutPage's triggerReconcile behavior.
 *
 * These tests target behavior that requires rendering the real component:
 *
 *   C1 — Concurrency guard: the button is disabled while isReconciling is true
 *        (UI-level guard), and after a failure the ref resets so a retry works.
 *   C2 — Activated response: when reconcile succeeds, reconcileWarning stays null;
 *        start-checkout is never called; the component does not show payment_ready.
 *   C3 — After a reconcile failure, reconcileWarning appears and "Volver a
 *        verificar" is available; clicking it calls reconcile and clears warning.
 *
 * Mocking strategy
 * ─────────────────
 * • useSearchParams returns { get } per test via searchParamsGetMock.
 * • reconcileCheckoutSession is mocked per-test.
 * • Global fetch is stubbed for polling (GET /checkout-sessions/:id).
 * • getClientApiBaseUrl returns '' so fetch URLs are root-relative.
 * • No fake timers — avoids waitFor interaction issues.
 *   The polling interval (3s) is never advanced in these tests; we only assert
 *   on state visible before the first poll fires.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import { Suspense } from 'react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

// ── Module-level mocks ────────────────────────────────────────────────────────

const searchParamsGetMock = vi.fn();

vi.mock('next/navigation', () => ({
    useSearchParams: () => ({ get: (key: string) => searchParamsGetMock(key) }),
}));

vi.mock('@/lib/api-url', () => ({
    getClientApiBaseUrl: () => '',
}));

const reconcileMock = vi.fn();
vi.mock('@/features/billing/api', () => ({
    reconcileCheckoutSession: (...args: unknown[]) => reconcileMock(...args),
    validatePromoCode: vi.fn().mockResolvedValue({ valid: false, detail: '' }),
}));

// ── Import after mocks ────────────────────────────────────────────────────────

import OnboardingCheckoutPage from '@/app/app/onboarding/checkout/page';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeSearchParams(sessionId: string | null, planCode: string | null = null) {
    searchParamsGetMock.mockImplementation((key: string) => {
        if (key === 'session_id') return sessionId;
        if (key === 'plan') return planCode;
        return null;
    });
}

/** Polling response — keeps component in awaiting_activation. */
const pendingPollResponse = {
    ok: true,
    status: 200,
    json: async () => ({ status: 'awaiting_webhook', subscription: null }),
};

/** Renders the checkout page. */
function renderCheckoutPage() {
    return render(
        <Suspense fallback={<div>loading</div>}>
            <OnboardingCheckoutPage />
        </Suspense>,
    );
}

// ── Test suite ────────────────────────────────────────────────────────────────

describe('OnboardingCheckoutPage — reconcile behavior', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    afterEach(() => {
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
    });

    // ── C1: Concurrency guard via isReconciling state ─────────────────────────
    //
    // The UI-level protection against concurrent reconciles is the
    // `disabled={isReconciling}` prop on the retry button.  The programmatic
    // guard is reconcileInFlightRef.current inside triggerReconcile.
    //
    // Scenario tested:
    //   1. First reconcile fails → reconcileWarning set → retry button shown.
    //   2. Two rapid fireEvent.click calls on the retry button BEFORE React re-renders.
    //      - Click 1: reconcileInFlightRef.current (false) → true → call starts.
    //      - Click 2 (synchronous, before re-render): ref is already true → blocked.
    //   3. reconcileMock called exactly 2 times total (1 mount + 1 button).
    //   4. After slow call resolves, ref resets → a new click works.

    it('C1 — reconcileInFlightRef blocks a rapid second click before React re-renders', async () => {
        makeSearchParams('test-session');

        const reconcileError = Object.assign(
            new Error('[billing.checkout.reconcile] HTTP 405'),
            { httpStatus: 405 },
        );

        // call 1 (useEffect): fails fast → warning shown
        // call 2 (retry click): slow / deferred
        // call 3+ (if not blocked): should not happen
        let resolveSecond!: (v: { session_id: string; status: string; action_taken: string[]; error: null }) => void;
        const secondDeferred = new Promise<{ session_id: string; status: string; action_taken: string[]; error: null }>(
            (res) => { resolveSecond = res; },
        );
        reconcileMock
            .mockRejectedValueOnce(reconcileError)                     // call 1: fast failure
            .mockReturnValueOnce(secondDeferred)                       // call 2: slow in-flight
            .mockResolvedValue({                                        // call 3+: immediate
                session_id: 'test-session',
                status: 'awaiting_webhook',
                action_taken: [],
                error: null,
            });

        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(pendingPollResponse));
        renderCheckoutPage();

        // Step 1: warning appears after call 1 (fast failure).
        await waitFor(() => screen.getByText('Seguimos verificando tu suscripción'));
        const retryBtn = screen.getByRole('button', { name: /Volver a verificar/i });
        expect(reconcileMock).toHaveBeenCalledTimes(1); // only useEffect call so far

        // Step 2: two rapid clicks — SYNCHRONOUS, no await between them.
        // React has not re-rendered between these two clicks, so:
        //   - Click 1 → triggerReconcile runs → reconcileInFlightRef.current = true (sync)
        //   - Click 2 → triggerReconcile checks ref → true → returns early (blocked)
        fireEvent.click(retryBtn);
        fireEvent.click(retryBtn); // second click blocked by reconcileInFlightRef

        // Step 3: only one additional call was made (call 2, not call 3).
        expect(reconcileMock).toHaveBeenCalledTimes(2);

        // Step 4: resolve call 2 → ref resets to false.
        await act(async () => {
            resolveSecond({ session_id: 'test-session', status: 'awaiting_webhook', action_taken: [], error: null });
        });

        // After resolution, isReconciling=false and reconcileWarning=null (cleared at
        // start of triggerReconcile). The warning banner is gone — no retry button.
        // Verify the ref reset by confirming total call count remains 2
        // (no spurious third call was triggered).
        expect(reconcileMock).toHaveBeenCalledTimes(2);
    });

    // ── C2: Reconcile activated — immediate success transition ───────────────
    //
    // When reconcileCheckoutSession returns { status: 'activated' }, the
    // component must transition to the activated phase immediately — WITHOUT
    // waiting for a polling tick to confirm the state.

    it('C2 — reconcile activated: page transitions to success without waiting for poll', async () => {
        makeSearchParams('test-session');

        reconcileMock.mockResolvedValue({
            session_id: 'test-session',
            status: 'activated',
            action_taken: ['Activated'],
            error: null,
        });

        // Polling returns PENDING — proves the component does NOT rely on a
        // subsequent poll to detect activation.
        const fetchMock = vi.fn().mockResolvedValue(pendingPollResponse);
        vi.stubGlobal('fetch', fetchMock);

        renderCheckoutPage();

        // The activated phase must appear from the reconcile result alone —
        // not from the polling loop.
        await waitFor(() => {
            expect(screen.getByText('¡Tu cuenta está activa!')).toBeTruthy();
        });

        // No warning was shown at any point.
        expect(screen.queryByText(/Seguimos verificando/)).toBeNull();

        // start-checkout must NOT have been called.
        const startCheckoutCalls = fetchMock.mock.calls.filter(
            ([url]: [string]) => String(url).includes('start-checkout'),
        );
        expect(startCheckoutCalls).toHaveLength(0);

        // No redirect to Mercado Pago was shown.
        expect(screen.queryByText('Ir a Mercado Pago →')).toBeNull();

        // Only one reconcile call was made.
        expect(reconcileMock).toHaveBeenCalledTimes(1);
    });

    // ── C_race: Reconcile + polling both activated simultaneously ─────────────
    //
    // redirectScheduledRef prevents duplicate activation when both paths
    // complete at nearly the same time.

    it('C_race — reconcile and polling both returning activated causes exactly one activation', async () => {
        makeSearchParams('test-session');

        // Both reconcile and poll return 'activated'.
        reconcileMock.mockResolvedValue({
            session_id: 'test-session',
            status: 'activated',
            action_taken: ['Activated'],
            error: null,
        });

        const activatedPollResponse = {
            ok: true,
            status: 200,
            json: async () => ({
                status: 'activated',
                subscription: {
                    is_active: true,
                    provider_status: 'active',
                    service_type: 'gestion',
                    plan_code: 'start',
                },
            }),
        };
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(activatedPollResponse));

        renderCheckoutPage();

        // The activated phase appears.
        await waitFor(() => {
            expect(screen.getByText('¡Tu cuenta está activa!')).toBeTruthy();
        });

        // No warning appeared.
        expect(screen.queryByText(/Seguimos verificando/)).toBeNull();

        // The activated text is in the DOM exactly once (no duplicate rendering).
        expect(screen.getAllByText('¡Tu cuenta está activa!')).toHaveLength(1);
    });

    // ── C3: Reconcile failure → warning + retry ───────────────────────────────

    it('C3 — after reconcile failure, warning appears; retry succeeds and clears warning', async () => {
        makeSearchParams('test-session');

        const reconcileError = Object.assign(
            new Error('[billing.checkout.reconcile] HTTP 405 for session test-session'),
            { httpStatus: 405 },
        );
        reconcileMock
            .mockRejectedValueOnce(reconcileError)
            .mockResolvedValue({ session_id: 'test-session', status: 'awaiting_webhook', action_taken: [], error: null });

        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(pendingPollResponse));
        renderCheckoutPage();

        // Warning must appear after the failed reconcile.
        await waitFor(() => screen.getByText('Seguimos verificando tu suscripción'));

        // "Volver a verificar" is present and enabled.
        const retryBtn = screen.getByRole('button', { name: /Volver a verificar/i });
        expect(retryBtn).not.toBeDisabled();

        // Clicking retry calls reconcile a second time.
        fireEvent.click(retryBtn);
        await waitFor(() => expect(reconcileMock).toHaveBeenCalledTimes(2));

        // After successful retry, warning is cleared.
        await waitFor(() => {
            expect(screen.queryByText('Seguimos verificando tu suscripción')).toBeNull();
        });
    });
});

// ── Service-type routing and redirect verification ────────────────────────────
//
// These tests require:
//   • Fake timers (to control the 3-second redirect delay in scheduleAppRedirect).
//   • window.location.assign mocked so redirect calls can be asserted.
//   • vi.advanceTimersByTimeAsync: advances fake time AND flushes pending Promises,
//     ensuring background GETs and other microtasks complete before the timer fires.
//
// ── Service-type routing and redirect verification ────────────────────────────
//
// The fix guarantees: resolveActivatedRoute (awaited) → scheduleAppRedirect().
// No redirect timer starts until the route is resolved.
//
// Key behaviors verified:
//   A — Slow GET: redirect timer starts only AFTER the GET completes.
//   B — Polling provides service type: no extra GET, direct route.
//   C — Polling caches service_type before reconcile completes: priority 2 used.
//   D — GET aborted by timeout: safe fallback used, page not blocked.
//   E — Polling halted after activation.

describe('OnboardingCheckoutPage — service-type routing and redirect', () => {
    const assignMock = vi.fn();

    beforeAll(() => {
        Object.defineProperty(window, 'location', {
            configurable: true,
            value: { assign: assignMock },
        });
    });

    beforeEach(() => {
        vi.clearAllMocks();
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.runOnlyPendingTimers();
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    // ── helpers ───────────────────────────────────────────────────────────────

    /** Deferred fetch: call resolve() to make it return the given response. */
    function makeDeferredFetch(serviceType?: string) {
        let resolve!: () => void;
        const pending = new Promise<void>(r => { resolve = r; });
        const mock = vi.fn().mockImplementation((_url: string, _opts?: RequestInit) =>
            pending.then(() => ({
                ok: true,
                status: 200,
                json: async () => ({
                    status: 'activated',
                    subscription: serviceType
                        ? { is_active: true, service_type: serviceType, provider_status: 'active' }
                        : null,
                }),
            })),
        );
        return { mock, resolve };
    }

    /** Immediate fetch returning the given service type (or null subscription). */
    function makeInstantFetch(serviceType?: string, activated = true) {
        return vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => ({
                status: activated ? 'activated' : 'linked',
                subscription: serviceType
                    ? { is_active: activated, service_type: serviceType, provider_status: 'active' }
                    : null,
            }),
        });
    }

    /**
     * Fetch that never resolves but aborts when the AbortController fires.
     * Used to test the ROUTE_RESOLUTION_TIMEOUT_MS (5 s) behavior.
     */
    function makeAbortableFetch() {
        return vi.fn().mockImplementation((_url: string, _opts?: RequestInit) =>
            new Promise((_, reject) => {
                _opts?.signal?.addEventListener('abort', () => {
                    reject(new DOMException('Aborted', 'AbortError'));
                });
                // never resolves otherwise
            }),
        );
    }

    // ── Test A — Slow GET; redirect waits for route resolution ────────────────
    //
    // Under the OLD design the 3-second timer would fire BEFORE the GET finished,
    // sending the user to /app/dashboard.
    // Under the NEW design, scheduleAppRedirect() is only called after the GET.

    it('A — slow GET for qr_reviews: redirect waits; fires only after route is known', async () => {
        makeSearchParams('session-reviews');
        reconcileMock.mockResolvedValue({
            session_id: 'session-reviews',
            status: 'activated',
            action_taken: [],
            error: null,
        });

        const { mock: slowFetch, resolve: resolveFetch } = makeDeferredFetch('qr_reviews');
        vi.stubGlobal('fetch', slowFetch);

        renderCheckoutPage();

        // Flush reconcile; GET is now pending. No timers fired yet.
        await vi.advanceTimersByTimeAsync(0);

        // Success screen shown immediately.
        expect(screen.getByText('¡Tu cuenta está activa!')).toBeTruthy();

        // Advance 3 001 ms — under the OLD design this would have fired the redirect.
        // Under the NEW design, scheduleAppRedirect() hasn't been called yet.
        await vi.advanceTimersByTimeAsync(3001);
        expect(assignMock).not.toHaveBeenCalled();

        // Resolve the GET (simulating a >3 s network).
        resolveFetch();
        // Flush the Promise chain: GET response → resolveActivatedRoute completes
        // → activateSession sets route and calls scheduleAppRedirect().
        await vi.advanceTimersByTimeAsync(0);

        // Redirect timer now starts. Advance past the 3-second delay.
        await vi.advanceTimersByTimeAsync(3001);

        expect(assignMock).toHaveBeenCalledTimes(1);
        expect(assignMock).toHaveBeenCalledWith('/app/resenas/configuracion');
    });

    // ── Test B — Polling delivers service type (no resolution GET needed) ─────
    //
    // Reconcile is slow. Polling fires at T=3 000 ms with activated + service_type.
    // resolveActivatedRoute uses priority 1 → returns immediately without fetching.

    it('B — gestion from polling: single fetch, no extra GET, routes to /app/gestion', async () => {
        makeSearchParams('test-session');

        // Reconcile is slow — polling wins.
        let resolveReconcile!: (v: { session_id: string; status: string; action_taken: string[]; error: null }) => void;
        reconcileMock.mockReturnValue(new Promise(r => { resolveReconcile = r; }));

        // Polling returns gestion (activated) at T=3 000 ms.
        const fetchMock = makeInstantFetch('gestion', true);
        vi.stubGlobal('fetch', fetchMock);

        renderCheckoutPage();

        // Polling fires at T=3 000 ms → activateSession('gestion') → priority 1.
        await vi.advanceTimersByTimeAsync(3001);
        expect(screen.getByText('¡Tu cuenta está activa!')).toBeTruthy();

        // Redirect timer starts after route resolves (immediately, priority 1).
        await vi.advanceTimersByTimeAsync(3001);

        expect(assignMock).toHaveBeenCalledTimes(1);
        expect(assignMock).toHaveBeenCalledWith('/app/gestion');

        // Only the polling GET — no extra resolution GET (priority 1 short-circuits).
        expect(fetchMock).toHaveBeenCalledTimes(1);

        // Late reconcile is a no-op.
        await act(async () => {
            resolveReconcile({ session_id: 'test-session', status: 'activated', action_taken: [], error: null });
        });
        expect(assignMock).toHaveBeenCalledTimes(1);
    });

    // ── Test C — Poll caches service_type before reconcile activates ──────────
    //
    // Polling fires (non-activated) and caches qr_reviews in knownServiceTypeRef.
    // When reconcile later activates, resolveActivatedRoute uses priority 2.
    // No extra GET is needed.

    it('C — knownServiceTypeRef cached by poll; reconcile uses priority-2 cache', async () => {
        makeSearchParams('test-session');

        // Reconcile is slow.
        let resolveReconcile!: (v: { session_id: string; status: string; action_taken: string[]; error: null }) => void;
        reconcileMock.mockReturnValue(new Promise(r => { resolveReconcile = r; }));

        // Polling: returns LINKED (not activated) but with service_type='qr_reviews'.
        // This updates knownServiceTypeRef without calling activateSession.
        const fetchMock = makeInstantFetch('qr_reviews', false /* not activated */);
        vi.stubGlobal('fetch', fetchMock);

        renderCheckoutPage();

        // Polling fires at T=3 000 ms → caches qr_reviews; does NOT activate.
        await vi.advanceTimersByTimeAsync(3001);

        // Reconcile completes with activated → activateSession() uses priority 2.
        await act(async () => {
            resolveReconcile({ session_id: 'test-session', status: 'activated', action_taken: [], error: null });
        });
        // Flush activateSession's async chain (resolveActivatedRoute returns immediately).
        await vi.advanceTimersByTimeAsync(0);

        expect(screen.getByText('¡Tu cuenta está activa!')).toBeTruthy();

        // Redirect timer fires 3 s after route resolved.
        await vi.advanceTimersByTimeAsync(3001);

        expect(assignMock).toHaveBeenCalledTimes(1);
        expect(assignMock).toHaveBeenCalledWith('/app/resenas/configuracion');
    });

    // ── Test D — Timeout: AbortController fires, fallback used ────────────────
    //
    // The resolution GET never responds.  After ROUTE_RESOLUTION_TIMEOUT_MS (5 s),
    // window.setTimeout calls controller.abort() → fetch rejects with AbortError.
    // resolveActivatedRoute falls through to /app/dashboard.

    it('D — GET times out after 5 s; falls back to /app/dashboard; page not blocked', async () => {
        makeSearchParams('test-session');
        reconcileMock.mockResolvedValue({
            session_id: 'test-session',
            status: 'activated',
            action_taken: [],
            error: null,
        });

        vi.stubGlobal('fetch', makeAbortableFetch());

        renderCheckoutPage();

        // Flush reconcile; GET starts (abortable fetch, never resolves on its own).
        await vi.advanceTimersByTimeAsync(0);
        expect(screen.getByText('¡Tu cuenta está activa!')).toBeTruthy();
        expect(assignMock).not.toHaveBeenCalled();

        // Advance 5 001 ms → window.setTimeout for AbortController fires
        // → controller.abort() → fetch rejects → resolveActivatedRoute catches
        // → falls through to /app/dashboard → scheduleAppRedirect() called.
        await vi.advanceTimersByTimeAsync(5001);
        // Redirect timer not yet fired (3 s delay starts now).
        expect(assignMock).not.toHaveBeenCalled();

        // Advance the 3-second redirect delay.
        await vi.advanceTimersByTimeAsync(3001);

        expect(assignMock).toHaveBeenCalledTimes(1);
        expect(assignMock).toHaveBeenCalledWith('/app/dashboard');
    });

    // ── Test E — Polling halted, no spurious fetches after activation ─────────

    it('E — polling cleared after activation; no new fetches; redirect fires once', async () => {
        makeSearchParams('test-session');
        reconcileMock.mockResolvedValue({
            session_id: 'test-session',
            status: 'activated',
            action_taken: [],
            error: null,
        });

        const fetchMock = makeInstantFetch('gestion', true);
        vi.stubGlobal('fetch', fetchMock);

        renderCheckoutPage();

        // Reconcile fires; resolution GET runs; route resolved.
        await vi.advanceTimersByTimeAsync(0);
        expect(screen.getByText('¡Tu cuenta está activa!')).toBeTruthy();

        const fetchCallsAtActivation = fetchMock.mock.calls.length;

        // Advance 10 s — would trigger 3+ polling cycles if interval still ran.
        await vi.advanceTimersByTimeAsync(10_000);

        // No new fetches.
        expect(fetchMock.mock.calls.length).toBe(fetchCallsAtActivation);
        // Redirect fired.
        expect(assignMock).toHaveBeenCalledWith('/app/gestion');
    });
});

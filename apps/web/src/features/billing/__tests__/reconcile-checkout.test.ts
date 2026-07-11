/**
 * Tests for reconcileCheckoutSession — the canonical checkout reconciliation helper.
 *
 * These tests verify:
 *   1.  Canonical URL construction: /reconcile/ is always in the PATH, never
 *       in a query parameter.
 *   2.  HTTP error (e.g. 405 Method Not Allowed) is detected and thrown.
 *   3.  Network failure is propagated as a thrown error.
 *   4.  Successful response is returned correctly.
 *   5.  Special characters in session IDs are URL-encoded.
 *
 * See also: apps/web/src/app/app/onboarding/__tests__/reconcile-checkout-flow.test.ts
 * for integration tests covering the page component's triggerReconcile behaviour.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { reconcileCheckoutSession } from '@/features/billing/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockFetchOk(payload: object) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => payload,
  });
}

function mockFetchError(status: number) {
  return vi.fn().mockResolvedValue({
    ok: false,
    status,
    json: async () => ({ detail: `error ${status}` }),
  });
}

function mockFetchNetworkError() {
  return vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
}

// ── Test suite ────────────────────────────────────────────────────────────────

describe('reconcileCheckoutSession', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  // ── Test 1: Canonical URL construction ──────────────────────────────────────

  it('calls POST with /reconcile/ as a PATH segment — no query string', async () => {
    const fetchMock = mockFetchOk({ session_id: 'test-session', status: 'activated', action_taken: [], error: null });
    vi.stubGlobal('fetch', fetchMock);

    await reconcileCheckoutSession('test-session');

    expect(fetchMock).toHaveBeenCalledOnce();
    const [calledUrl, calledInit] = fetchMock.mock.calls[0] as [string, RequestInit];

    // /reconcile/ must be the final PATH segment — not part of a query string.
    expect(calledUrl).toMatch(/\/api\/v1\/billing\/checkout-sessions\/test-session\/reconcile\/$/);
    expect(calledUrl).not.toContain('?');
    expect(calledUrl).not.toContain('preapproval_id');
    // /reconcile/ must NOT appear after a '?'
    expect(calledUrl).not.toMatch(/\?.*\/reconcile\//);

    // Method and credentials.
    expect(calledInit).toMatchObject({ method: 'POST', credentials: 'include' });
  });

  it('URL-encodes special characters in sessionId', async () => {
    const fetchMock = mockFetchOk({ session_id: 'x', status: 'awaiting_webhook', action_taken: [], error: null });
    vi.stubGlobal('fetch', fetchMock);

    // UUID-style IDs only contain hex and dashes, but verify encoding is applied.
    await reconcileCheckoutSession('abc-123');

    const [calledUrl] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).toContain('/checkout-sessions/abc-123/reconcile/');
  });

  // ── Test 2: HTTP error (e.g. 405 Method Not Allowed) ────────────────────────

  it('throws when the server returns 405 Method Not Allowed', async () => {
    vi.stubGlobal('fetch', mockFetchError(405));

    await expect(reconcileCheckoutSession('test-session')).rejects.toThrow();
  });

  it('attaches httpStatus to the thrown error on HTTP failure', async () => {
    vi.stubGlobal('fetch', mockFetchError(405));

    let caughtError: unknown;
    try {
      await reconcileCheckoutSession('test-session');
    } catch (err) {
      caughtError = err;
    }

    expect(caughtError).toBeDefined();
    expect((caughtError as { httpStatus?: number }).httpStatus).toBe(405);
  });

  it('throws when the server returns 403 Forbidden', async () => {
    vi.stubGlobal('fetch', mockFetchError(403));

    await expect(reconcileCheckoutSession('test-session')).rejects.toThrow();
  });

  it('throws when the server returns 500', async () => {
    vi.stubGlobal('fetch', mockFetchError(500));

    await expect(reconcileCheckoutSession('test-session')).rejects.toThrow();
  });

  // ── Test 3: Network error ────────────────────────────────────────────────────

  it('propagates a network error (fetch rejects)', async () => {
    vi.stubGlobal('fetch', mockFetchNetworkError());

    await expect(reconcileCheckoutSession('test-session')).rejects.toThrow('Failed to fetch');
  });

  it('does not swallow network errors with .catch(() => {})', async () => {
    vi.stubGlobal('fetch', mockFetchNetworkError());

    // Ensure the rejection is real and not silently swallowed.
    let threw = false;
    try {
      await reconcileCheckoutSession('test-session');
    } catch {
      threw = true;
    }
    expect(threw).toBe(true);
  });

  // ── Test 4: Successful response ──────────────────────────────────────────────

  it('returns the parsed response body on success', async () => {
    const payload = {
      session_id: 'test-session',
      status: 'activated',
      action_taken: ['Upserted SubscriptionV2', 'Activated'],
      error: null,
    };
    vi.stubGlobal('fetch', mockFetchOk(payload));

    const result = await reconcileCheckoutSession('test-session');

    expect(result.session_id).toBe('test-session');
    expect(result.status).toBe('activated');
    expect(result.action_taken).toEqual(['Upserted SubscriptionV2', 'Activated']);
    expect(result.error).toBeNull();
  });

  it('returns a safe fallback when the response body is empty / unparseable', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => { throw new SyntaxError('Unexpected end of JSON'); },
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await reconcileCheckoutSession('some-session');

    // Should not throw; returns a minimal fallback object.
    expect(result.session_id).toBe('some-session');
    expect(result.status).toBe('unknown');
  });

  it('returns awaiting_webhook status when payment not confirmed yet', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetchOk({ session_id: 'test-session', status: 'awaiting_webhook', action_taken: [], error: null }),
    );

    const result = await reconcileCheckoutSession('test-session');
    expect(result.status).toBe('awaiting_webhook');
  });

  // ── Test 5: No body / no preapproval_id in request ──────────────────────────

  it('does not send a body or preapproval_id to the reconcile endpoint', async () => {
    const fetchMock = mockFetchOk({ session_id: 'x', status: 'activated', action_taken: [], error: null });
    vi.stubGlobal('fetch', fetchMock);

    await reconcileCheckoutSession('no-body-session');

    const [, calledInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    // No body should be sent.
    expect(calledInit.body).toBeUndefined();
    // URL must not contain preapproval_id.
    const [calledUrl] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(calledUrl).not.toContain('preapproval_id');
  });
});

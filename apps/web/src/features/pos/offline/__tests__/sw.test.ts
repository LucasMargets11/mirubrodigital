/**
 * PR-OFF-08 — Service worker fetch-handler safety.
 *
 * `public/sw.js` is a classic worker script. We load it in a controlled sandbox
 * (fake `self`, injectable `caches` / `fetch`) and assert the hardened fetch
 * logic: it NEVER resolves to `undefined`, uses a safe cache-first strategy for
 * `/_next/static`, serves a controlled offline fallback for navigations, and
 * never intercepts the API.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';

const here = path.dirname(fileURLToPath(import.meta.url));
const swPath = path.resolve(here, '../../../../../public/sw.js');
const swCode = readFileSync(swPath, 'utf8');

const ORIGIN = 'https://app.mirubro.test';

interface SwHandles {
  exports: {
    isCacheableStatic: (request: { method: string }, url: URL) => boolean;
    handleNavigate: (request: unknown) => Promise<Response>;
    handleStatic: (request: unknown) => Promise<Response>;
    offlineFallbackResponse: () => Response;
    cachePosRoutes: (urls: unknown[]) => Promise<void>;
    CACHE_NAME: string;
  };
  listeners: Record<string, (event: unknown) => void>;
}

function loadSw(overrides: { caches?: unknown; fetch?: unknown } = {}): SwHandles {
  const listeners: Record<string, (event: unknown) => void> = {};
  const fakeSelf = {
    location: { origin: ORIGIN },
    addEventListener: (type: string, cb: (event: unknown) => void) => {
      listeners[type] = cb;
    },
    skipWaiting: () => {},
    clients: { claim: () => Promise.resolve() },
  };
  const moduleObj: { exports: Record<string, unknown> } = { exports: {} };
  const sandbox: Record<string, unknown> = {
    self: fakeSelf,
    caches: overrides.caches,
    fetch: overrides.fetch ?? (() => Promise.reject(new Error('offline'))),
    Response: globalThis.Response,
    URL: globalThis.URL,
    console,
    module: moduleObj,
  };
  const fn = new Function(...Object.keys(sandbox), `${swCode}\n;return module.exports;`);
  const exports = fn(...Object.values(sandbox)) as SwHandles['exports'];
  return { exports, listeners };
}

function fakeCache(matchValue: Response | undefined) {
  return {
    match: vi.fn().mockResolvedValue(matchValue),
    open: vi.fn().mockResolvedValue({ put: vi.fn().mockResolvedValue(undefined) }),
  };
}

// ── isCacheableStatic ────────────────────────────────────────────────────────

describe('sw.isCacheableStatic', () => {
  it('caches /_next/static GET assets', () => {
    const { exports } = loadSw();
    const url = new URL(`${ORIGIN}/_next/static/chunks/page.js`);
    expect(exports.isCacheableStatic({ method: 'GET' }, url)).toBe(true);
  });

  it('never caches the API', () => {
    const { exports } = loadSw();
    const url = new URL(`${ORIGIN}/api/v1/pos/sales`);
    expect(exports.isCacheableStatic({ method: 'GET' }, url)).toBe(false);
  });

  it('never caches non-GET requests', () => {
    const { exports } = loadSw();
    const url = new URL(`${ORIGIN}/_next/static/chunks/page.js`);
    expect(exports.isCacheableStatic({ method: 'POST' }, url)).toBe(false);
  });
});

// ── handleStatic (cache-first, safe fallback) ────────────────────────────────

describe('sw.handleStatic', () => {
  it('returns the cached asset without hitting the network (cache-first)', async () => {
    const cached = new Response('cached-js');
    const fetchMock = vi.fn();
    const { exports } = loadSw({ caches: fakeCache(cached), fetch: fetchMock });

    const res = await exports.handleStatic({ url: `${ORIGIN}/_next/static/chunks/x.js` });

    expect(res).toBe(cached);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('returns a valid Response (never undefined) when offline with no cache', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('offline'));
    const { exports } = loadSw({ caches: fakeCache(undefined), fetch: fetchMock });

    const res = await exports.handleStatic({ url: `${ORIGIN}/_next/static/chunks/x.js` });

    expect(res).toBeInstanceOf(Response);
    expect(res.type).toBe('error');
  });
});

// ── handleNavigate (network-first, controlled fallback) ──────────────────────

describe('sw.handleNavigate', () => {
  it('returns the network response when online', async () => {
    const network = new Response('<html>ok</html>', { status: 200 });
    const fetchMock = vi.fn().mockResolvedValue(network);
    const { exports } = loadSw({ caches: fakeCache(undefined), fetch: fetchMock });

    const res = await exports.handleNavigate({ url: `${ORIGIN}/pos/terminal` });

    expect(res).toBe(network);
  });

  it('serves the controlled offline fallback when offline with no cache', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('offline'));
    const { exports } = loadSw({ caches: fakeCache(undefined), fetch: fetchMock });

    const res = await exports.handleNavigate({ url: `${ORIGIN}/pos/terminal/new-sale` });

    expect(res).toBeInstanceOf(Response);
    const text = await res.text();
    expect(text).toContain('todavía no está disponible offline');
  });

  it('falls back to the precached /pos/terminal shell when offline (priority over login)', async () => {
    const terminal = new Response('<html>terminal</html>', { status: 200 });
    const login = new Response('<html>login</html>', { status: 200 });
    const fetchMock = vi.fn().mockRejectedValue(new Error('offline'));
    // Exact request miss, but both /pos/terminal and /pos/login are cached.
    const caches = {
      match: vi.fn((key: unknown) => {
        if (key === '/pos/terminal') return Promise.resolve(terminal);
        if (key === '/pos/login') return Promise.resolve(login);
        return Promise.resolve(undefined);
      }),
      open: vi.fn().mockResolvedValue({ put: vi.fn().mockResolvedValue(undefined) }),
    };
    const { exports } = loadSw({ caches, fetch: fetchMock });

    const res = await exports.handleNavigate({ url: `${ORIGIN}/pos/terminal/new-sale` });

    // Must serve the terminal shell, NEVER login.
    expect(res).toBe(terminal);
    expect(res).not.toBe(login);
  });

  it('returns the exact cached navigation when available without consulting fallbacks', async () => {
    const exact = new Response('<html>exact</html>', { status: 200 });
    const fetchMock = vi.fn().mockRejectedValue(new Error('offline'));
    const caches = {
      match: vi.fn((key: unknown) =>
        Promise.resolve(typeof key === 'object' ? exact : undefined),
      ),
      open: vi.fn().mockResolvedValue({ put: vi.fn().mockResolvedValue(undefined) }),
    };
    const { exports } = loadSw({ caches, fetch: fetchMock });

    const res = await exports.handleNavigate({ url: `${ORIGIN}/pos/terminal` });

    expect(res).toBe(exact);
  });
});

// ── fetch listener routing ───────────────────────────────────────────────────

describe('sw fetch listener', () => {
  function dispatch(handles: SwHandles, request: { url: string; method: string; mode: string }) {
    const respondWith = vi.fn();
    handles.listeners.fetch?.({ request, respondWith });
    return respondWith;
  }

  it('does not intercept the API', () => {
    const handles = loadSw({ caches: fakeCache(undefined) });
    const respondWith = dispatch(handles, {
      url: `${ORIGIN}/api/v1/pos/sales`,
      method: 'GET',
      mode: 'cors',
    });
    expect(respondWith).not.toHaveBeenCalled();
  });

  it('does not intercept cross-origin requests', () => {
    const handles = loadSw({ caches: fakeCache(undefined) });
    const respondWith = dispatch(handles, {
      url: 'https://api.elsewhere.test/v1/data',
      method: 'GET',
      mode: 'cors',
    });
    expect(respondWith).not.toHaveBeenCalled();
  });

  it('handles /_next/static assets', () => {
    const handles = loadSw({ caches: fakeCache(undefined) });
    const respondWith = dispatch(handles, {
      url: `${ORIGIN}/_next/static/chunks/page.js`,
      method: 'GET',
      mode: 'no-cors',
    });
    expect(respondWith).toHaveBeenCalledTimes(1);
  });

  it('handles /pos navigations', () => {
    const handles = loadSw({ caches: fakeCache(undefined) });
    const respondWith = dispatch(handles, {
      url: `${ORIGIN}/pos/terminal/new-sale`,
      method: 'GET',
      mode: 'navigate',
    });
    expect(respondWith).toHaveBeenCalledTimes(1);
  });
});

// ── cachePosRoutes (message precache) ────────────────────────────────────────

describe('sw.cachePosRoutes', () => {
  it('only caches same-app /pos routes and ignores foreign URLs', async () => {
    const add = vi.fn().mockResolvedValue(undefined);
    const caches = {
      match: vi.fn(),
      open: vi.fn().mockResolvedValue({ add }),
    };
    const { exports } = loadSw({ caches });

    await exports.cachePosRoutes(['/pos/terminal', '/pos/terminal/new-sale', '/app/secret', 42]);

    expect(add).toHaveBeenCalledTimes(2);
    expect(add).toHaveBeenCalledWith('/pos/terminal');
    expect(add).toHaveBeenCalledWith('/pos/terminal/new-sale');
  });
});

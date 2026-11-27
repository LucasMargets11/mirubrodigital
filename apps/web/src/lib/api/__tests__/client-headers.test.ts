import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiGet, apiPatch, apiPost } from '../client';

// PROD-08C: headers por llamada (p. ej. `X-Business-Id`) sin perder el
// Content-Type ni el envío de cookies; sin opciones, el comportamiento previo.

function mockFetch() {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
}

function initOf(fetchMock: ReturnType<typeof mockFetch>, index: number): RequestInit {
    return (fetchMock.mock.calls[index] as unknown as [string, RequestInit])[1];
}

afterEach(() => vi.unstubAllGlobals());

describe('lib/api/client headers', () => {
    it('sin opciones envía solo Content-Type y cookies', async () => {
        const fetchMock = mockFetch();
        await apiGet('/api/v1/x/');
        const init = initOf(fetchMock, 0);
        expect(init.method).toBe('GET');
        expect(init.credentials).toBe('include');
        expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    });

    it('suma headers extra sin reemplazar Content-Type en GET, POST y PATCH', async () => {
        const fetchMock = mockFetch();
        const options = { headers: { 'X-Business-Id': '7' } };
        await apiGet('/api/v1/x/', options);
        await apiPost('/api/v1/x/', { a: 1 }, options);
        await apiPatch('/api/v1/x/', { b: 2 }, options);
        for (let index = 0; index < 3; index += 1) {
            const init = initOf(fetchMock, index);
            expect(init.credentials).toBe('include');
            expect(init.headers).toEqual({ 'Content-Type': 'application/json', 'X-Business-Id': '7' });
        }
        expect(initOf(fetchMock, 1).body).toBe('{"a":1}');
        expect(initOf(fetchMock, 2).method).toBe('PATCH');
    });
});

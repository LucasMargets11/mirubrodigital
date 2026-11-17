import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Bandeja abierta (Turnos IA, prueba con teléfono): una derivación nueva
// aparece sola, con el mismo mecanismo de refresco que los avisos.

const api = vi.hoisted(() => ({ listLeads: vi.fn(), acknowledgeLeadAttention: vi.fn() }));
vi.mock('../api', async (importOriginal) => ({ ...(await importOriginal<object>()), ...api }));

import { LEADS_INBOX_POLL_MS, useLeads } from '../hooks';

function wrapper() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useLeads: refresco de la bandeja abierta', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        api.listLeads.mockReset();
        api.acknowledgeLeadAttention.mockReset();
    });
    afterEach(() => vi.useRealTimers());

    it('vuelve a pedir la misma página cada LEADS_INBOX_POLL_MS y muestra la derivación nueva', async () => {
        api.listLeads
            .mockResolvedValueOnce({ count: 0, results: [] })
            .mockResolvedValue({ count: 1, results: [{ id: 'nuevo' }] });
        const filters = { limit: 25, offset: 0 };
        const { result } = renderHook(() => useLeads(filters), { wrapper: wrapper() });

        await vi.waitFor(() => expect(result.current.data?.count).toBe(0));
        await vi.advanceTimersByTimeAsync(LEADS_INBOX_POLL_MS + 50);
        await vi.waitFor(() => expect(result.current.data?.count).toBe(1));

        expect(LEADS_INBOX_POLL_MS).toBeLessThanOrEqual(15_000);
        expect(api.listLeads).toHaveBeenCalledTimes(2);
        expect(api.listLeads).toHaveBeenLastCalledWith(filters);
        // Solo lee: refrescar la bandeja no marca nada como visto.
        expect(api.acknowledgeLeadAttention).not.toHaveBeenCalled();
    });

    it('un refresco fallido conserva lo ya cargado', async () => {
        api.listLeads
            .mockResolvedValueOnce({ count: 1, results: [{ id: 'a' }] })
            .mockRejectedValueOnce(new Error('red caída'));
        const { result } = renderHook(() => useLeads({}), { wrapper: wrapper() });

        await vi.waitFor(() => expect(result.current.data?.count).toBe(1));
        await vi.advanceTimersByTimeAsync(LEADS_INBOX_POLL_MS + 50);
        await vi.waitFor(() => expect(api.listLeads).toHaveBeenCalledTimes(2));
        await vi.advanceTimersByTimeAsync(50);
        expect(result.current.data?.results).toEqual([{ id: 'a' }]);
    });
});

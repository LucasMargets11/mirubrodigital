/**
 * PR-OFF-02B — POS offline bootstrap API client.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { posGetOfflineBootstrap } from '@/lib/api/pos';

describe('posGetOfflineBootstrap', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls the bootstrap endpoint with the employee token', async () => {
    const payload = { bootstrap_version: 1, products: [] };
    const fetchSpy = vi
      .spyOn(global, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

    const result = await posGetOfflineBootstrap('tok-123');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain('/api/v1/pos/offline/bootstrap/');
    expect(init?.method).toBe('GET');
    expect(
      (init?.headers as Record<string, string>)['X-Employee-Token'],
    ).toBe('tok-123');
    expect(result).toMatchObject({ bootstrap_version: 1 });
  });
});

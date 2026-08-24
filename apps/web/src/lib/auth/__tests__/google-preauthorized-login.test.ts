import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { googleAuth, googlePreauthorizedLogin } from '@/lib/auth/client';

const fetchMock = vi.fn();

function response({
  ok,
  status,
  payload,
}: {
  ok: boolean;
  status: number;
  payload: Record<string, unknown>;
}) {
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(payload),
  } as unknown as Response;
}

describe('googlePreauthorizedLogin — ADMIN-CLIENTES 04D API contract', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'log').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('posts the canonical credential payload with cookies to the preauthorized endpoint', async () => {
    fetchMock.mockResolvedValueOnce(response({
      ok: true,
      status: 200,
      payload: { status: 'ok', onboarding: true, access_token: 'ignored' },
    }));

    const result = await googlePreauthorizedLogin('google-id-credential');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/auth/google/preauthorized/',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ credential: 'google-id-credential' }),
      },
    );
    expect(result).toEqual({ success: true, onboarding: true });
  });

  it('maps google_account_not_authorized without retrying the standard endpoint', async () => {
    fetchMock.mockResolvedValueOnce(response({
      ok: false,
      status: 401,
      payload: {
        code: 'google_account_not_authorized',
        detail: 'Sensitive backend reason that must not be shown',
      },
    }));

    await expect(googlePreauthorizedLogin('rejected-credential')).resolves.toEqual({
      success: false,
      code: 'google_account_not_authorized',
      message: 'Esta cuenta de Google no tiene un acceso habilitado. Verificá que estés usando el correo registrado por el administrador.',
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      'http://localhost:8000/api/v1/auth/google/preauthorized/',
    ]);
  });

  it('keeps canonical token and network error treatments', async () => {
    fetchMock
      .mockResolvedValueOnce(response({
        ok: false,
        status: 401,
        payload: { code: 'invalid_google_token', detail: 'Token de Google inválido' },
      }))
      .mockRejectedValueOnce(new TypeError('network unavailable'));

    await expect(googlePreauthorizedLogin('invalid')).resolves.toEqual({
      success: false,
      code: 'invalid_google_token',
      message: 'Token de Google inválido',
    });
    await expect(googlePreauthorizedLogin('offline')).resolves.toEqual({
      success: false,
      message: 'Error de red al autenticar con Google',
    });
  });

  it('leaves the standard Google login on its original endpoint', async () => {
    fetchMock.mockResolvedValueOnce(response({
      ok: true,
      status: 200,
      payload: { onboarding: false },
    }));

    await googleAuth('self-service-credential');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/auth/google/',
      expect.objectContaining({
        credentials: 'include',
        body: JSON.stringify({ credential: 'self-service-credential' }),
      }),
    );
    expect(fetchMock.mock.calls[0][0]).not.toContain('/preauthorized/');
  });

  it('never persists credentials or response tokens in browser storage', async () => {
    const localStorageSet = vi.spyOn(Storage.prototype, 'setItem');
    fetchMock.mockResolvedValueOnce(response({
      ok: true,
      status: 200,
      payload: {
        onboarding: false,
        access_token: 'must-be-ignored',
        refresh_token: 'must-also-be-ignored',
      },
    }));

    await googlePreauthorizedLogin('credential-not-for-storage');

    expect(localStorageSet).not.toHaveBeenCalled();
  });

  it('sends a valid positive business_id in the body (ADMIN-CLIENTES 04D)', async () => {
    fetchMock.mockResolvedValueOnce(response({
      ok: true,
      status: 200,
      payload: { status: 'ok', onboarding: true },
    }));

    const result = await googlePreauthorizedLogin('google-id-credential', 42);

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/auth/google/preauthorized/',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ credential: 'google-id-credential', business_id: 42 }),
      },
    );
    expect(result).toEqual({ success: true, onboarding: true });
  });

  it('omits business_id when it is missing or not a positive integer', async () => {
    fetchMock.mockResolvedValueOnce(response({
      ok: true,
      status: 200,
      payload: { status: 'ok', onboarding: false },
    }));

    await googlePreauthorizedLogin('google-id-credential', undefined);

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/auth/google/preauthorized/',
      expect.objectContaining({
        body: JSON.stringify({ credential: 'google-id-credential' }),
      }),
    );
  });

  it('maps google_preauthorized_business_required to the specific message', async () => {
    fetchMock.mockResolvedValueOnce(response({
      ok: false,
      status: 400,
      payload: {
        code: 'google_preauthorized_business_required',
        detail: 'Usá el enlace de acceso específico de tu comercio para ingresar.',
      },
    }));

    const result = await googlePreauthorizedLogin('credential', 7);

    expect(result).toEqual({
      success: false,
      code: 'google_preauthorized_business_required',
      message: 'Usá el enlace de acceso específico de tu comercio para ingresar.',
    });
  });
});

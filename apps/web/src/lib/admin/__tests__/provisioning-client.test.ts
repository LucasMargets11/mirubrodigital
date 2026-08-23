import { describe, it, expect, vi, afterEach } from 'vitest';

const INPUT = {
  business_name: 'Comercio Ejemplo',
  business_slug: 'comercio-ejemplo',
  service_type: 'gestion',
  country: 'AR',
  currency: 'ARS',
  owner_email: 'owner@empresa.com',
  plan_code: 'gestion_pro',
  complimentary_start: '2026-08-14',
  complimentary_end: '2027-02-14',
  grant_reason: 'Alta administrativa por cortesía comercial',
};

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  };
}

describe('lib/admin/client — provisioning API layer', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  describe('getAdminClientProvisioningOptions', () => {
    it('performs a GET with credentials against the real options endpoint', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(200, { services: [{ value: 'gestion', label: 'Gestión Comercial', plans: [] }] }),
      );
      vi.stubGlobal('fetch', fetchMock);

      const { getAdminClientProvisioningOptions } = await import('@/lib/admin/client');
      const result = await getAdminClientProvisioningOptions();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toMatch(/\/api\/v1\/platform-admin\/clients\/provisioning-options\/$/);
      expect(init.method).toBe('GET');
      expect(init.credentials).toBe('include');

      expect(result.status).toBe('ok');
      if (result.status === 'ok') {
        expect(result.data.services).toHaveLength(1);
      }
    });

    it('maps a 401 to session_expired', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, {})));
      const { getAdminClientProvisioningOptions } = await import('@/lib/admin/client');
      const result = await getAdminClientProvisioningOptions();
      expect(result.status).toBe('session_expired');
    });

    it('maps a 500 to a recoverable error', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(500, {})));
      const { getAdminClientProvisioningOptions } = await import('@/lib/admin/client');
      const result = await getAdminClientProvisioningOptions();
      expect(result.status).toBe('error');
    });

    it('maps a network failure to a recoverable error', async () => {
      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));
      const { getAdminClientProvisioningOptions } = await import('@/lib/admin/client');
      const result = await getAdminClientProvisioningOptions();
      expect(result.status).toBe('error');
    });
  });

  describe('provisionAdminClient', () => {
    it('POSTs to the real endpoint with exactly the ten allowed fields', async () => {
      const fetchMock = vi.fn().mockResolvedValue(
        jsonResponse(201, {
          owner_email: 'owner@empresa.com',
          owner_user_id: 1,
          business_id: 55,
          membership_id: 2,
          login_url: 'https://frontend.example.com/entrar/cliente',
          business: { id: 55, name: 'x', slug: 'x', status: 'trialing', service_type: 'gestion', country: 'AR', currency: 'ARS' },
          owner: { id: 1, email: 'owner@empresa.com', created: true },
          membership: { id: 2, role: 'owner', status: 'active' },
          subscription: { id: 'uuid-value', plan_code: 'gestion_pro', provider: 'manual', status: 'trialing', current_period_start: null, current_period_end: null },
        }),
      );
      vi.stubGlobal('fetch', fetchMock);

      const { provisionAdminClient } = await import('@/lib/admin/client');
      const result = await provisionAdminClient(INPUT);

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toMatch(/\/api\/v1\/platform-admin\/clients\/$/);
      expect(init.method).toBe('POST');
      expect(init.credentials).toBe('include');
      expect(init.headers['Content-Type']).toBe('application/json');

      const body = JSON.parse(init.body as string);
      expect(Object.keys(body).sort()).toEqual([
        'business_name', 'business_slug', 'complimentary_end', 'complimentary_start',
        'country', 'currency', 'grant_reason', 'owner_email', 'plan_code', 'service_type',
      ].sort());
      expect(body).toEqual(INPUT);
      // Dates must be plain YYYY-MM-DD, never a full ISO datetime.
      expect(body.complimentary_start).toBe('2026-08-14');
      expect(body.complimentary_end).toBe('2027-02-14');

      expect(result.status).toBe('ok');
      if (result.status === 'ok') {
        expect(result.data.owner_email).toBe('owner@empresa.com');
        expect(result.data.owner_user_id).toBe(1);
        expect(result.data.business_id).toBe(55);
        expect(result.data.membership_id).toBe(2);
        expect(result.data.login_url).toBe('https://frontend.example.com/entrar/cliente');
        expect(result.data.business.id).toBe(55);
        expect(result.data.subscription.id).toBe('uuid-value');
      }
    });

    it('maps 401 to session_expired', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, {})));
      const { provisionAdminClient } = await import('@/lib/admin/client');
      const result = await provisionAdminClient(INPUT);
      expect(result.status).toBe('session_expired');
    });

    it('maps 403 to forbidden without inspecting the body', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(403, { code: 'unauthorized_provisioning_actor' })));
      const { provisionAdminClient } = await import('@/lib/admin/client');
      const result = await provisionAdminClient(INPUT);
      expect(result.status).toBe('forbidden');
    });

    it('maps DRF structural 400 errors to field_errors keyed by field name', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
        jsonResponse(400, { business_name: ['This field is required.'] }),
      ));
      const { provisionAdminClient } = await import('@/lib/admin/client');
      const result = await provisionAdminClient(INPUT);
      expect(result.status).toBe('field_errors');
      if (result.status === 'field_errors') {
        expect(result.fieldErrors.business_name).toContain('required');
      }
    });

    it('maps the 409 business_slug_conflict domain envelope to domain_error on business_slug', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
        jsonResponse(409, { code: 'business_slug_conflict', detail: 'El slug ya está utilizado.', field: 'business_slug' }),
      ));
      const { provisionAdminClient } = await import('@/lib/admin/client');
      const result = await provisionAdminClient(INPUT);
      expect(result.status).toBe('domain_error');
      if (result.status === 'domain_error') {
        expect(result.error.field).toBe('business_slug');
        expect(result.error.code).toBe('business_slug_conflict');
      }
    });

    it('maps a 422 domain envelope to domain_error with a safe general message', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
        jsonResponse(422, { code: 'complimentary_grant_failed', detail: 'No se pudo otorgar el acceso bonificado.', field: null }),
      ));
      const { provisionAdminClient } = await import('@/lib/admin/client');
      const result = await provisionAdminClient(INPUT);
      expect(result.status).toBe('domain_error');
      if (result.status === 'domain_error') {
        expect(result.error.field).toBeNull();
      }
    });

    it('maps an unparseable 500 to server_error without leaking body content', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error('not json')),
      }));
      const { provisionAdminClient } = await import('@/lib/admin/client');
      const result = await provisionAdminClient(INPUT);
      expect(result.status).toBe('server_error');
    });
  });
});

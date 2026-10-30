import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api/client', async (importOriginal) => ({
    ...await importOriginal<typeof import('@/lib/api/client')>(),
    apiPost: vi.fn(),
    apiGet: vi.fn(),
}));

import { ApiError, apiGet, apiPost } from '@/lib/api/client';
import { buildLeadQuery, confirmAppointmentProposal, createAppointmentProposal, createLeadAppointment, getCurrentAppointmentProposal } from '../api';
import { resolveLeadsAccess } from '../access';

describe('createLeadAppointment (Slice 1)', () => {
    it('manda el contrato canónico en un único POST bajo Leads', async () => {
        const payload = {
            service_id: 's1', professional_id: 'p1', start_at: '2026-11-02T13:00:00Z',
            customer_name: 'Ana', customer_phone: '1155550101', customer_id: 'c1',
        };
        const response = { id: 'lead-1', appointment: { id: 'a1' } };
        vi.mocked(apiPost).mockResolvedValueOnce(response);
        await expect(createLeadAppointment('lead-1', payload)).resolves.toEqual(response);
        expect(apiPost).toHaveBeenCalledExactlyOnceWith('/api/v1/leads/lead-1/appointment/', payload);
    });
});

describe('appointment proposals (Slice 3B)', () => {
    it('confirma manualmente con un POST sin payload de booking ni takeover', async () => {
        const appointment = { id: 'a1', status: 'confirmed' };
        vi.mocked(apiPost).mockResolvedValueOnce(appointment);
        await expect(confirmAppointmentProposal('lead-1', 'proposal-1')).resolves.toEqual(appointment);
        expect(apiPost).toHaveBeenLastCalledWith('/api/v1/leads/lead-1/appointment-proposals/proposal-1/confirm/');
    });

    it('POST manda solo el contrato de propuesta al endpoint del Lead', async () => {
        const payload = {
            service_id: 's1', professional_id: 'p1', start_at: '2026-11-02T13:00:00Z',
            idempotency_key: 'd9f0775a-927a-4fc5-9249-7545580c136d',
        };
        await createAppointmentProposal('lead-1', payload);
        expect(apiPost).toHaveBeenLastCalledWith('/api/v1/leads/lead-1/appointment-proposals/', payload);
    });

    it('GET current interpreta únicamente 404 como ausencia', async () => {
        vi.mocked(apiGet).mockRejectedValueOnce(new ApiError('Not found', 404));
        await expect(getCurrentAppointmentProposal('lead-1')).resolves.toBeNull();
        expect(apiGet).toHaveBeenLastCalledWith('/api/v1/leads/lead-1/appointment-proposals/current/');
        const forbidden = new ApiError('Forbidden', 403);
        vi.mocked(apiGet).mockRejectedValueOnce(forbidden);
        await expect(getCurrentAppointmentProposal('lead-1')).rejects.toBe(forbidden);
        const network = new TypeError('Network');
        vi.mocked(apiGet).mockRejectedValueOnce(network);
        await expect(getCurrentAppointmentProposal('lead-1')).rejects.toBe(network);
    });
});

describe('buildLeadQuery (LEADS 05A)', () => {
    it('sin filtros no manda parámetros (orden `priority` del backend)', () => {
        expect(buildLeadQuery({})).toBe('');
    });

    it('traduce todos los filtros a los parámetros del backend', () => {
        const query = buildLeadQuery({
            status: 'in_progress',
            source: 'whatsapp_agent',
            outcome: 'spam',
            urgency: true,
            needsAttention: false,
            assignedTo: 'unassigned',
            customer: 'unlinked',
            appointment: 'without',
            q: 'ana 11',
            limit: 25,
            offset: 50,
        });
        const params = new URLSearchParams(query.slice(1));
        expect(Object.fromEntries(params)).toEqual({
            status: 'in_progress',
            source: 'whatsapp_agent',
            outcome: 'spam',
            urgency: 'true',
            needs_attention: 'false',
            assigned_to: 'unassigned',
            customer: 'unlinked',
            appointment: 'without',
            q: 'ana 11',
            limit: '25',
            offset: '50',
        });
        expect(params.has('ordering')).toBe(false);
    });
});

describe('resolveLeadsAccess', () => {
    it('exige el flag de plan `leads` y el permiso `view_leads`', () => {
        expect(resolveLeadsAccess({ features: { leads: true }, permissions: { view_leads: true } })).toBe('ok');
        expect(resolveLeadsAccess({ features: { leads: false }, permissions: { view_leads: true } })).toBe('no_plan');
        expect(resolveLeadsAccess({ features: {}, permissions: { view_leads: true } })).toBe('no_plan');
        expect(resolveLeadsAccess({ features: { leads: true }, permissions: { view_leads: false } })).toBe('no_permission');
        expect(resolveLeadsAccess({ features: { leads: true }, permissions: {} })).toBe('no_permission');
    });
});

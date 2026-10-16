import { describe, expect, it } from 'vitest';

import { buildLeadQuery } from '../api';
import { resolveLeadsAccess } from '../access';

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

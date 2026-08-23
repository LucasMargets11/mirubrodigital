/**
 * PR-A — Pricing/product copy regression tests.
 *
 * Validates that the canonical product definition keeps the right split:
 *   • Base highlights advertise "Filtro inteligente" and "Feedback privado".
 *   • Base highlights do NOT advertise "Carteles profesionales".
 *   • Pro highlights include "Analytics avanzadas", "Estados de gestión"
 *     and "Carteles profesionales".
 */

import { describe, it, expect } from 'vitest';
import { REVIEW_PRICING_CARDS } from '../product';

const baseCard = REVIEW_PRICING_CARDS.find((c) => /base/i.test(c.name))!;
const proCard = REVIEW_PRICING_CARDS.find((c) => /pro/i.test(c.name))!;

describe('REVIEW_PRICING_CARDS — PR-A copy contract', () => {
    it('exposes a Base and a Pro card', () => {
        expect(baseCard).toBeTruthy();
        expect(proCard).toBeTruthy();
    });

    it('Base highlights include filtro inteligente + feedback privado', () => {
        const txt = baseCard.highlights.join(' | ').toLowerCase();
        expect(txt).toMatch(/filtro inteligente/);
        expect(txt).toMatch(/feedback privado/);
    });

    it('Base does NOT list carteles profesionales as included', () => {
        const txt = baseCard.highlights.join(' | ').toLowerCase();
        expect(txt).not.toMatch(/carteles profesionales/);
        expect(txt).not.toMatch(/analytics avanzadas/);
        expect(txt).not.toMatch(/estados de gestión/);
    });

    it('Pro highlights include carteles, analytics avanzadas y estados de gestión', () => {
        const txt = proCard.highlights.join(' | ').toLowerCase();
        expect(txt).toMatch(/carteles profesionales/);
        expect(txt).toMatch(/analytics avanzadas/);
        expect(txt).toMatch(/estados de gestión/);
        expect(txt).toMatch(/métricas de conversión/);
    });
});

describe('REVIEW_PRICING_CARDS — PR-B landing pricing', () => {
    it('Base card displays landing price $15.000', () => {
        expect(baseCard.price).toContain('15.000');
        expect(baseCard.period).toBe('/mes');
    });

    it('Pro card displays landing price $20.000', () => {
        expect(proCard.price).toContain('20.000');
        expect(proCard.period).toBe('/mes');
    });

    it('Base and Pro cards do NOT display canonical plans.ts prices', () => {
        expect(baseCard.price).not.toContain('20.000');
        expect(baseCard.price).not.toContain('28.000');
        expect(proCard.price).not.toContain('25.000');
        expect(proCard.price).not.toContain('28.000');
        expect(proCard.price).not.toContain('40.000');
    });
});

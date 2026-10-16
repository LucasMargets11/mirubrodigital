import { createElement, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { mailtoHref, normalizeWhatsappPhone, telHref, whatsappHref } from '../contact-links';
import { useRefreshCustomerAppointmentViews } from '../hooks';

describe('normalizeWhatsappPhone (mismas reglas que business/whatsapp.py)', () => {
    it.each([
        ['+54 9 11 1234-5678', '5491112345678'],
        ['+54 11 1234-5678', '5491112345678'],
        ['0054 9 11 1234 5678', '5491112345678'],
        ['011 1234-5678', '5491112345678'],
        ['11 1234 5678', '5491112345678'],
        ['(0351) 555-1234', '5493515551234'],
        ['+1 415 555 0100', '14155550100'],
    ])('%s → %s', (raw, expected) => {
        expect(normalizeWhatsappPhone(raw)).toBe(expected);
    });

    it.each([null, undefined, '', '4555-0001', '+54 11 123', 'llamar 1112345678', '011 15 1234-5678', '+0 123 456 789'])(
        'no adivina: %s → null',
        (raw) => {
            expect(normalizeWhatsappPhone(raw as string | null | undefined)).toBeNull();
        },
    );

    it('whatsappHref nunca agrega mensaje', () => {
        expect(whatsappHref('11 5555-0001')).toBe('https://wa.me/5491155550001');
        expect(whatsappHref('abc')).toBeNull();
    });
});

describe('telHref / mailtoHref', () => {
    it('tel: conserva el número de la ficha (sin agregar el 9 móvil)', () => {
        expect(telHref('+54 11 4555-0001')).toBe('tel:+541145550001');
        expect(telHref('4555-0001')).toBe('tel:45550001');
        expect(telHref('123')).toBeNull();
        expect(telHref('javascript:alert(1)')).toBeNull();
        expect(telHref(null)).toBeNull();
    });

    it('mailto: solo con un email con forma válida', () => {
        expect(mailtoHref(' ana@qa-turnos.test ')).toBe('mailto:ana@qa-turnos.test');
        expect(mailtoHref('ana@')).toBeNull();
        expect(mailtoHref('a b@c.d')).toBeNull();
        expect(mailtoHref(null)).toBeNull();
    });
});

describe('useRefreshCustomerAppointmentViews', () => {
    it('invalida ficha, turnos, timeline y recordatorios (07B) de ese Customer (no notas ni listado)', async () => {
        const client = new QueryClient();
        const invalidate = vi.spyOn(client, 'invalidateQueries');
        const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children);

        const { result } = renderHook(() => useRefreshCustomerAppointmentViews('c-1'), { wrapper });
        await result.current();

        expect(invalidate.mock.calls.map(([filters]) => filters)).toEqual([
            { queryKey: ['gestion', 'customers', 'c-1'], exact: true },
            { queryKey: ['gestion', 'customers', 'c-1', 'appointments'] },
            { queryKey: ['gestion', 'customers', 'c-1', 'timeline'] },
            { queryKey: ['gestion', 'customers', 'c-1', 'reminders'] },
        ]);
    });
});

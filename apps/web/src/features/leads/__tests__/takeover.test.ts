// MIRUBRO TAKEOVER 05B: cliente HTTP de takeover/release, mapeo de errores y
// regla de polling (solo mientras el control está `*_pending`).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/lib/api/client';

import { releaseLead, takeoverLead } from '../api';
import { conversationCommandRequestFeedback, conversationControlErrorMessage } from '../errors';
import { LEAD_CONVERSATION_POLL_MS, leadConversationPollInterval } from '../hooks';
import type { ConversationControlState, LeadDetail } from '../types';

function jsonResponse(status: number, body: unknown) {
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

const fetchMock = vi.fn();

beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('takeoverLead / releaseLead', () => {
    it.each([
        ['takeover', takeoverLead],
        ['release', releaseLead],
    ] as const)('%s: POST a /api/v1/leads/{id}/%s/ sin body y con cookies de sesión', async (action, fn) => {
        fetchMock.mockResolvedValue(jsonResponse(202, { ok: true, state: `${action}_pending`, command_version: 3 }));
        await expect(fn('lead-1')).resolves.toEqual({ ok: true, state: `${action}_pending`, command_version: 3 });

        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
        expect(url).toMatch(new RegExp(`/api/v1/leads/lead-1/${action}/$`));
        expect(init.method).toBe('POST');
        expect(init.body).toBeUndefined();
        expect(init.credentials).toBe('include');
    });

    it('200 idempotente devuelve el estado actual tal cual', async () => {
        fetchMock.mockResolvedValue(jsonResponse(200, { ok: true, state: 'taken', command_version: 1 }));
        await expect(takeoverLead('lead-1')).resolves.toMatchObject({ state: 'taken' });
    });

    it('errores HTTP llegan como ApiError con status y payload (parser actual), sin reintentos', async () => {
        fetchMock.mockResolvedValue(jsonResponse(409, { ok: false, code: 'command_in_progress', detail: 'Hay otra acción en curso.' }));
        const error = await releaseLead('lead-1').catch((err: unknown) => err);
        expect(error).toBeInstanceOf(ApiError);
        expect((error as ApiError).status).toBe(409);
        expect((error as ApiError).payload).toMatchObject({ code: 'command_in_progress' });
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });
});

describe('conversationControlErrorMessage', () => {
    it.each([
        ['network_error', 'No pudimos comunicarnos con el bot.'],
        ['timeout', 'El bot tardó demasiado en responder.'],
        ['invalid_signature', 'La integración con el bot necesita revisión.'],
        ['http_401', 'La integración con el bot necesita revisión.'],
        ['takeover_disabled', 'El control del bot está deshabilitado.'],
        ['conversation_not_found', 'El bot ya no reconoce esta conversación.'],
        ['version_conflict', 'El estado de la conversación está desincronizado.'],
        ['version_regression', 'El estado de la conversación está desincronizado.'],
        ['business_mismatch', 'La configuración de esta conversación no coincide con el negocio.'],
        ['http_502', 'No pudimos cambiar el control de esta conversación.'],
        [null, 'No pudimos cambiar el control de esta conversación.'],
    ])('%s → texto para recepción', (code, message) => {
        expect(conversationControlErrorMessage(code)).toBe(message);
    });
});

describe('conversationCommandRequestFeedback', () => {
    it('409 es un cambio de estado (info), 503 integración no disponible, otros genérico', () => {
        expect(conversationCommandRequestFeedback(new ApiError('x', 409, { detail: 'crudo' }))).toEqual({
            tone: 'info',
            message: 'El estado de la conversación cambió. Actualizamos la información.',
        });
        expect(conversationCommandRequestFeedback(new ApiError('x', 503, {}))).toEqual({
            tone: 'error',
            message: 'El control del bot no está disponible en este momento.',
        });
        expect(conversationCommandRequestFeedback(new ApiError('x', 403, {})).message).toBe('No tenés permiso para realizar esta acción.');
        expect(conversationCommandRequestFeedback(new TypeError('Failed to fetch')).message).toBe(
            'No pudimos cambiar el control de esta conversación. Intentá nuevamente.',
        );
    });
});

describe('leadConversationPollInterval', () => {
    const withState = (state: ConversationControlState) =>
        ({ conversation_control: { state } }) as unknown as LeadDetail;

    it('refresca solo durante takeover_pending / release_pending', () => {
        expect(leadConversationPollInterval(withState('takeover_pending'))).toBe(LEAD_CONVERSATION_POLL_MS);
        expect(leadConversationPollInterval(withState('release_pending'))).toBe(LEAD_CONVERSATION_POLL_MS);
        expect(LEAD_CONVERSATION_POLL_MS).toBeGreaterThanOrEqual(2000);
        expect(LEAD_CONVERSATION_POLL_MS).toBeLessThanOrEqual(3000);
    });

    it('se detiene en active / taken / error, sin control o sin datos', () => {
        for (const state of ['active', 'taken', 'error'] as const) {
            expect(leadConversationPollInterval(withState(state))).toBe(false);
        }
        expect(leadConversationPollInterval({ conversation_control: null } as unknown as LeadDetail)).toBe(false);
        expect(leadConversationPollInterval(undefined)).toBe(false);
    });
});

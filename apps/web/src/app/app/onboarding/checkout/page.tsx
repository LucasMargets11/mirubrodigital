'use client';

/**
 * Onboarding checkout page — Wave 4 / Wave 5.
 *
 * Step 3 of the onboarding funnel: payment initiation, MP redirect, and
 * activation polling.
 *
 * URL params:
 *   ?plan=<plan_code>     — plan code to pass to start-checkout (required on
 *                           first visit or when re-initiating from plan page)
 *   ?session_id=<uuid>    — Wave 5: existing checkout session ID returned by
 *                           the MP back_url redirect handler.  When present,
 *                           the start-checkout call is skipped entirely —
 *                           polling begins immediately against the known session.
 *
 * Flow (normal):
 *   1. On mount: POST /api/v1/auth/onboarding/start-checkout/ with plan_code.
 *      This is IDEMPOTENT — if a checkout session already exists for this
 *      (user, tenant, plan), the same session and init_point are returned.
 *   2. Page shows payment link (init_point → Mercado Pago).
 *   3. User opens the MP link (new tab recommended, handled below).
 *   4. Page starts polling GET /api/v1/billing/checkout-sessions/<id> every 3 s.
 *   5. On status='activated' → show success → redirect to /app/dashboard.
 *   6. On status='failed'|'expired' → show error + retry option.
 *
 * Flow (MP return / Wave 5):
 *   The /subscribe/return page detects checkout_session_id in the back_url
 *   and redirects here with ?session_id=<id>.  We set sessionIdRef directly
 *   and start polling without calling start-checkout again.
 *
 * Resume semantics:
 *   If the user re-logs in with an existing checkout_pending session, the
 *   onboarding index page redirects here with ?plan=<code>.  The idempotent
 *   start-checkout call recovers the existing session and init_point so the
 *   user can complete the payment without starting over.
 */

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';

import { getClientApiBaseUrl } from '@/lib/api-url';

const API_URL = getClientApiBaseUrl();

// Poll every 3 seconds for up to ~15 minutes (300 attempts).
const POLL_INTERVAL_MS = 3_000;
const MAX_POLL_ATTEMPTS = 300;

// ── Types ─────────────────────────────────────────────────────────────────────

type StartCheckoutPayload = {
    checkout_session_id: string;
    init_point: string;
    status: string;
    reused: boolean;
};

type SessionPollData = {
    status: string;
    subscription: { is_active: boolean; provider_status: string } | null;
};

type PagePhase =
    | 'loading'             // calling start-checkout
    | 'payment_ready'       // init_point available — waiting for user to click
    | 'awaiting_activation' // user opened MP; polling for webhook activation
    | 'activated'           // business.status → active/trialing
    | 'failed'              // checkout failed or expired
    | 'error';              // unexpected API error during initiation

// ── Component ─────────────────────────────────────────────────────────────────

export default function OnboardingCheckoutPage() {
    const searchParams = useSearchParams();
    const planCode = searchParams.get('plan') ?? '';
    // Wave 5: session_id provided by the MP back_url return handler.
    // When set, we skip start-checkout and jump directly to polling.
    const resumeSessionId = searchParams.get('session_id') ?? '';

    const [phase, setPhase] = useState<PagePhase>('loading');
    const [initPoint, setInitPoint] = useState<string>('');
    const [errorMessage, setErrorMessage] = useState<string>('');

    // Use refs to avoid stale closures inside the polling interval.
    const sessionIdRef = useRef<string>('');
    const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollCountRef = useRef(0);

    // ── Polling helpers ────────────────────────────────────────────────────────

    function stopPolling() {
        if (pollTimerRef.current) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
        }
    }

    function scheduleAppRedirect() {
        // Give the user a moment to read the success message before navigating.
        setTimeout(() => {
            window.location.assign('/app/dashboard');
        }, 3_000);
    }

    function startPolling() {
        if (pollTimerRef.current) return; // guard: only one interval at a time
        setPhase('awaiting_activation');
        pollCountRef.current = 0;

        pollTimerRef.current = setInterval(async () => {
            pollCountRef.current += 1;

            if (pollCountRef.current > MAX_POLL_ATTEMPTS) {
                stopPolling();
                setPhase('failed');
                setErrorMessage(
                    'El tiempo de espera expiró. ' +
                    'Si completaste el pago, tu cuenta será activada en unos minutos automáticamente.',
                );
                return;
            }

            const sid = sessionIdRef.current;
            if (!sid) return;

            try {
                const resp = await fetch(
                    `${API_URL}/api/v1/billing/checkout-sessions/${sid}`,
                    { credentials: 'include' },
                );
                if (!resp.ok) return; // transient error — keep retrying

                const data: SessionPollData = await resp.json();

                if (data.status === 'activated' || data.subscription?.is_active) {
                    stopPolling();
                    setPhase('activated');
                    scheduleAppRedirect();
                } else if (data.status === 'failed' || data.status === 'expired') {
                    stopPolling();
                    setPhase('failed');
                    setErrorMessage('El pago no fue completado o la sesión expiró.');
                }
                // else: still pending — keep polling
            } catch {
                // Network error — keep polling silently
            }
        }, POLL_INTERVAL_MS);
    }

    // ── Checkout initiation ────────────────────────────────────────────────────

    async function initiateCheckout(code: string) {
        try {
            const resp = await fetch(`${API_URL}/api/v1/auth/onboarding/start-checkout/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ plan_code: code }),
            });

            if (!resp.ok) {
                const payload = await resp.json().catch(() => ({}));

                // 409 = business already activated — leave onboarding funnel
                if (resp.status === 409) {
                    window.location.assign('/app');
                    return;
                }

                // 403 = email not verified
                if (resp.status === 403) {
                    setPhase('error');
                    setErrorMessage(
                        'Verificá tu email antes de continuar. ' +
                        'Revisá tu bandeja de entrada y hacé clic en el link que te enviamos.',
                    );
                    return;
                }

                setPhase('error');
                setErrorMessage(
                    payload?.detail ?? 'No pudimos iniciar el pago. Intentalo de nuevo.',
                );
                return;
            }

            const result: StartCheckoutPayload = await resp.json();
            sessionIdRef.current = result.checkout_session_id;
            setInitPoint(result.init_point);
            setPhase('payment_ready');
        } catch {
            setPhase('error');
            setErrorMessage('Error de red. Verificá tu conexión e intentalo de nuevo.');
        }
    }

    // ── Mount ──────────────────────────────────────────────────────────────────

    useEffect(() => {
        // Wave 5: MP back_url return path — session already exists, jump to polling.
        if (resumeSessionId) {
            sessionIdRef.current = resumeSessionId;
            startPolling();
            return;
        }

        if (!planCode) {
            setPhase('error');
            setErrorMessage('No se especificó ningún plan. Volvé a elegir un plan.');
            return;
        }
        initiateCheckout(planCode);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Cleanup on unmount
    useEffect(() => () => stopPolling(), []);

    // ── Render ─────────────────────────────────────────────────────────────────

    return (
        <div className="w-full max-w-lg">
            {/* Step indicator */}
            <div className="flex items-center gap-2 mb-8 text-xs text-slate-500">
                <span className="text-slate-400">1. Servicio</span>
                <span>→</span>
                <span className="text-slate-400">2. Plan</span>
                <span>→</span>
                <span className="font-semibold text-slate-900">3. Confirmación</span>
            </div>

            {/* ── Loading ───────────────────────────────────────────────────── */}
            {phase === 'loading' && (
                <div className="text-center py-16">
                    <div className="inline-block w-6 h-6 border-2 border-slate-300 border-t-slate-900 rounded-full animate-spin mb-4" />
                    <p className="text-sm text-slate-500">Preparando tu pago...</p>
                </div>
            )}

            {/* ── Payment ready ─────────────────────────────────────────────── */}
            {phase === 'payment_ready' && (
                <div>
                    <h1 className="text-2xl font-semibold text-slate-900 mb-2">
                        Completá tu pago
                    </h1>
                    <p className="text-sm text-slate-500 mb-8">
                        Al hacer clic en el botón serás llevado a Mercado Pago para completar
                        tu suscripción. Cuando el pago sea confirmado, tu cuenta quedará activa
                        automáticamente sin que tengas que hacer nada más.
                    </p>

                    {initPoint ? (
                        <a
                            href={initPoint}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={startPolling}
                            className="block w-full py-3 px-4 bg-slate-900 text-white text-sm
                                       font-medium rounded-lg hover:bg-slate-800 transition-colors
                                       text-center"
                        >
                            Ir a Mercado Pago →
                        </a>
                    ) : (
                        /* init_point not available (edge case) — allow manual polling */
                        <button
                            onClick={startPolling}
                            className="w-full py-3 px-4 bg-slate-900 text-white text-sm font-medium
                                       rounded-lg hover:bg-slate-800 transition-colors"
                        >
                            Ya completé el pago — verificar estado
                        </button>
                    )}

                    <p className="text-xs text-slate-400 mt-5 text-center">
                        ¿Ya completaste el pago en otra pestaña?{' '}
                        <button
                            onClick={startPolling}
                            className="underline text-slate-600 hover:text-slate-900"
                        >
                            Verificar estado
                        </button>
                    </p>
                </div>
            )}

            {/* ── Awaiting activation (polling) ─────────────────────────────── */}
            {phase === 'awaiting_activation' && (
                <div className="text-center py-16">
                    <div className="inline-block w-8 h-8 border-2 border-slate-300 border-t-slate-900 rounded-full animate-spin mb-5" />
                    <h1 className="text-xl font-semibold text-slate-900 mb-2">
                        Verificando tu pago...
                    </h1>
                    <p className="text-sm text-slate-500">
                        Esto puede tardar unos segundos. No cierres esta ventana.
                    </p>
                </div>
            )}

            {/* ── Activated ─────────────────────────────────────────────────── */}
            {phase === 'activated' && (
                <div className="text-center py-16">
                    <div className="text-5xl mb-5 select-none">✓</div>
                    <h1 className="text-2xl font-semibold text-slate-900 mb-2">
                        ¡Tu cuenta está activa!
                    </h1>
                    <p className="text-sm text-slate-500 mb-6">
                        Serás redirigido a tu panel en unos segundos...
                    </p>
                    <a
                        href="/app/dashboard"
                        className="text-sm font-medium text-slate-900 underline underline-offset-2"
                    >
                        Ir al panel ahora
                    </a>
                </div>
            )}

            {/* ── Failed ────────────────────────────────────────────────────── */}
            {phase === 'failed' && (
                <div className="text-center py-16">
                    <div className="text-5xl mb-5 select-none text-red-500">✗</div>
                    <h1 className="text-xl font-semibold text-slate-900 mb-2">
                        No pudimos confirmar tu pago
                    </h1>
                    <p className="text-sm text-slate-500 mb-6">
                        {errorMessage || 'El pago no fue completado o la sesión expiró.'}
                    </p>
                    <div className="flex flex-col items-center gap-3">
                        <a
                            href="/app/onboarding/plan"
                            className="text-sm font-medium text-slate-900 underline underline-offset-2"
                        >
                            Volver a elegir plan
                        </a>
                        {planCode && (
                            <button
                                onClick={() => {
                                    setPhase('loading');
                                    setErrorMessage('');
                                    stopPolling();
                                    initiateCheckout(planCode);
                                }}
                                className="text-sm text-slate-500 underline underline-offset-2 hover:text-slate-800"
                            >
                                Reintentar con el mismo plan
                            </button>
                        )}
                    </div>
                </div>
            )}

            {/* ── Error ─────────────────────────────────────────────────────── */}
            {phase === 'error' && (
                <div className="rounded-xl border border-red-200 bg-red-50 p-6">
                    <p className="text-sm font-semibold text-red-800 mb-2">
                        Ocurrió un error
                    </p>
                    <p className="text-xs text-red-700 mb-5">{errorMessage}</p>
                    <div className="flex gap-4">
                        <a
                            href="/app/onboarding/plan"
                            className="text-sm text-slate-700 underline underline-offset-2"
                        >
                            Volver a elegir plan
                        </a>
                        {planCode && (
                            <button
                                onClick={() => {
                                    setPhase('loading');
                                    setErrorMessage('');
                                    initiateCheckout(planCode);
                                }}
                                className="text-sm text-slate-900 underline underline-offset-2 font-medium"
                            >
                                Reintentar
                            </button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

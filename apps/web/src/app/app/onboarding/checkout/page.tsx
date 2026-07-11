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
import { reconcileCheckoutSession, validatePromoCode } from '@/features/billing/api';
import type { PromoValidationSuccess } from '@/features/billing/subscription-types';

const API_URL = getClientApiBaseUrl();

// Poll every 3 seconds for up to ~15 minutes (300 attempts).
const POLL_INTERVAL_MS = 3_000;
const MAX_POLL_ATTEMPTS = 300;
// After this many attempts, show the "still processing" soft-warning but keep polling.
const SOFT_WARNING_ATTEMPTS = 40; // ~2 min
// Maximum time allowed for the background service-type lookup before falling back.
const ROUTE_RESOLUTION_TIMEOUT_MS = 5_000;

// ── Types ─────────────────────────────────────────────────────────────────────

type StartCheckoutPayload = {
    checkout_session_id: string;
    init_point: string;
    status: string;
    reused: boolean;
};

type SessionPollData = {
    status: string;
    subscription: {
        is_active: boolean;
        provider_status: string;
        service_type?: string;
        plan_code?: string;
    } | null;
};

// Map a service_type to the entry route after activation.
function routeForService(serviceType?: string): string {
    switch (serviceType) {
        case 'qr_reviews':
            return '/app/resenas/configuracion';
        case 'menu_qr':
        case 'menu_qr_visual':
        case 'menu_qr_marca':
            return '/app/carta';
        case 'gestion':
            return '/app/gestion';
        default:
            return '/app/dashboard';
    }
}

type PagePhase =
    | 'pre_checkout'        // promo input form — before initiating checkout
    | 'loading'             // calling start-checkout
    | 'payment_ready'       // init_point available — waiting for user to click
    | 'awaiting_activation' // user opened MP; polling for webhook activation
    | 'activated'           // business.status → active/trialing
    | 'failed'              // checkout failed or expired (genuine MP rejection)
    | 'timed_out'           // polling timed out — payment may still be processing
    | 'error';              // unexpected API error during initiation

// ── Component ─────────────────────────────────────────────────────────────────

export default function OnboardingCheckoutPage() {
    const searchParams = useSearchParams();
    const planCode = searchParams.get('plan') ?? '';
    // product_code forwarded from the plan page for start-checkout validation.
    const productCode = searchParams.get('product') ?? '';
    // Wave 5: session_id provided by the MP back_url return handler.
    // When set, we skip start-checkout and jump directly to polling.
    const resumeSessionId = searchParams.get('session_id') ?? '';

    const [phase, setPhase] = useState<PagePhase>('loading');
    const [initPoint, setInitPoint] = useState<string>('');
    const [errorMessage, setErrorMessage] = useState<string>('');

    // Promo code state
    const [promoInput, setPromoInput] = useState('');
    const [promoLoading, setPromoLoading] = useState(false);
    const [appliedPromo, setAppliedPromo] = useState<PromoValidationSuccess | null>(null);
    const [promoError, setPromoError] = useState('');

    // Use refs to avoid stale closures inside the polling interval.
    const sessionIdRef = useRef<string>('');
    const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollCountRef = useRef(0);
    // Guard: prevent double initiation from React Strict Mode / concurrent effects.
    const initiatingRef = useRef(false);
    // Guard: prevent concurrent reconcile requests for the same session.
    const reconcileInFlightRef = useRef(false);
    // Guard: prevent duplicate activation when reconcile + polling both see 'activated'.
    const redirectScheduledRef = useRef(false);
    // Guard: prevent two concurrent route-resolution + activation flows.
    const activationInFlightRef = useRef(false);
    // Caches the service_type discovered from any poll response.
    // Used by activateSession if reconcile wins the race before the first poll fires.
    const knownServiceTypeRef = useRef<string | null>(null);
    // Track whether the open-session soft warning has been shown.
    const [pollingSlowWarning, setPollingSlowWarning] = useState(false);
    // Non-destructive reconcile feedback: shown alongside polling, never blocks UX.
    const [reconcileWarning, setReconcileWarning] = useState<string | null>(null);
    // True while a reconcile request is in flight (used to disable retry button).
    const [isReconciling, setIsReconciling] = useState(false);

    // ── Polling helpers ────────────────────────────────────────────────────────

    function stopPolling() {
        if (pollTimerRef.current) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
        }
    }

    // ── Shared activation helper ───────────────────────────────────────────────
    //
    // Called by BOTH the polling interval and triggerReconcile when the session
    // reaches 'activated' status.
    //
    // Guaranteed order:
    //   1. Cache serviceType immediately (polling may provide it while reconcile
    //      is resolving the route in the background).
    //   2. Guard against concurrent activations and duplicate redirects.
    //   3. setPhase('activated') — success screen shown immediately.
    //   4. AWAIT resolveActivatedRoute — route fully resolved before timer starts.
    //   5. redirectScheduledRef = true and scheduleAppRedirect() called only after
    //      the route is known.
    //
    // This eliminates the race where a slow GET could finish after the 3-second
    // timer had already fired with the wrong (/app/dashboard) URL.
    //
    async function activateSession(serviceType?: string) {
        // Immediately cache any service type we receive — even if we return early,
        // the value may be used by a concurrent activation that is already running.
        if (serviceType) {
            knownServiceTypeRef.current = serviceType;
        }

        // Idempotency guards.
        if (redirectScheduledRef.current || activationInFlightRef.current) {
            return;
        }
        activationInFlightRef.current = true;

        stopPolling();
        setReconcileWarning(null);
        // Show the success screen immediately while the route resolves.
        setPhase('activated');

        try {
            const sid = sessionIdRef.current;
            const route = await resolveActivatedRoute(sid, serviceType);

            // Re-check: another activation path may have completed while we were
            // resolving the route (e.g. a second poll delivered a competing result).
            if (redirectScheduledRef.current) return;

            redirectTargetRef.current = route;
            redirectScheduledRef.current = true;
            scheduleAppRedirect();
        } finally {
            activationInFlightRef.current = false;
        }
    }

    // ── Service-type resolver ──────────────────────────────────────────────
    //
    // Resolves the post-activation redirect route.
    //
    // Priority:
    //   1. explicitServiceType (from polling, which always has subscription data).
    //   2. knownServiceTypeRef.current (cached from any prior poll).
    //   3. One GET to the session status endpoint (with AbortController timeout).
    //   4. Re-check knownServiceTypeRef.current — polling may have updated it
    //      while the GET was in flight.
    //   5. routeForService(undefined) — falls back to /app/dashboard which is a
    //      smart router: it reads the user’s active service and redirects there.
    //      Safe for all activated services (gestion, qr_reviews, menu_qr, etc.).
    //
    async function resolveActivatedRoute(
        sessionId: string,
        explicitServiceType?: string,
    ): Promise<string> {
        // Priority 1.
        if (explicitServiceType) {
            knownServiceTypeRef.current = explicitServiceType;
            return routeForService(explicitServiceType);
        }

        // Priority 2.
        if (knownServiceTypeRef.current) {
            return routeForService(knownServiceTypeRef.current);
        }

        // Priority 3: single GET with hard timeout.
        if (sessionId) {
            const controller = new AbortController();
            const timeoutId = window.setTimeout(
                () => controller.abort(),
                ROUTE_RESOLUTION_TIMEOUT_MS,
            );
            try {
                const resp = await fetch(
                    `${API_URL}/api/v1/billing/checkout-sessions/${sessionId}`,
                    { credentials: 'include', signal: controller.signal },
                );
                if (resp.ok) {
                    const data: SessionPollData = await resp.json();
                    const st = data.subscription?.service_type;
                    if (st) {
                        knownServiceTypeRef.current = st;
                        return routeForService(st);
                    }
                }
            } catch {
                // Timeout (AbortError) or network error — fall through.
            } finally {
                window.clearTimeout(timeoutId);
            }
        }

        // Priority 4: re-check cache (polling may have updated it during the GET).
        if (knownServiceTypeRef.current) {
            return routeForService(knownServiceTypeRef.current);
        }

        // Priority 5: safe universal fallback.
        // /app/dashboard is a smart server-side router that reads session.current.service
        // and redirects to the service-specific entry point. Safe for all activated services.
        return routeForService(undefined);
    }

    // ── Canonical reconcile ────────────────────────────────────────────────────
    //
    // Single entry point for all reconcile calls. Uses the canonical helper from
    // billing/api.ts which always builds:
    //   POST /api/v1/billing/checkout-sessions/{sessionId}/reconcile/
    // with /reconcile/ as a PATH segment — never in a query parameter.
    //
    // Result handling:
    //   status='activated'  → activateSession() immediately (no polling needed).
    //   other status + error field → show non-technical warning; keep polling.
    //   HTTP or network error → show warning; keep polling.
    //   Never creates a new checkout or redirects to MP.
    //   Concurrency guard prevents two simultaneous requests for the same session.
    //
    async function triggerReconcile(sid: string) {
        if (!sid || reconcileInFlightRef.current) return;
        reconcileInFlightRef.current = true;
        setIsReconciling(true);
        setReconcileWarning(null); // clear any previous warning at start of attempt

        try {
            const result = await reconcileCheckoutSession(sid);

            if (result.status === 'activated') {
                // Backend confirmed activation — transition immediately.
                // No need to wait for the next polling tick.
                void activateSession();
                return;
            }

            // Non-terminal status returned successfully.
            // If the backend signals an internal issue despite HTTP 200,
            // show a non-technical warning but keep polling — webhook may still arrive.
            if (result.error) {
                console.warn(
                    '[billing.checkout.reconcile] Server returned error field',
                    `scope=billing.checkout.reconcile`,
                    `checkout_session_id=${sid}`,
                    `status=${result.status}`,
                );
                setReconcileWarning(
                    'Seguimos verificando tu suscripción. Mercado Pago puede tardar unos instantes en ' +
                    'confirmar la operación. No vuelvas a pagar. ' +
                    'Podés esperar o volver a verificar el estado.',
                );
            }
            // else: clean non-activated status (e.g. awaiting_webhook, linked) —
            // warning already cleared above; polling continues normally.

        } catch (err: unknown) {
            const httpStatus = (err as { httpStatus?: number })?.httpStatus;
            // Log technical context without sensitive data.
            console.error(
                '[billing.checkout.reconcile]',
                'scope=billing.checkout.reconcile',
                `checkout_session_id=${sid}`,
                httpStatus != null ? `http_status=${httpStatus}` : 'error=network',
                err,
            );
            // Show a non-alarmist, non-technical message to the user.
            // Polling remains active — the webhook can still confirm the payment.
            setReconcileWarning(
                'Seguimos verificando tu suscripción. Mercado Pago puede tardar unos instantes en ' +
                'confirmar la operación. No vuelvas a pagar. ' +
                'Podés esperar o volver a verificar el estado.',
            );
        } finally {
            reconcileInFlightRef.current = false;
            setIsReconciling(false);
        }
    }

    // Where to send the user once activation is confirmed.  Set from the
    // poll response so we can route into the service-specific entry page
    // (e.g. /app/resenas/configuracion for QR de Reseñas).
    const redirectTargetRef = useRef<string>('/app/dashboard');

    function scheduleAppRedirect() {
        // Give the user a moment to read the success message before navigating.
        setTimeout(() => {
            window.location.assign(redirectTargetRef.current);
        }, 3_000);
    }

    function startPolling() {
        if (pollTimerRef.current) return; // guard: only one interval at a time
        setPhase('awaiting_activation');
        pollCountRef.current = 0;

        pollTimerRef.current = setInterval(async () => {
            pollCountRef.current += 1;

            // After ~2 min without activation, show a soft warning inside the
            // spinner screen so the user knows we haven't forgotten them.
            if (pollCountRef.current === SOFT_WARNING_ATTEMPTS) {
                setPollingSlowWarning(true);
            }

            if (pollCountRef.current > MAX_POLL_ATTEMPTS) {
                stopPolling();
                // Timeout ≠ payment failure.  The webhook may still arrive.
                // Use a dedicated phase so we can show a "don't pay again" message
                // and NOT offer the "Reintentar / Volver a elegir plan" buttons.
                setPhase('timed_out');
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

                // Cache service_type whenever the session provides it.
                // This lets activateSession use it directly if reconcile fires first.
                if (data.subscription?.service_type && !knownServiceTypeRef.current) {
                    knownServiceTypeRef.current = data.subscription.service_type;
                }

                if (data.status === 'activated' || data.subscription?.is_active) {
                    // Use shared activateSession to avoid duplicate activation
                    // if reconcile already fired simultaneously.
                    void activateSession(data.subscription?.service_type);
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

    async function initiateCheckout(code: string, promoCode?: string | null) {
        // Prevent concurrent calls (React Strict Mode double-mount, user double-click).
        if (initiatingRef.current) return;
        initiatingRef.current = true;

        try {
            const body: Record<string, string> = { plan_code: code };
            if (productCode) body.product_code = productCode;
            if (promoCode) body.promo_code = promoCode;

            const resp = await fetch(`${API_URL}/api/v1/auth/onboarding/start-checkout/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(body),
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
                    initiatingRef.current = false;
                    return;
                }

                setPhase('error');
                setErrorMessage(
                    payload?.detail ?? 'No pudimos iniciar el pago. Intentalo de nuevo.',
                );
                initiatingRef.current = false;
                return;
            }

            const result: StartCheckoutPayload = await resp.json();
            sessionIdRef.current = result.checkout_session_id;
            setInitPoint(result.init_point);

            // If the session is already past checkout_created (user has already
            // been to MP — login recovery after payment), skip payment_ready and
            // go directly to polling. Also trigger a reconciliation so activation
            // does not depend solely on the async webhook.
            const alreadyAtMP = ['awaiting_webhook', 'linked', 'activated'].includes(result.status);
            if (alreadyAtMP) {
                // Trigger reconciliation then start polling.
                // triggerReconcile is fire-and-forget here; polling runs in parallel.
                triggerReconcile(result.checkout_session_id);
                startPolling();
            } else {
                setPhase('payment_ready');
            }
        } catch {
            setPhase('error');
            setErrorMessage('Error de red. Verificá tu conexión e intentalo de nuevo.');
            initiatingRef.current = false;
        }
    }

    // ── Promo code application ─────────────────────────────────────────────────

    async function handleApplyPromo() {
        const code = promoInput.trim().toUpperCase();
        if (!code) return;

        setPromoLoading(true);
        setPromoError('');
        setAppliedPromo(null);

        try {
            const result = await validatePromoCode({ code, plan_code: planCode });
            if (result.valid === true) {
                setAppliedPromo(result);
                setPromoError('');
            } else {
                setPromoError(result.detail);
            }
        } catch {
            setPromoError('No pudimos verificar el código. Intentalo de nuevo.');
        } finally {
            setPromoLoading(false);
        }
    }

    // ── Mount ──────────────────────────────────────────────────────────────────

    useEffect(() => {
        // Wave 5: MP back_url return path — session already exists.
        // 1. Trigger a proactive server-side reconciliation so that activation
        //    does NOT depend solely on the async MP webhook arriving first.
        // 2. Then start polling normally — the reconciliation will have already
        //    activated the subscription if MP confirms the payment.
        if (resumeSessionId) {
            sessionIdRef.current = resumeSessionId;

            // Fire reconcile and start polling in parallel.
            // triggerReconcile handles errors non-destructively — polling continues.
            startPolling();
            triggerReconcile(resumeSessionId);

            return;
        }

        if (!planCode) {
            setPhase('error');
            setErrorMessage('No se especificó ningún plan. Volvé a elegir un plan.');
            return;
        }
        // Show promo input form before initiating checkout.
        setPhase('pre_checkout');
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

            {/* ── Pre-checkout: optional promo code ────────────────────────── */}
            {phase === 'pre_checkout' && (
                <div>
                    <h1 className="text-2xl font-semibold text-slate-900 mb-2">
                        Confirmá tu suscripción
                    </h1>
                    <p className="text-sm text-slate-500 mb-8">
                        Si tenés un código promocional podés aplicarlo antes de ir a Mercado Pago.
                    </p>

                    {/* Promo code input */}
                    <div className="mb-6">
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                            Código promocional <span className="text-slate-400 font-normal">(opcional)</span>
                        </label>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={promoInput}
                                onChange={(e) => {
                                    const val = e.target.value.toUpperCase();
                                    setPromoInput(val);
                                    // Clear applied result when user modifies the input
                                    if (appliedPromo) setAppliedPromo(null);
                                    if (promoError) setPromoError('');
                                }}
                                onKeyDown={(e) => { if (e.key === 'Enter') handleApplyPromo(); }}
                                placeholder="EJEMPLO50"
                                maxLength={64}
                                disabled={promoLoading}
                                className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded-lg
                                           focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent
                                           disabled:opacity-50 uppercase placeholder-slate-400"
                            />
                            <button
                                onClick={handleApplyPromo}
                                disabled={promoLoading || !promoInput.trim()}
                                className="px-4 py-2 text-sm font-medium bg-slate-100 text-slate-700
                                           border border-slate-300 rounded-lg hover:bg-slate-200
                                           transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                                {promoLoading ? (
                                    <span className="inline-block w-4 h-4 border-2 border-slate-400 border-t-slate-700 rounded-full animate-spin" />
                                ) : 'Aplicar'}
                            </button>
                        </div>

                        {/* Promo error */}
                        {promoError && (
                            <p className="mt-2 text-xs text-red-600">{promoError}</p>
                        )}

                        {/* Promo success summary */}
                        {appliedPromo && (
                            <div className="mt-3 rounded-lg border border-green-200 bg-green-50 p-3">
                                <div className="flex items-start justify-between gap-2">
                                    <div>
                                        <p className="text-xs font-semibold text-green-800 mb-0.5">
                                            Código <span className="font-mono">{appliedPromo.code}</span> aplicado
                                        </p>
                                        <p className="text-xs text-green-700">{appliedPromo.summary}</p>
                                    </div>
                                    <button
                                        onClick={() => {
                                            setAppliedPromo(null);
                                            setPromoInput('');
                                            setPromoError('');
                                        }}
                                        className="text-green-600 hover:text-green-900 text-xs shrink-0 mt-0.5"
                                        title="Quitar código"
                                    >
                                        ✕
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* CTA */}
                    <button
                        onClick={() => {
                            setPhase('loading');
                            initiateCheckout(planCode, appliedPromo?.code ?? null);
                        }}
                        className="w-full py-3 px-4 bg-slate-900 text-white text-sm font-medium
                                   rounded-lg hover:bg-slate-800 transition-colors"
                    >
                        {appliedPromo ? 'Ir a Mercado Pago con descuento →' : 'Ir a Mercado Pago →'}
                    </button>

                    <p className="text-xs text-slate-400 mt-4 text-center">
                        Sin código también podés continuar directamente.
                    </p>
                </div>
            )}

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
                    {reconcileWarning ? (
                        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-left max-w-sm mx-auto">
                            <p className="text-sm font-semibold text-amber-800 mb-1">
                                Seguimos verificando tu suscripción
                            </p>
                            <p className="text-xs text-amber-700 mb-3">
                                {reconcileWarning}
                            </p>
                            <button
                                onClick={() => {
                                    const sid = sessionIdRef.current;
                                    if (sid) triggerReconcile(sid);
                                }}
                                disabled={isReconciling}
                                className="text-xs font-medium text-amber-900 underline underline-offset-2 disabled:opacity-60"
                            >
                                {isReconciling ? 'Verificando...' : 'Volver a verificar'}
                            </button>
                        </div>
                    ) : pollingSlowWarning ? (
                        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-left max-w-sm mx-auto">
                            <p className="text-sm font-semibold text-amber-800 mb-1">
                                Esto está tardando más de lo habitual
                            </p>
                            <p className="text-xs text-amber-700">
                                Tu pago puede estar siendo procesado. Podés cerrar esta
                                ventana — te enviaremos un email cuando tu cuenta quede activa.{' '}
                                <strong>No vuelvas a pagar.</strong>
                            </p>
                        </div>
                    ) : (
                        <p className="text-sm text-slate-500">
                            Esto puede tardar unos segundos. No cierres esta ventana.
                        </p>
                    )}
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
                        href={redirectTargetRef.current}
                        className="text-sm font-medium text-slate-900 underline underline-offset-2"
                    >
                        Ir al panel ahora
                    </a>
                </div>
            )}

            {/* ── Timed out (webhook still pending) ────────────────────────── */}
            {phase === 'timed_out' && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-center">
                    <div className="text-4xl mb-4 select-none">⏳</div>
                    <h1 className="text-xl font-semibold text-slate-900 mb-2">
                        Tu pago se está procesando
                    </h1>
                    <p className="text-sm text-amber-800 mb-1">
                        La confirmación de Mercado Pago está tardando más de lo esperado.
                    </p>
                    <p className="text-sm text-slate-700 mb-6">
                        Si el pago ya se debitó,{' '}
                        <strong>no vuelvas a pagar</strong>.
                        Tu cuenta se activará automáticamente cuando Mercado Pago confirme
                        el pago — normalmente en minutos.
                    </p>
                    {reconcileWarning && (
                        <p className="text-xs text-amber-800 mb-4 bg-amber-100 rounded-lg p-3 border border-amber-200">
                            {reconcileWarning}
                        </p>
                    )}
                    <p className="text-xs text-slate-500 mb-4">
                        ¿Necesitás ayuda? Escribinos a{' '}
                        <a
                            href="mailto:soporte@mirubro.com"
                            className="underline text-slate-700 hover:text-slate-900"
                        >
                            soporte@mirubro.com
                        </a>{' '}
                        con tu email y te ayudamos.
                    </p>
                    <div className="flex flex-col items-center gap-3">
                        <button
                            onClick={() => {
                                // Restart polling and trigger a fresh server-side reconcile.
                                // triggerReconcile clears the previous warning automatically.
                                const sid = sessionIdRef.current;
                                setPollingSlowWarning(false);
                                startPolling();
                                if (sid) triggerReconcile(sid);
                            }}
                            disabled={isReconciling}
                            className="px-4 py-2 text-sm font-medium bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                            {isReconciling ? 'Verificando...' : 'Volver a verificar'}
                        </button>
                        <button
                            onClick={() => {
                                setPollingSlowWarning(false);
                                startPolling();
                            }}
                            className="text-sm text-slate-600 underline underline-offset-2 hover:text-slate-900"
                        >
                            Seguir esperando
                        </button>
                    </div>
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
                                    initiateCheckout(planCode, appliedPromo?.code ?? null);
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
                                    initiateCheckout(planCode, appliedPromo?.code ?? null);
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

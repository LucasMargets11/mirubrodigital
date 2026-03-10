'use client';

/**
 * MP back_url return handler — Wave 5.
 *
 * MercadoPago redirects users here after completing (or aborting) a checkout
 * flow.  There are two distinct param shapes depending on which checkout path
 * was used:
 *
 *   checkout_session_id=<uuid>  — Wave 4 onboarding checkout (new path)
 *   intent_id=<id>              — Legacy start-subscription flow (old path)
 *
 * For the new path we immediately redirect the user back into the onboarding
 * checkout page which is already polling for activation.  This reconnects them
 * with the correct state machine without duplicating any polling logic here.
 *
 * For the legacy path the original polling behavior is preserved unchanged.
 */

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { getClientApiBaseUrl } from '@/lib/api-url';
import { Loader2 } from 'lucide-react';

/**
 * Handles Wave 4+ onboarding checkout returns.
 * Triggers router.replace() in an effect to avoid render-phase side-effects.
 */
function OnboardingReturnRedirect({ sessionId }: { sessionId: string }) {
    const router = useRouter();
    useEffect(() => {
        router.replace(`/app/onboarding/checkout?session_id=${encodeURIComponent(sessionId)}`);
    }, [router, sessionId]);

    return (
        <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
            <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
            <p className="text-sm text-slate-600">Verificando tu pago...</p>
        </div>
    );
}

/**
 * Handles the legacy intent_id polling flow unchanged.
 */
function LegacyIntentPoller({ intentId }: { intentId: string | null }) {
    const router = useRouter();
    const [status, setStatus] = useState('Verificando estado del pago...');
    const [isPolling, setIsPolling] = useState(true);

    useEffect(() => {
        if (!intentId) {
            setStatus('No se encontró información del pago.');
            setIsPolling(false);
            return;
        }

        const baseUrl = getClientApiBaseUrl();
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`${baseUrl}/api/v1/billing/intent-status?intent_id=${intentId}`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.active) {
                        clearInterval(interval);
                        setStatus('Pago confirmado. Redirigiendo...');
                        setTimeout(() => {
                            router.push('/entrar');
                        }, 1000);
                    } else if (data.status === 'failed') {
                        setStatus('El pago ha fallado. Por favor intenta nuevamente.');
                        setIsPolling(false);
                        clearInterval(interval);
                    }
                }
            } catch (e) {
                console.error(e);
            }
        }, 2000);

        const timeout = setTimeout(() => {
            clearInterval(interval);
            setStatus('La verificación está tomando más tiempo de lo esperado. Te enviaremos un email cuando tu cuenta esté activa.');
            setIsPolling(false);
        }, 60000);

        return () => {
            clearInterval(interval);
            clearTimeout(timeout);
        };
    }, [intentId, router]);

    return (
        <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
            {isPolling && <Loader2 className="w-8 h-8 animate-spin text-brand-600" />}
            <h1 className="text-xl font-medium text-slate-900">{status}</h1>
            {!isPolling && intentId && (
                <button
                    onClick={() => router.push('/pricing')}
                    className="text-brand-600 hover:underline"
                >
                    Volver a planes
                </button>
            )}
        </div>
    );
}

function ReturnContent() {
    const searchParams = useSearchParams();
    const checkoutSessionId = searchParams.get('checkout_session_id');
    const intentId = searchParams.get('intent_id');

    // Wave 4+ path: reconnect with onboarding checkout polling page.
    if (checkoutSessionId) {
        return <OnboardingReturnRedirect sessionId={checkoutSessionId} />;
    }

    // Legacy path: poll intent-status as before.
    return <LegacyIntentPoller intentId={intentId} />;
}

export default function ReturnPage() {
    return (
        <Suspense fallback={<div>Cargando...</div>}>
            <ReturnContent />
        </Suspense>
    )
}

'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { getClientApiBaseUrl } from '@/lib/api-url';
import { Loader2 } from 'lucide-react';

type AppointmentsCheckoutStatus = {
  checkout_id: string;
  status: 'pending' | 'linked' | 'active' | 'failed' | 'expired';
  plan_code: string;
  usage_tier: string | null;
  billing_cycle: string;
  subscription_status: string | null;
  can_retry: boolean;
  failure_code: string | null;
};

function AppointmentsCheckoutPoller({ checkoutId }: { checkoutId: string }) {
  const router = useRouter();
  const [status, setStatus] = useState<
    AppointmentsCheckoutStatus['status'] | 'timeout' | 'unauthorized' | 'not_found' | 'error'
  >('pending');
  const [canRetry, setCanRetry] = useState(false);
  const [isPolling, setIsPolling] = useState(true);

  useEffect(() => {
    let active = true;
    let inFlight = false;
    const baseUrl = getClientApiBaseUrl();
    const controller = new AbortController();
    const stop = () => {
      active = false;
      clearInterval(interval);
      clearTimeout(timeout);
      controller.abort();
    };

    const poll = async () => {
      if (!active || inFlight) return;
      inFlight = true;
      try {
        const response = await fetch(
          `${baseUrl}/api/v1/billing/appointments/checkouts/${encodeURIComponent(checkoutId)}/status/`,
          { credentials: 'include', signal: controller.signal },
        );
        if (!active) return;
        if (response.status === 401 || response.status === 403) {
          stop();
          setStatus('unauthorized');
          setIsPolling(false);
          return;
        }
        if (response.status === 404) {
          stop();
          setStatus('not_found');
          setIsPolling(false);
          return;
        }
        if (!response.ok) return;

        const data = (await response.json()) as AppointmentsCheckoutStatus;
        if (!active) return;
        setCanRetry(data.can_retry);
        setStatus(data.status);
        if (data.status === 'active' || data.status === 'failed' || data.status === 'expired') {
          stop();
          setIsPolling(false);
        }
      } catch {
        // Transient network errors leave server state authoritative until the UI timeout.
      } finally {
        inFlight = false;
      }
    };

    void poll();
    const interval = setInterval(() => void poll(), 2000);
    const timeout = setTimeout(() => {
      if (!active) return;
      stop();
      setStatus('timeout');
      setIsPolling(false);
    }, 60000);

    return stop;
  }, [checkoutId]);

  const retryToPricing = () => router.push('/pricing?service=appointments');

  let message = 'Estamos confirmando tu pago.';
  if (status === 'linked')
    message = 'Tu suscripción fue vinculada. Estamos esperando confirmación del pago.';
  if (status === 'active') message = 'Tu plan de Turnos está activo.';
  if (status === 'failed') message = 'No pudimos completar la contratación.';
  if (status === 'expired') message = 'El intento de contratación venció.';
  if (status === 'timeout') message = 'Seguimos procesando la confirmación.';
  if (status === 'unauthorized')
    message = 'Iniciá sesión como propietario del negocio para consultar este intento.';
  if (status === 'not_found')
    message = 'No encontramos este intento de contratación para tu negocio.';
  if (status === 'error') message = 'No pudimos consultar el estado de la contratación.';

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 px-4 text-center">
      {isPolling && <Loader2 className="h-8 w-8 animate-spin text-brand-600" />}
      <h1 className="text-xl font-medium text-slate-900" data-testid="appointments-return-state">
        {message}
      </h1>
      {status === 'active' && (
        <button
          onClick={() => router.push('/app/turnos?onboarding=1')}
          className="text-brand-600 hover:underline"
        >
          Configurar Turnos
        </button>
      )}
      {status === 'failed' && (
        <div className="flex flex-wrap justify-center gap-4">
          {canRetry && (
            <button onClick={retryToPricing} className="text-brand-600 hover:underline">
              Reintentar contratación
            </button>
          )}
          <button
            onClick={() => router.push('/contacto')}
            className="text-brand-600 hover:underline"
          >
            Contactar soporte
          </button>
        </div>
      )}
      {status === 'expired' && (
        <div className="flex flex-wrap justify-center gap-4">
          <button onClick={retryToPricing} className="text-brand-600 hover:underline">
            Volver a planes de Turnos
          </button>
          <button
            onClick={() => router.push('/contacto')}
            className="text-brand-600 hover:underline"
          >
            Contactar soporte
          </button>
        </div>
      )}
      {(status === 'unauthorized' ||
        status === 'not_found' ||
        status === 'timeout' ||
        status === 'error') && (
        <button
          onClick={() =>
            router.push(status === 'unauthorized' ? '/entrar' : '/pricing?service=appointments')
          }
          className="text-brand-600 hover:underline"
        >
          {status === 'unauthorized' ? 'Iniciar sesión' : 'Volver a planes'}
        </button>
      )}
    </div>
  );
}

function OnboardingReturnRedirect({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  useEffect(() => {
    router.replace(`/app/onboarding/checkout?session_id=${encodeURIComponent(sessionId)}`);
  }, [router, sessionId]);

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4">
      <Loader2 className="h-8 w-8 animate-spin text-brand-600" />
      <p className="text-sm text-slate-600">Verificando tu pago...</p>
    </div>
  );
}

function LegacyIntentPoller({ intentId }: { intentId: string | null }) {
  const router = useRouter();
  const [status, setStatus] = useState('Verificando estado del pago...');
  const [isPolling, setIsPolling] = useState(true);

  useEffect(() => {
    if (!intentId) {
      return;
    }

    const baseUrl = getClientApiBaseUrl();
    const interval = setInterval(async () => {
      try {
        const res = await fetch(
          `${baseUrl}/api/v1/billing/intent-status?intent_id=${encodeURIComponent(intentId)}`,
        );
        if (res.ok) {
          const data = await res.json();
          if (data.active) {
            clearInterval(interval);
            setStatus('Pago confirmado. Redirigiendo...');
            setTimeout(() => router.push('/entrar'), 1000);
          } else if (data.status === 'failed') {
            setStatus('El pago ha fallado. Por favor intenta nuevamente.');
            setIsPolling(false);
            clearInterval(interval);
          }
        }
      } catch (error) {
        console.error(error);
      }
    }, 2000);

    const timeout = setTimeout(() => {
      clearInterval(interval);
      setStatus(
        'La verificación está tomando más tiempo de lo esperado. Te enviaremos un email cuando tu cuenta esté activa.',
      );
      setIsPolling(false);
    }, 60000);

    return () => {
      clearInterval(interval);
      clearTimeout(timeout);
    };
  }, [intentId, router]);

  const displayStatus = intentId ? status : 'No se encontró información del pago.';

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center space-y-4">
      {isPolling && intentId && <Loader2 className="h-8 w-8 animate-spin text-brand-600" />}
      <h1 className="text-xl font-medium text-slate-900">{displayStatus}</h1>
      {!isPolling && intentId && (
        <button onClick={() => router.push('/pricing')} className="text-brand-600 hover:underline">
          Volver a planes
        </button>
      )}
    </div>
  );
}

function ReturnContent() {
  const searchParams = useSearchParams();
  const appointmentsCheckoutId = searchParams.get('appointments_checkout_id');
  const checkoutSessionId = searchParams.get('checkout_session_id');
  const intentId = searchParams.get('intent_id');

  if (appointmentsCheckoutId) {
    return <AppointmentsCheckoutPoller checkoutId={appointmentsCheckoutId} />;
  }
  if (checkoutSessionId) {
    return <OnboardingReturnRedirect sessionId={checkoutSessionId} />;
  }
  return <LegacyIntentPoller intentId={intentId} />;
}

export default function ReturnPage() {
  return (
    <Suspense fallback={<div>Cargando...</div>}>
      <ReturnContent />
    </Suspense>
  );
}

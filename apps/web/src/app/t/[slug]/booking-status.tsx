'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { PublicAppointmentBooking } from '@/features/appointments/types';
import {
    BOOKING_POLL_INTERVAL_MS,
    BOOKING_POLL_TIMEOUT_MS,
    deriveBookingView,
    fetchPublicBooking,
    isHoldActive,
    openWhatsapp,
    redirectToCheckout,
    shouldPollBooking,
    startPublicCheckout,
    whatsappContactUrl,
    type PaymentReturnHint,
} from '@/features/appointments/public-booking';

interface Props {
    apiUrl: string;
    slug: string;
    publicToken: string;
    /** Reserva recién creada (evita un GET extra). Sin ella se consulta el backend. */
    initialBooking?: PublicAppointmentBooking | null;
    /** `payment=` de la back URL de Mercado Pago: SOLO afecta el texto de carga. */
    paymentHint?: PaymentReturnHint | null;
    onRestart: () => void;
}

type LoadState = 'loading' | 'ready' | 'not_found' | 'error';

function formatPrice(price: string): string {
    const value = Number(price);
    if (Number.isNaN(value)) return price;
    return `$ ${value.toLocaleString('es-AR')}`;
}

function formatDateDisplay(isoDate: string): string {
    const [year, month, day] = isoDate.split('-');
    return `${day}/${month}/${year}`;
}

function formatCountdown(seconds: number): string {
    const mm = Math.floor(seconds / 60)
        .toString()
        .padStart(2, '0');
    const ss = (seconds % 60).toString().padStart(2, '0');
    return `${mm}:${ss}`;
}

/**
 * Pantalla "Estado de tu reserva" (Slice 4B hold + Slice 6C checkout/retorno).
 *
 * Todo lo que se muestra sale de `GET .../bookings/<public_token>/`. Ver
 * `features/appointments/public-booking.ts` para las reglas de derivación.
 */
export function BookingStatus({ apiUrl, slug, publicToken, initialBooking, paymentHint, onRestart }: Props) {
    const [booking, setBooking] = useState<PublicAppointmentBooking | null>(initialBooking ?? null);
    const [loadState, setLoadState] = useState<LoadState>(initialBooking ? 'ready' : 'loading');
    const [refreshing, setRefreshing] = useState(false);
    const [pollExhausted, setPollExhausted] = useState(false);
    const [checkoutBusy, setCheckoutBusy] = useState(false);
    const [notice, setNotice] = useState('');
    const [secondsLeft, setSecondsLeft] = useState<number | null>(null);

    // Guard síncrono contra doble click (el estado de React llega un render tarde).
    const checkoutInFlight = useRef(false);
    // Descarta respuestas viejas si se superponen dos GET.
    const loadSeq = useRef(0);

    const load = useCallback(async (): Promise<PublicAppointmentBooking | null> => {
        const seq = ++loadSeq.current;
        const result = await fetchPublicBooking(apiUrl, slug, publicToken);
        if (seq !== loadSeq.current) return null;
        if (result.kind === 'ok') {
            setBooking(result.booking);
            setLoadState('ready');
        } else if (result.kind === 'not_found') {
            setBooking(null);
            setLoadState('not_found');
        } else {
            // Si ya había datos, se conservan; el próximo intento puede funcionar.
            setLoadState((prev) => (prev === 'ready' ? prev : 'error'));
        }
        return result.kind === 'ok' ? result.booking : null;
    }, [apiUrl, slug, publicToken]);

    // Restauración por `?booking=`: siempre se consulta el backend.
    // (El setState ocurre después del fetch, no sincrónicamente.)
    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        if (!initialBooking) void load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [load]);

    // Volver atrás desde Mercado Pago puede restaurar la página desde bfcache con
    // el botón en "Redirigiendo…": se libera y se re-consulta el estado real.
    useEffect(() => {
        const onPageShow = (event: PageTransitionEvent) => {
            if (!event.persisted) return;
            checkoutInFlight.current = false;
            setCheckoutBusy(false);
            void load();
        };
        window.addEventListener('pageshow', onPageShow);
        return () => window.removeEventListener('pageshow', onPageShow);
    }, [load]);

    // Arranque / corte del polling: derivado del estado real del backend.
    const polling = booking !== null && shouldPollBooking(booking) && !pollExhausted;

    // Polling acotado: cada BOOKING_POLL_INTERVAL_MS hasta BOOKING_POLL_TIMEOUT_MS.
    useEffect(() => {
        if (!polling) return;
        const deadline = Date.now() + BOOKING_POLL_TIMEOUT_MS;
        let inFlight = false;
        const id = setInterval(async () => {
            if (Date.now() >= deadline) {
                clearInterval(id);
                setPollExhausted(true);
                return;
            }
            if (inFlight) return;
            inFlight = true;
            try {
                await load();
            } finally {
                inFlight = false;
            }
        }, BOOKING_POLL_INTERVAL_MS);
        return () => clearInterval(id);
    }, [polling, load]);

    // Countdown del hold: siempre desde `expires_at` del backend; al llegar a 0
    // se re-consulta (el backend decide si venció).
    const holdExpiresAt = booking?.status === 'pending_payment' ? booking.expires_at : null;
    useEffect(() => {
        if (!holdExpiresAt) return;
        const expiresAt = new Date(holdExpiresAt).getTime();
        let fired = false;
        const tick = () => {
            const remaining = Math.max(0, Math.round((expiresAt - Date.now()) / 1000));
            setSecondsLeft(remaining);
            if (remaining <= 0 && !fired) {
                fired = true;
                clearInterval(interval);
                void load();
            }
        };
        const interval = setInterval(tick, 1000);
        tick();
        return () => clearInterval(interval);
    }, [holdExpiresAt, load]);

    async function handleRefresh() {
        if (refreshing) return;
        setRefreshing(true);
        setNotice('');
        try {
            await load();
        } finally {
            setRefreshing(false);
        }
    }

    /**
     * Inicia el checkout. En un reintento (`refetchFirst`) primero se vuelve a
     * consultar el backend y solo se hace el POST si el estado actual sigue
     * siendo inequívocamente reintentable (rejected/cancelled/error con hold
     * vigente); si no, la pantalla simplemente pasa al estado nuevo.
     */
    async function runCheckout({ refetchFirst }: { refetchFirst: boolean }) {
        if (checkoutInFlight.current) return;
        checkoutInFlight.current = true;
        setCheckoutBusy(true);
        setNotice('');

        if (refetchFirst) {
            const fresh = await load();
            if (!fresh || deriveBookingView(fresh) !== 'payment_failed' || !isHoldActive(fresh)) {
                checkoutInFlight.current = false;
                setCheckoutBusy(false);
                return;
            }
        }

        const result = await startPublicCheckout(apiUrl, slug, publicToken);

        if (result.kind === 'redirect') {
            // El botón queda deshabilitado mientras el navegador sale del sitio.
            redirectToCheckout(result.checkoutUrl);
            return;
        }

        if (result.kind === 'not_found') {
            setBooking(null);
            setLoadState('not_found');
        } else {
            switch (result.code) {
                case 'payment_unavailable':
                    setNotice('No pudimos iniciar el pago en este momento.');
                    break;
                case 'payment_provider_error':
                case 'unknown':
                    setNotice('No pudimos iniciar el pago. Revisá el estado de tu reserva e intentá nuevamente.');
                    break;
                // expired / not_payable / payment_in_progress / payment_uncertain:
                // el estado actualizado del backend alcanza para explicar qué pasó.
                default:
                    break;
            }
            // Nunca inferir el siguiente paso del código HTTP: el backend decide.
            await load();
        }

        checkoutInFlight.current = false;
        setCheckoutBusy(false);
    }

    if (loadState === 'loading') {
        return (
            <div role="status" aria-live="polite" className="space-y-2">
                <p className="text-sm text-slate-500 animate-pulse">
                    {paymentHint ? 'Estamos verificando el estado de tu pago…' : 'Cargando tu reserva…'}
                </p>
            </div>
        );
    }

    if (loadState === 'not_found') {
        return (
            <>
                <h2 className="text-lg font-semibold text-slate-800">No encontramos tu reserva</h2>
                <p className="text-sm text-slate-500">
                    El enlace no es válido o la reserva no pertenece a este negocio.
                </p>
                <PrimaryButton onClick={onRestart}>Hacer una reserva</PrimaryButton>
            </>
        );
    }

    if (loadState === 'error' || !booking) {
        return (
            <>
                <h2 className="text-lg font-semibold text-slate-800">No pudimos cargar tu reserva</h2>
                <p className="text-sm text-slate-500">Revisá tu conexión e intentá de nuevo.</p>
                <RefreshButton refreshing={refreshing} onClick={handleRefresh} />
            </>
        );
    }

    const view = deriveBookingView(booking);
    const holdActive = isHoldActive(booking);
    const summary = <BookingSummary booking={booking} tone={view === 'confirmed' ? 'success' : 'neutral'} />;
    const countdown =
        holdActive && secondsLeft !== null ? (
            <p className="text-center text-2xl font-semibold tabular-nums text-amber-700" aria-label="Tiempo restante">
                {formatCountdown(secondsLeft)}
            </p>
        ) : null;
    const noticeBanner = notice ? <Banner tone="error">{notice}</Banner> : null;
    // Slice 6D: el backend solo entrega el link en confirmed / requires_review.
    const whatsappUrl = whatsappContactUrl(booking);

    switch (view) {
        case 'confirmed':
            return (
                <>
                    <h2 className="text-lg font-semibold text-emerald-700">Tu turno está confirmado.</h2>
                    {summary}
                    {whatsappUrl && <WhatsappButton url={whatsappUrl} label="Abrir WhatsApp" />}
                    <SecondaryButton onClick={onRestart}>Hacer otra reserva</SecondaryButton>
                </>
            );

        case 'requires_review':
            return (
                <>
                    <h2 className="text-lg font-semibold text-amber-700">Estamos revisando tu reserva</h2>
                    <Banner tone="info">
                        El pago fue recibido, pero necesitamos revisar la reserva antes de confirmarla. No hace
                        falta que pagues de nuevo: el negocio se va a comunicar con vos.
                    </Banner>
                    {summary}
                    <p className="text-xs text-slate-400">
                        Guardá este enlace para volver a consultar el estado de tu reserva.
                    </p>
                    {whatsappUrl && <WhatsappButton url={whatsappUrl} label="Contactar al negocio" />}
                    <RefreshButton refreshing={refreshing} onClick={handleRefresh} />
                </>
            );

        case 'expired':
            if (polling) {
                return <Processing summary={summary} />;
            }
            return (
                <>
                    <h2 className="text-lg font-semibold text-red-700">Tu reserva venció</h2>
                    <p className="text-sm text-slate-500">
                        El tiempo para completar la reserva venció y el horario volvió a estar disponible.
                    </p>
                    {pollExhausted && (
                        <p className="text-xs text-slate-400">
                            Si ya realizaste el pago, puede tardar unos instantes en verse reflejado.
                        </p>
                    )}
                    <PrimaryButton onClick={onRestart}>Elegir otro horario</PrimaryButton>
                    {pollExhausted && <RefreshButton refreshing={refreshing} onClick={handleRefresh} />}
                </>
            );

        case 'cancelled':
            return (
                <>
                    <h2 className="text-lg font-semibold text-slate-800">La reserva fue cancelada</h2>
                    {summary}
                    <PrimaryButton onClick={onRestart}>Hacer una nueva reserva</PrimaryButton>
                </>
            );

        case 'inactive':
            return (
                <>
                    <h2 className="text-lg font-semibold text-slate-800">Esta reserva ya no está activa</h2>
                    {summary}
                    <SecondaryButton onClick={onRestart}>Hacer otra reserva</SecondaryButton>
                </>
            );

        case 'verifying':
            return (
                <>
                    <h2 className="text-lg font-semibold text-amber-700">Estamos verificando el estado del pago</h2>
                    <p className="text-sm text-slate-500">
                        No realices otro pago por ahora. Si el problema continúa, comunicate con el negocio.
                    </p>
                    {summary}
                    {noticeBanner}
                    <RefreshButton refreshing={refreshing} onClick={handleRefresh} />
                </>
            );

        case 'payment_pending':
            if (polling) {
                return <Processing summary={summary} />;
            }
            return (
                <>
                    <h2 className="text-lg font-semibold text-amber-700">
                        Estamos esperando la confirmación del pago.
                    </h2>
                    <p className="text-sm text-slate-500">
                        Puede tardar unos instantes. Si ya pagaste, no hace falta que pagues de nuevo.
                    </p>
                    {summary}
                    {countdown}
                    {noticeBanner}
                    {/* Sin checkout acá: el cliente pudo haber pagado y el webhook
                        todavía no llegó. Solo polling + consulta manual (GET). */}
                    <RefreshButton refreshing={refreshing} onClick={handleRefresh} primary />
                </>
            );

        case 'payment_failed':
            return (
                <>
                    <h2 className="text-lg font-semibold text-red-700">El pago no se completó</h2>
                    {summary}
                    {countdown}
                    {noticeBanner}
                    {holdActive ? (
                        <CheckoutButton
                            busy={checkoutBusy}
                            onClick={() => runCheckout({ refetchFirst: true })}
                            label="Intentar nuevamente"
                        />
                    ) : (
                        <PrimaryButton onClick={onRestart}>Elegir otro horario</PrimaryButton>
                    )}
                </>
            );

        case 'awaiting_checkout':
        default:
            return (
                <>
                    <h2 className="text-lg font-semibold text-amber-700">Tu horario está reservado temporalmente</h2>
                    {summary}
                    {countdown}
                    <p className="text-center text-xs text-slate-400">
                        Completá el pago de la seña antes de que termine el tiempo para no perder el horario.
                    </p>
                    {noticeBanner}
                    {holdActive ? (
                        <CheckoutButton
                            busy={checkoutBusy}
                            onClick={() => runCheckout({ refetchFirst: false })}
                            label="Continuar al pago"
                        />
                    ) : (
                        <RefreshButton refreshing={refreshing} onClick={handleRefresh} />
                    )}
                </>
            );
    }
}

/* ── Piezas de UI ──────────────────────────────────────────────────────── */

function BookingSummary({ booking, tone }: { booking: PublicAppointmentBooking; tone: 'success' | 'neutral' }) {
    const hasDeposit = Number(booking.deposit_amount) > 0;
    return (
        <div
            className={
                tone === 'success'
                    ? 'space-y-2 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-left shadow-sm'
                    : 'space-y-2 rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm'
            }
        >
            <p className="font-semibold text-slate-800">{booking.service.name}</p>
            {booking.professional && <p className="text-sm text-slate-600">{booking.professional.name}</p>}
            <p className="text-sm text-slate-600">
                {formatDateDisplay(booking.start_at.slice(0, 10))} · {booking.start_at.slice(11, 16)}
            </p>
            {tone !== 'success' && hasDeposit && (
                <p className="text-sm font-semibold text-amber-700">Seña: {formatPrice(booking.deposit_amount)}</p>
            )}
        </div>
    );
}

function Processing({ summary }: { summary: React.ReactNode }) {
    return (
        <>
            <div role="status" aria-live="polite" className="space-y-1">
                <h2 className="text-lg font-semibold text-slate-800">Procesando tu pago…</h2>
                <p className="text-sm text-slate-500 animate-pulse">
                    Estamos esperando la confirmación de Mercado Pago. No cierres esta página.
                </p>
            </div>
            {summary}
        </>
    );
}

function Banner({ tone, children }: { tone: 'error' | 'info'; children: React.ReactNode }) {
    return (
        <div
            role={tone === 'error' ? 'alert' : 'status'}
            className={
                tone === 'error'
                    ? 'rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-100'
                    : 'rounded-xl bg-amber-50 px-4 py-3 text-left text-sm text-amber-800 ring-1 ring-amber-200'
            }
        >
            {children}
        </div>
    );
}

const primaryClassName =
    'w-full rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500';
const secondaryClassName =
    'w-full rounded-full border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-slate-600 shadow-sm transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300';

function PrimaryButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
    return (
        <button type="button" onClick={onClick} className={primaryClassName}>
            {children}
        </button>
    );
}

function SecondaryButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
    return (
        <button type="button" onClick={onClick} className={secondaryClassName}>
            {children}
        </button>
    );
}

/** Abre WhatsApp solo al tocarlo; el cliente decide si envía el mensaje. */
function WhatsappButton({ url, label }: { url: string; label: string }) {
    return (
        <button type="button" onClick={() => openWhatsapp(url)} className={secondaryClassName}>
            {label}
        </button>
    );
}

function CheckoutButton({ busy, onClick, label }: { busy: boolean; onClick: () => void; label: string }) {
    return (
        <button type="button" onClick={onClick} disabled={busy} aria-busy={busy} className={primaryClassName}>
            {busy ? 'Redirigiendo a Mercado Pago…' : label}
        </button>
    );
}

function RefreshButton({
    refreshing,
    onClick,
    primary = false,
}: {
    refreshing: boolean;
    onClick: () => void;
    primary?: boolean;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={refreshing}
            aria-busy={refreshing}
            className={primary ? primaryClassName : secondaryClassName}
        >
            {refreshing ? 'Actualizando…' : 'Actualizar estado'}
        </button>
    );
}

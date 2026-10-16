/* ── Estado público de reserva + checkout de seña (Slice 6C) ─────────────
 *
 * Lógica pura (sin React) de la pantalla "Estado de tu reserva" de `/t/[slug]`.
 *
 * Reglas:
 * - La fuente de verdad es SIEMPRE `GET .../bookings/<public_token>/`. La query
 *   `payment=success|pending|failure` de las back URLs de Mercado Pago es solo
 *   una pista visual y nunca decide el estado.
 * - El checkout se inicia con `POST .../checkout/` con body vacío: el frontend
 *   solo conoce `slug` + `public_token`. Monto, referencia y reintentos los
 *   decide el backend.
 * - El `public_token` es una credencial de la reserva: no se loguea ni se
 *   envía a terceros.
 */
import type {
    PublicAppointmentBooking,
    PublicAppointmentCheckout,
    PublicAppointmentCheckoutErrorCode,
} from './types';

/** Intervalo entre consultas mientras se espera el webhook de Mercado Pago. */
export const BOOKING_POLL_INTERVAL_MS = 2_500;
/** Duración máxima del polling automático (después: "Actualizar estado" manual). */
export const BOOKING_POLL_TIMEOUT_MS = 45_000;

export type PaymentReturnHint = 'success' | 'pending' | 'failure';

export function parsePaymentHint(value: string | null | undefined): PaymentReturnHint | null {
    return value === 'success' || value === 'pending' || value === 'failure' ? value : null;
}

/** Vista a renderizar, derivada únicamente de la respuesta del backend. */
export type BookingView =
    | 'confirmed'
    | 'awaiting_checkout'
    | 'payment_pending'
    | 'payment_failed'
    | 'verifying'
    | 'requires_review'
    | 'expired'
    | 'cancelled'
    | 'inactive';

const PENDING_PAYMENT_STATUSES = new Set(['creating', 'pending']);
const RETRYABLE_PAYMENT_STATUSES = new Set(['rejected', 'cancelled', 'error']);

export function deriveBookingView(booking: PublicAppointmentBooking): BookingView {
    const payment = booking.payment_status ?? null;

    // Dinero cobrado pero no aplicado: nunca "confirmado", nunca "pagá otra vez".
    if (payment === 'requires_review' && booking.status !== 'confirmed') {
        return 'requires_review';
    }

    switch (booking.status) {
        case 'confirmed':
            return 'confirmed';
        case 'expired':
            return 'expired';
        case 'cancelled':
            return 'cancelled';
        case 'completed':
        case 'no_show':
            return 'inactive';
        case 'pending_payment':
            break;
        default:
            return 'inactive';
    }

    if (payment === null) return 'awaiting_checkout';
    if (payment === 'uncertain') return 'verifying';
    if (RETRYABLE_PAYMENT_STATUSES.has(payment)) return 'payment_failed';
    // creating / pending / approved-sin-aplicar-todavía: esperar al webhook.
    return 'payment_pending';
}

/**
 * ¿Conviene seguir consultando? Solo mientras el webhook todavía puede
 * cambiar el resultado: intento `creating`/`pending` (o `approved` sin
 * reflejarse aún) sobre un turno no confirmado. Incluye `expired` porque un
 * pago aprobado dentro del hold puede confirmar el turno aunque el webhook
 * llegue tarde (Slice 6B).
 */
export function shouldPollBooking(booking: PublicAppointmentBooking): boolean {
    if (booking.status !== 'pending_payment' && booking.status !== 'expired') return false;
    const payment = booking.payment_status ?? null;
    return payment !== null && (PENDING_PAYMENT_STATUSES.has(payment) || payment === 'approved');
}

export function isHoldActive(booking: PublicAppointmentBooking, now: number = Date.now()): boolean {
    if (booking.status !== 'pending_payment' || !booking.expires_at) return false;
    return new Date(booking.expires_at).getTime() > now;
}

/* ── HTTP ────────────────────────────────────────────────────────────────── */

export type FetchBookingResult =
    | { kind: 'ok'; booking: PublicAppointmentBooking }
    | { kind: 'not_found' }
    | { kind: 'error' };

function bookingUrl(apiUrl: string, slug: string, publicToken: string): string {
    return `${apiUrl}/api/v1/appointments/public/${encodeURIComponent(slug)}/bookings/${encodeURIComponent(publicToken)}/`;
}

export async function fetchPublicBooking(
    apiUrl: string,
    slug: string,
    publicToken: string,
): Promise<FetchBookingResult> {
    try {
        const res = await fetch(bookingUrl(apiUrl, slug, publicToken), { cache: 'no-store' });
        if (res.status === 404) return { kind: 'not_found' };
        if (!res.ok) return { kind: 'error' };
        return { kind: 'ok', booking: (await res.json()) as PublicAppointmentBooking };
    } catch {
        return { kind: 'error' };
    }
}

export type CheckoutResult =
    | { kind: 'redirect'; checkoutUrl: string }
    | { kind: 'not_found' }
    | { kind: 'error'; code: PublicAppointmentCheckoutErrorCode | 'unknown' };

const KNOWN_CHECKOUT_ERRORS: ReadonlySet<string> = new Set<PublicAppointmentCheckoutErrorCode>([
    'not_payable',
    'expired',
    'payment_in_progress',
    'payment_unavailable',
    'payment_provider_error',
    'payment_uncertain',
]);

function isSafeCheckoutUrl(value: unknown): value is string {
    if (typeof value !== 'string') return false;
    try {
        const url = new URL(value);
        return url.protocol === 'https:' || url.protocol === 'http:';
    } catch {
        return false;
    }
}

export async function startPublicCheckout(
    apiUrl: string,
    slug: string,
    publicToken: string,
): Promise<CheckoutResult> {
    try {
        // Body vacío a propósito: nada financiero sale del navegador.
        const res = await fetch(`${bookingUrl(apiUrl, slug, publicToken)}checkout/`, { method: 'POST' });
        if (res.status === 404) return { kind: 'not_found' };
        const data = (await res.json().catch(() => null)) as
            | Partial<PublicAppointmentCheckout>
            | { code?: string }
            | null;
        if (res.ok) {
            const checkoutUrl = data && 'checkout_url' in data ? data.checkout_url : undefined;
            return isSafeCheckoutUrl(checkoutUrl)
                ? { kind: 'redirect', checkoutUrl }
                : { kind: 'error', code: 'unknown' };
        }
        const code = data && 'code' in data ? data.code : undefined;
        return {
            kind: 'error',
            code: code && KNOWN_CHECKOUT_ERRORS.has(code) ? (code as PublicAppointmentCheckoutErrorCode) : 'unknown',
        };
    } catch {
        return { kind: 'error', code: 'unknown' };
    }
}

/** Navegación externa al checkout (misma pestaña). Aislado para poder testearlo. */
export function redirectToCheckout(checkoutUrl: string): void {
    window.location.assign(checkoutUrl);
}

/**
 * Deja en la URL solo `?booking=<public_token>` (sin la pista `payment=`),
 * para que refresh / volver atrás restauren el estado desde el backend.
 * `null` limpia la query (volver a empezar).
 */
export function syncBookingQuery(publicToken: string | null): void {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    url.search = publicToken ? `?${new URLSearchParams({ booking: publicToken }).toString()}` : '';
    window.history.replaceState(window.history.state, '', url.toString());
}

/* ── Contacto manual por WhatsApp (Slice 6D) ─────────────────────────────── */

const WHATSAPP_URL_PREFIX = 'https://wa.me/';

/**
 * Link de WhatsApp a mostrar, o null. El backend ya arma y valida la URL;
 * acá solo se acepta `https://wa.me/...` (defensa en profundidad: nunca
 * `javascript:`, `data:` ni otro host).
 */
export function whatsappContactUrl(booking: PublicAppointmentBooking): string | null {
    const url = booking.contact_whatsapp_url;
    if (typeof url !== 'string' || !url.startsWith(WHATSAPP_URL_PREFIX)) return null;
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'https:' && parsed.host === 'wa.me' ? parsed.toString() : null;
    } catch {
        return null;
    }
}

/** Abre WhatsApp en otra pestaña. Solo se llama desde un click del cliente. */
export function openWhatsapp(url: string): void {
    window.open(url, '_blank', 'noopener,noreferrer');
}

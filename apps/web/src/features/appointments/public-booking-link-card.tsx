'use client';

import { useEffect, useRef, useState } from 'react';

import type { PublicBookingPage } from '@/lib/auth/types';

const UNAVAILABLE_MESSAGES: Record<string, string> = {
    missing_slug: 'La página pública todavía no está disponible.',
    not_publishable: 'La página pública no está disponible mientras tu negocio no esté activo.',
    service_disabled: 'Turnos no está habilitado para este negocio.',
};

function unavailableMessage(page: PublicBookingPage | null | undefined): string {
    // `null` = la sesión no tiene Turnos habilitado.
    if (!page) return UNAVAILABLE_MESSAGES.service_disabled;
    return UNAVAILABLE_MESSAGES[page.reason ?? ''] ?? UNAVAILABLE_MESSAGES.missing_slug;
}

/**
 * La URL la arma el backend (base pública canónica + `Business.slug`) con la
 * misma regla que `/t/<slug>`. Acá solo se valida que sea http(s) y apunte a
 * `/t/…` antes de volverla accionable; nunca se construye en el cliente.
 */
export function usablePublicBookingUrl(page: PublicBookingPage | null | undefined): string | null {
    if (!page?.available || !page.url) return null;
    try {
        const parsed = new URL(page.url);
        if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return null;
        if (!/^\/t\/[^/]+\/?$/.test(parsed.pathname)) return null;
        return page.url;
    } catch {
        return null;
    }
}

type Props = {
    publicBooking: PublicBookingPage | null | undefined;
};

export function PublicBookingLinkCard({ publicBooking }: Props) {
    const url = usablePublicBookingUrl(publicBooking);
    const [feedback, setFeedback] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(() => () => {
        if (timer.current) clearTimeout(timer.current);
    }, []);

    function showFeedback(kind: 'ok' | 'error', text: string) {
        setFeedback({ kind, text });
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => setFeedback(null), 2500);
    }

    async function handleCopy() {
        if (!url) return;
        try {
            if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
            await navigator.clipboard.writeText(url);
            showFeedback('ok', 'Enlace copiado');
        } catch {
            showFeedback('error', 'No pudimos copiar el enlace. Copialo manualmente.');
        }
    }

    return (
        <section
            aria-labelledby="public-booking-title"
            className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
        >
            <div>
                <h2 id="public-booking-title" className="text-sm font-semibold text-slate-800">
                    Página de reservas
                </h2>
                <p className="text-xs text-slate-500">
                    Compartí este enlace para que tus clientes puedan reservar un turno.
                </p>
            </div>

            {url ? (
                <>
                    <p
                        data-testid="public-booking-url"
                        className="break-all rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-sm text-slate-700 select-all"
                    >
                        {url}
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                        <button
                            type="button"
                            onClick={handleCopy}
                            className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
                        >
                            Copiar enlace
                        </button>
                        <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                        >
                            Abrir página
                        </a>
                        {feedback && (
                            <span
                                role="status"
                                className={feedback.kind === 'ok' ? 'text-xs text-emerald-600' : 'text-xs text-rose-600'}
                            >
                                {feedback.text}
                            </span>
                        )}
                    </div>
                </>
            ) : (
                <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-500">
                    {unavailableMessage(publicBooking)}
                </p>
            )}
        </section>
    );
}

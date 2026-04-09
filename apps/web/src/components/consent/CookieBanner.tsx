'use client';

import { usePathname } from 'next/navigation';
import { useConsent } from '@/lib/consent/ConsentProvider';
import { COMPACT_BANNER_ROUTES, SUPPRESSED_ROUTES } from '@/lib/consent/constants';
import { ConsentModal } from './ConsentModal';

export function CookieBanner() {
    const {
        ready,
        hasConsented,
        acceptAll,
        rejectNonEssential,
        openPreferences,
        isPreferencesOpen,
    } = useConsent();
    const pathname = usePathname();

    // Don't render anything until mount (avoids hydration mismatch).
    if (!ready) return null;

    // Already consented → only render modal if open.
    if (hasConsented) {
        return isPreferencesOpen ? <ConsentModal /> : null;
    }

    // Suppress on operational routes.
    const suppressed = SUPPRESSED_ROUTES.some((p) => pathname.startsWith(p));
    if (suppressed) return null;

    const compact = COMPACT_BANNER_ROUTES.some((p) => pathname.startsWith(p));

    return (
        <>
            {/* Backdrop */}
            <div className="fixed inset-0 z-[9998] bg-black/20 pointer-events-none" aria-hidden />

            <div
                role="dialog"
                aria-label="Preferencias de cookies"
                className={`fixed bottom-0 inset-x-0 z-[9999] ${compact ? 'px-3 pb-3' : 'px-4 pb-4 sm:px-6 sm:pb-6'}`}
            >
                <div
                    className={`mx-auto rounded-xl border border-slate-200 bg-white shadow-lg ${compact ? 'max-w-md p-3' : 'max-w-2xl p-4 sm:p-5'}`}
                >
                    {compact ? (
                        <CompactBanner
                            onAccept={acceptAll}
                            onReject={rejectNonEssential}
                            onCustomize={openPreferences}
                        />
                    ) : (
                        <FullBanner
                            onAccept={acceptAll}
                            onReject={rejectNonEssential}
                            onCustomize={openPreferences}
                        />
                    )}
                </div>
            </div>

            {isPreferencesOpen && <ConsentModal />}
        </>
    );
}

/* ── Full banner (marketing, auth, r/*) ─────────────────────────── */

function FullBanner({
    onAccept,
    onReject,
    onCustomize,
}: {
    onAccept: () => void;
    onReject: () => void;
    onCustomize: () => void;
}) {
    return (
        <>
            <p className="text-sm text-slate-700 leading-relaxed">
                Usamos cookies para mejorar tu experiencia. Las cookies necesarias son
                imprescindibles para el funcionamiento del sitio. También podemos usar cookies de
                analítica y marketing si nos das tu consentimiento.
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-2">
                <button
                    type="button"
                    onClick={onAccept}
                    className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
                >
                    Aceptar todo
                </button>
                <button
                    type="button"
                    onClick={onReject}
                    className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2"
                >
                    Solo necesarias
                </button>
                <button
                    type="button"
                    onClick={onCustomize}
                    className="px-3 py-2 text-sm font-medium text-slate-500 underline underline-offset-2 transition-colors hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2"
                >
                    Personalizar
                </button>
            </div>
        </>
    );
}

/* ── Compact banner (/m/* — mobile QR menu) ─────────────────────── */

function CompactBanner({
    onAccept,
    onReject,
    onCustomize,
}: {
    onAccept: () => void;
    onReject: () => void;
    onCustomize: () => void;
}) {
    return (
        <div className="flex flex-col gap-2">
            <p className="text-xs text-slate-600 leading-snug">
                Este sitio usa cookies.{' '}
                <button
                    type="button"
                    onClick={onCustomize}
                    className="underline underline-offset-2 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-slate-400"
                >
                    Más info
                </button>
            </p>
            <div className="flex items-center gap-2">
                <button
                    type="button"
                    onClick={onAccept}
                    className="flex-1 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-1"
                >
                    Aceptar
                </button>
                <button
                    type="button"
                    onClick={onReject}
                    className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-1"
                >
                    Rechazar
                </button>
            </div>
        </div>
    );
}

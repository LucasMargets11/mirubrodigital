'use client';

import { useState, useEffect } from 'react';
import { getReviewSettings, updateReviewSettings, activateReviewsTrial } from '@/features/reviews/api';
import type { ReviewConfig, ReviewMode } from '@/features/reviews/types';
import { UpgradeToProButton } from '@/features/reviews/upgrade-to-pro-button';
import { DowngradeToBaseButton } from '@/features/reviews/downgrade-to-base-button';
import { GooglePlaceAutocomplete, type GooglePlaceResult } from '@/features/reviews/google-place-autocomplete';
import { PlaceIdHelpModal } from '@/features/reviews/components/place-id-help';
import { BusinessBrandingPanel } from '@/features/business/branding';

// Feature flag: set to true when Google Places API is properly configured in Google Cloud.
// While false, only the manual Place ID flow is shown.
const GOOGLE_PLACE_SEARCH_ENABLED = false;

const MODE_LABELS: Record<ReviewMode, string> = {
    direct: 'Directo — redirige siempre a Google',
    smart_filter: 'Filtro inteligente — filtra por puntaje',
};

type PlaceFlowState = 'idle' | 'searching' | 'confirming';

export function ReviewConfigClient() {
    const [config, setConfig] = useState<ReviewConfig | null>(null);
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(true);
    const [activatingTrial, setActivatingTrial] = useState(false);
    const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
    const [downgraded, setDowngraded] = useState(false);

    // Form fields
    const [enabled, setEnabled] = useState(false);
    const [googlePlaceId, setGooglePlaceId] = useState('');
    const [googlePlaceName, setGooglePlaceName] = useState('');
    const [googlePlaceAddress, setGooglePlaceAddress] = useState('');
    const [googleReviewUrl, setGoogleReviewUrl] = useState('');
    const [customRedirectUrl, setCustomRedirectUrl] = useState('');
    const [redirectThreshold, setRedirectThreshold] = useState(4);
    const [collectContact, setCollectContact] = useState(false);
    const [thankYouMessage, setThankYouMessage] = useState('');
    const [mode, setMode] = useState<ReviewMode>('direct');

    // Public landing text customisation
    const [publicDisplayName, setPublicDisplayName] = useState('');
    const [publicSubtitle, setPublicSubtitle] = useState('');
    const [publicQuestion, setPublicQuestion] = useState('');

    // Google Place autocomplete flow
    const [placeFlow, setPlaceFlow] = useState<PlaceFlowState>('idle');
    const [pendingPlace, setPendingPlace] = useState<GooglePlaceResult | null>(null);
    const [manualFallback, setManualFallback] = useState(!GOOGLE_PLACE_SEARCH_ENABLED);
    const [showPlaceIdHelp, setShowPlaceIdHelp] = useState(false);

    useEffect(() => {
        getReviewSettings()
            .then((data) => {
                setConfig(data);
                setEnabled(data.enabled);
                setGooglePlaceId(data.google_place_id ?? '');
                setGooglePlaceName(data.google_place_name ?? '');
                setGooglePlaceAddress(data.google_place_formatted_address ?? '');
                setGoogleReviewUrl(data.google_review_url ?? '');
                setCustomRedirectUrl(data.custom_redirect_url ?? '');
                setRedirectThreshold(data.redirect_threshold ?? 4);
                setCollectContact(data.collect_contact ?? false);
                setThankYouMessage(data.thank_you_message ?? '');
                setMode(data.mode ?? 'direct');
                setPublicDisplayName(data.public_display_name ?? '');
                setPublicSubtitle(data.public_subtitle ?? '');
                setPublicQuestion(data.public_question ?? '');
            })
            .catch(() => {
                // First time — no config yet
            })
            .finally(() => setLoading(false));
    }, []);

    const canEditMode = config?.smart_filter_allowed ?? false;
    const isSmartFilter = mode === 'smart_filter';
    const isPro = config?.is_reviews_pro ?? false;
    const hasLinkedPlace = !!googlePlaceId;

    function handleDowngraded() {
        getReviewSettings().then((data) => {
            setConfig(data);
            setMode(data.mode ?? 'direct');
            setDowngraded(true);
            setMessage({ type: 'success', text: 'Tu plan volvió a Reseñas Base.' });
        });
    }

    function handlePlaceSelected(place: GooglePlaceResult) {
        setPendingPlace(place);
        setPlaceFlow('confirming');
    }

    async function handleConfirmPlace() {
        if (!pendingPlace) return;
        setSaving(true);
        setMessage(null);
        try {
            const payload = {
                google_place_id: pendingPlace.placeId,
                google_place_name: pendingPlace.displayName,
                google_place_formatted_address: pendingPlace.formattedAddress,
                google_review_url: pendingPlace.reviewUrl,
            };
            const updated = await updateReviewSettings(payload);
            setConfig(updated);
            setGooglePlaceId(updated.google_place_id);
            setGooglePlaceName(updated.google_place_name);
            setGooglePlaceAddress(updated.google_place_formatted_address);
            setGoogleReviewUrl(updated.google_review_url);
            setPendingPlace(null);
            setPlaceFlow('idle');
            setManualFallback(false);
            setMessage({ type: 'success', text: 'Negocio vinculado correctamente.' });
        } catch {
            setMessage({ type: 'error', text: 'Error al vincular el negocio. Intentá de nuevo.' });
        } finally {
            setSaving(false);
        }
    }

    function handleUnlinkPlace() {
        setGooglePlaceId('');
        setGooglePlaceName('');
        setGooglePlaceAddress('');
        setGoogleReviewUrl('');
        setPendingPlace(null);
        setPlaceFlow('idle');
    }

    async function handleSave() {
        setSaving(true);
        setMessage(null);
        try {
            const payload: Parameters<typeof updateReviewSettings>[0] = {
                enabled,
                thank_you_message: thankYouMessage || undefined,
                public_display_name: publicDisplayName.trim(),
                public_subtitle: publicSubtitle.trim(),
                public_question: publicQuestion.trim(),
            };

            if (canEditMode) {
                payload.mode = mode;
            }

            if (isSmartFilter) {
                payload.redirect_threshold = redirectThreshold;
                payload.collect_contact = collectContact;
                payload.custom_redirect_url = customRedirectUrl || undefined;
            }

            const updated = await updateReviewSettings(payload);
            setConfig(updated);
            setMessage({ type: 'success', text: 'Configuración guardada correctamente.' });
        } catch {
            setMessage({ type: 'error', text: 'Error al guardar. Intentá de nuevo.' });
        } finally {
            setSaving(false);
        }
    }

    async function handleSaveManualFallback() {
        if (!googlePlaceId.trim()) return;
        setSaving(true);
        setMessage(null);
        try {
            const payload = {
                google_place_id: googlePlaceId.trim(),
                google_place_name: '',
                google_place_formatted_address: '',
                google_review_url: googleReviewUrl || undefined,
            };
            const updated = await updateReviewSettings(payload);
            setConfig(updated);
            setGooglePlaceId(updated.google_place_id);
            setGooglePlaceName(updated.google_place_name);
            setGooglePlaceAddress(updated.google_place_formatted_address);
            setGoogleReviewUrl(updated.google_review_url);
            setManualFallback(false);
            setMessage({ type: 'success', text: 'Place ID guardado correctamente.' });
        } catch {
            setMessage({ type: 'error', text: 'Error al guardar. Intentá de nuevo.' });
        } finally {
            setSaving(false);
        }
    }

    async function handleActivateTrial() {
        setActivatingTrial(true);
        setMessage(null);
        try {
            const updated = await activateReviewsTrial();
            setConfig(updated);
            setMode(updated.mode);
            setMessage({ type: 'success', text: 'Prueba gratuita activada. El filtro inteligente está activo por 7 días.' });
        } catch {
            setMessage({ type: 'error', text: 'No se pudo activar el período de prueba.' });
        } finally {
            setActivatingTrial(false);
        }
    }

    if (loading) {
        return (
            <div className="flex h-40 items-center justify-center">
                <p className="text-sm text-slate-400">Cargando configuración…</p>
            </div>
        );
    }

    return (
        <>
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">
                    QR de Reseñas
                </p>
                <h1 className="text-3xl font-display font-bold text-slate-900">Configuración</h1>
                <p className="mt-1 text-sm text-slate-500">
                    Configurá las reseñas y la redirección para tu negocio.
                </p>
            </header>

            <div className="max-w-xl space-y-6">
                <PlaceIdHelpModal open={showPlaceIdHelp} onClose={() => setShowPlaceIdHelp(false)} />
                {/* Habilitar */}
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <div className="flex items-center gap-3">
                        <input
                            id="reviews-enabled"
                            type="checkbox"
                            checked={enabled}
                            onChange={(e) => setEnabled(e.target.checked)}
                            className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                        />
                        <label htmlFor="reviews-enabled" className="text-sm font-medium text-slate-700">
                            Reseñas habilitadas
                        </label>
                    </div>
                </div>

                {/* Negocio de Google — 4-state flow */}
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-slate-900">Negocio de Google</h2>
                        <button
                            type="button"
                            onClick={() => setShowPlaceIdHelp(true)}
                            className="text-xs font-medium text-brand-600 underline hover:text-brand-700"
                        >
                            ¿Cómo obtener mi Place ID?
                        </button>
                    </div>

                    {/* State: saved — show linked business from our DB */}
                    {hasLinkedPlace && placeFlow === 'idle' && (
                        <div className="space-y-3">
                            <div className="rounded-lg border border-green-200 bg-green-50 p-4 space-y-1">
                                <div className="flex items-center gap-2">
                                    <svg className="h-4 w-4 text-green-600 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                    </svg>
                                    <span className="text-sm font-semibold text-green-800">Negocio vinculado</span>
                                </div>
                                {googlePlaceName && (
                                    <p className="text-sm font-medium text-slate-800">{googlePlaceName}</p>
                                )}
                                {googlePlaceAddress && (
                                    <p className="text-xs text-slate-500">{googlePlaceAddress}</p>
                                )}
                                <p className="text-xs text-slate-400 font-mono">{googlePlaceId}</p>
                                {googleReviewUrl && (
                                    <p className="text-xs text-slate-400 truncate">
                                        URL de reseñas:{' '}
                                        <a href={googleReviewUrl} target="_blank" rel="noopener noreferrer" className="text-brand-600 underline">
                                            {googleReviewUrl}
                                        </a>
                                    </p>
                                )}
                            </div>
                            <button
                                type="button"
                                onClick={() => GOOGLE_PLACE_SEARCH_ENABLED ? setPlaceFlow('searching') : setManualFallback(true)}
                                className="text-sm font-medium text-brand-600 hover:text-brand-700 underline"
                            >
                                Cambiar negocio
                            </button>
                        </div>
                    )}

                    {/* State: empty — CTA to search or manual */}
                    {!hasLinkedPlace && placeFlow === 'idle' && (
                        <div className="space-y-3">
                            <p className="text-xs text-slate-500">
                                Para vincular tu negocio, pegá el Place ID de Google. Si no completás la URL de reseñas,
                                MiRubro la genera automáticamente a partir del Place ID.
                            </p>
                            {GOOGLE_PLACE_SEARCH_ENABLED && (
                                <button
                                    type="button"
                                    onClick={() => setPlaceFlow('searching')}
                                    className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors"
                                >
                                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                                    </svg>
                                    Buscar negocio en Google
                                </button>
                            )}
                        </div>
                    )}

                    {/* State: searching — autocomplete loaded (requires GOOGLE_PLACE_SEARCH_ENABLED) */}
                    {GOOGLE_PLACE_SEARCH_ENABLED && placeFlow === 'searching' && (
                        <GooglePlaceAutocomplete
                            onSelect={handlePlaceSelected}
                            onCancel={() => setPlaceFlow('idle')}
                        />
                    )}

                    {/* State: confirming — show selected place for confirmation (requires GOOGLE_PLACE_SEARCH_ENABLED) */}
                    {GOOGLE_PLACE_SEARCH_ENABLED && placeFlow === 'confirming' && pendingPlace && (
                        <div className="space-y-4">
                            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-1">
                                <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
                                    Confirmá el negocio
                                </p>
                                <p className="text-sm font-medium text-slate-800">{pendingPlace.displayName}</p>
                                {pendingPlace.formattedAddress && (
                                    <p className="text-xs text-slate-500">{pendingPlace.formattedAddress}</p>
                                )}
                                <p className="text-xs text-slate-400 font-mono">{pendingPlace.placeId}</p>
                                {pendingPlace.googleMapsURI && (
                                    <p className="text-xs text-slate-400 truncate">
                                        Google Maps:{' '}
                                        <a href={pendingPlace.googleMapsURI} target="_blank" rel="noopener noreferrer" className="text-brand-600 underline">
                                            Ver en Google Maps
                                        </a>
                                    </p>
                                )}
                                {pendingPlace.reviewUrl && (
                                    <p className="text-xs text-slate-400 truncate">
                                        URL de reseñas: <span className="font-mono">{pendingPlace.reviewUrl}</span>
                                    </p>
                                )}
                            </div>
                            <div className="flex gap-3">
                                <button
                                    type="button"
                                    onClick={handleConfirmPlace}
                                    disabled={saving}
                                    className="rounded-full bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors disabled:opacity-50"
                                >
                                    {saving ? 'Guardando…' : 'Confirmar negocio'}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => { setPendingPlace(null); setPlaceFlow('searching'); }}
                                    className="text-sm text-slate-500 underline hover:text-slate-700"
                                >
                                    Buscar otro
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Manual fallback — secondary, collapsed */}
                    {GOOGLE_PLACE_SEARCH_ENABLED && placeFlow === 'idle' && !manualFallback && (
                        <button
                            type="button"
                            onClick={() => setManualFallback(true)}
                            className="text-xs text-slate-400 underline hover:text-slate-500"
                        >
                            ¿No encontrás tu negocio? Ingresá el Place ID manualmente
                        </button>
                    )}
                    {placeFlow === 'idle' && manualFallback && (
                        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3">
                            <p className="text-xs text-slate-500">
                                Podés encontrar el Place ID de tu negocio en{' '}
                                <a
                                    href="https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-brand-600 underline"
                                >
                                    Google Place ID Finder
                                </a>
                            </p>
                            <div>
                                <label htmlFor="manual-place-id" className="block text-xs font-medium text-slate-600">
                                    Google Place ID
                                </label>
                                <input
                                    id="manual-place-id"
                                    type="text"
                                    value={googlePlaceId}
                                    onChange={(e) => setGooglePlaceId(e.target.value)}
                                    placeholder="ChIJ..."
                                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                                />
                            </div>
                            <div>
                                <label htmlFor="manual-review-url" className="block text-xs font-medium text-slate-600">
                                    URL de reseñas (opcional)
                                </label>
                                <p className="mt-0.5 text-xs text-slate-400">
                                    Si no la completás, se genera automáticamente a partir del Place ID.
                                </p>
                                <input
                                    id="manual-review-url"
                                    type="url"
                                    value={googleReviewUrl}
                                    onChange={(e) => setGoogleReviewUrl(e.target.value)}
                                    placeholder="https://search.google.com/local/writereview?placeid=..."
                                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                                />
                            </div>
                            <div className="flex gap-3">
                                <button
                                    type="button"
                                    onClick={handleSaveManualFallback}
                                    disabled={saving || !googlePlaceId.trim()}
                                    className="rounded-full bg-slate-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-slate-700 transition-colors disabled:opacity-50"
                                >
                                    {saving ? 'Guardando…' : 'Guardar Place ID'}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setManualFallback(false)}
                                    className="text-xs text-slate-400 underline hover:text-slate-500"
                                >
                                    Cancelar
                                </button>
                            </div>
                        </div>
                    )}
                </div>

                {/* Modo */}
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <h2 className="text-sm font-semibold text-slate-900">Modo de operación</h2>
                    {canEditMode ? (
                        <>
                            <p className="text-xs text-slate-400">
                                Elegí cómo se comporta el QR cuando un cliente lo escanea.
                            </p>
                            <select
                                id="review-mode"
                                value={mode}
                                onChange={(e) => setMode(e.target.value as ReviewMode)}
                                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                            >
                                <option value="direct">{MODE_LABELS.direct}</option>
                                <option value="smart_filter">{MODE_LABELS.smart_filter}</option>
                            </select>
                            {config?.trial_active && (
                                <p className="text-xs text-amber-600">
                                    {config.trial_ends_at
                                        ? (() => {
                                              const daysLeft = Math.max(
                                                  0,
                                                  Math.ceil(
                                                      (new Date(config.trial_ends_at).getTime() - Date.now()) /
                                                          (1000 * 60 * 60 * 24),
                                                  ),
                                              );
                                              if (daysLeft === 0) return 'Tu prueba finaliza hoy.';
                                              if (daysLeft === 1) return 'Te queda 1 día de prueba.';
                                              return `Te quedan ${daysLeft} días de prueba.`;
                                          })()
                                        : 'Estás usando el filtro inteligente durante tu período de prueba.'}
                                </p>
                            )}
                        </>
                    ) : (
                        <>
                            <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2">
                                <span className="text-sm font-medium text-slate-700">{MODE_LABELS.direct}</span>
                            </div>
                            {config?.trial_used && !config.trial_active ? (
                                <div className="space-y-2">
                                    <p className="text-xs text-slate-500">
                                        Tu período de prueba finalizó y el QR volvió al modo Directo.
                                    </p>
                                    <UpgradeToProButton size="sm" />
                                </div>
                            ) : config?.trial_available ? (
                                <div className="space-y-2">
                                    <p className="text-xs text-slate-500">
                                        Probá el filtro inteligente gratis por 7 días.
                                    </p>
                                    <button
                                        onClick={handleActivateTrial}
                                        disabled={activatingTrial}
                                        className="rounded-full bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors disabled:opacity-50"
                                    >
                                        {activatingTrial ? 'Activando…' : 'Activar prueba gratuita'}
                                    </button>
                                </div>
                            ) : (
                                <p className="text-xs text-slate-400">
                                    El filtro inteligente está disponible con el plan Pro.
                                </p>
                            )}
                        </>
                    )}
                </div>

                {/* Plan management — visible for Pro users */}
                {isPro && !downgraded && (
                    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-3">
                        <h2 className="text-sm font-semibold text-slate-900">Tu plan</h2>
                        <div className="flex items-center gap-2">
                            <span className="inline-flex items-center rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-semibold text-brand-700">
                                Reseñas Pro
                            </span>
                        </div>
                        <p className="text-xs text-slate-500">
                            Tenés acceso al filtro inteligente, feedback privado y analytics avanzadas.
                        </p>
                        <DowngradeToBaseButton onDowngraded={handleDowngraded} />
                    </div>
                )}

                {/* Texto visible en tu QR — landing pública */}
                <PublicTextCard
                    displayName={publicDisplayName}
                    onDisplayNameChange={setPublicDisplayName}
                    subtitle={publicSubtitle}
                    onSubtitleChange={setPublicSubtitle}
                    question={publicQuestion}
                    onQuestionChange={setPublicQuestion}
                    fallbackName={config?.google_place_name || ''}
                />

                {/* Mensaje — visible in direct mode (shown on landing page) */}
                {!isSmartFilter && (
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <h2 className="text-sm font-semibold text-slate-900">Mensaje</h2>
                    <div>
                        <label htmlFor="thank-you-message-direct" className="block text-sm font-medium text-slate-700">
                            Mensaje en la página de reseña
                        </label>
                        <p className="mt-0.5 text-xs text-slate-400">
                            Se muestra al cliente cuando escanea el QR, antes de redirigirlo a Google.
                        </p>
                        <textarea
                            id="thank-you-message-direct"
                            value={thankYouMessage}
                            onChange={(e) => setThankYouMessage(e.target.value)}
                            placeholder="¡Gracias por visitarnos! Contanos tu experiencia."
                            rows={2}
                            className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                        />
                    </div>
                </div>
                )}

                {/* Redirect — smart_filter only */}
                {isSmartFilter && (
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <h2 className="text-sm font-semibold text-slate-900">Redirección</h2>

                    <div>
                        <label htmlFor="redirect-threshold" className="block text-sm font-medium text-slate-700">
                            Umbral de redirección
                        </label>
                        <p className="mt-0.5 text-xs text-slate-400">
                            Puntaje mínimo para redirigir a Google (1–5). Puntajes menores se guardan como feedback privado.
                        </p>
                        <select
                            id="redirect-threshold"
                            value={redirectThreshold}
                            onChange={(e) => setRedirectThreshold(Number(e.target.value))}
                            className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                        >
                            {[1, 2, 3, 4, 5].map((n) => (
                                <option key={n} value={n}>{n} estrella{n > 1 ? 's' : ''}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label htmlFor="custom-redirect-url" className="block text-sm font-medium text-slate-700">
                            URL de redirección personalizada
                        </label>
                        <p className="mt-0.5 text-xs text-slate-400">
                            Si querés redirigir a otro sitio en vez de Google (opcional).
                        </p>
                        <input
                            id="custom-redirect-url"
                            type="url"
                            value={customRedirectUrl}
                            onChange={(e) => setCustomRedirectUrl(e.target.value)}
                            placeholder="https://..."
                            className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                        />
                    </div>

                    {config?.redirect_url && (
                        <p className="text-xs text-slate-400">
                            URL activa: <span className="font-mono text-slate-500">{config.redirect_url}</span>
                        </p>
                    )}
                </div>
                )}

                {/* Feedback — smart_filter only */}
                {isSmartFilter && (
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <h2 className="text-sm font-semibold text-slate-900">Feedback</h2>

                    <div className="flex items-center gap-3">
                        <input
                            id="collect-contact"
                            type="checkbox"
                            checked={collectContact}
                            onChange={(e) => setCollectContact(e.target.checked)}
                            className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                        />
                        <label htmlFor="collect-contact" className="text-sm text-slate-700">
                            Pedir datos de contacto en el feedback
                        </label>
                    </div>

                    <div>
                        <label htmlFor="thank-you-message" className="block text-sm font-medium text-slate-700">
                            Mensaje de agradecimiento
                        </label>
                        <textarea
                            id="thank-you-message"
                            value={thankYouMessage}
                            onChange={(e) => setThankYouMessage(e.target.value)}
                            placeholder="¡Gracias por tu opinión!"
                            rows={2}
                            className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                        />
                    </div>
                </div>
                )}

                {/* Branding global */}
                <BusinessBrandingPanel />

                {/* Actions */}
                {message && (
                    <p className={`text-sm ${message.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>
                        {message.text}
                    </p>
                )}

                <button
                    onClick={handleSave}
                    disabled={saving}
                    className="rounded-full bg-brand-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors disabled:opacity-50"
                >
                    {saving ? 'Guardando…' : 'Guardar'}
                </button>
            </div>
        </>
    );
}

/* ── PublicTextCard ──────────────────────────────────────────────── */

const DISPLAY_NAME_MAX = 120;
const SUBTITLE_MAX = 180;
const QUESTION_MAX = 180;
const DEFAULT_SUBTITLE = 'Tu opinión nos ayuda a mejorar 💛';

function PublicTextCard({
    displayName,
    onDisplayNameChange,
    subtitle,
    onSubtitleChange,
    question,
    onQuestionChange,
    fallbackName,
}: {
    displayName: string;
    onDisplayNameChange: (v: string) => void;
    subtitle: string;
    onSubtitleChange: (v: string) => void;
    question: string;
    onQuestionChange: (v: string) => void;
    fallbackName: string;
}) {
    const effectiveName = displayName.trim() || fallbackName || 'tu negocio';
    const effectiveSubtitle = subtitle.trim() || DEFAULT_SUBTITLE;
    const effectiveQuestion = question.trim() || `¿Cómo fue tu experiencia en ${effectiveName}?`;

    return (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
            <div>
                <h2 className="text-sm font-semibold text-slate-900">Texto visible en tu QR</h2>
                <p className="mt-1 text-xs text-slate-500">
                    Personalizá lo que ven tus clientes en la landing pública. La URL del QR no cambia.
                </p>
            </div>

            <div>
                <label htmlFor="public-display-name" className="block text-sm font-medium text-slate-700">
                    Nombre público
                </label>
                <p className="mt-0.5 text-xs text-slate-400">
                    Se muestra como título de la página. Si lo dejás vacío, usamos el nombre de tu negocio.
                </p>
                <input
                    id="public-display-name"
                    type="text"
                    value={displayName}
                    onChange={(e) => onDisplayNameChange(e.target.value)}
                    maxLength={DISPLAY_NAME_MAX}
                    placeholder={fallbackName || 'Nombre de tu negocio'}
                    className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                />
                <p className="mt-1 text-[11px] text-slate-400 text-right">
                    {displayName.length}/{DISPLAY_NAME_MAX}
                </p>
            </div>

            <div>
                <label htmlFor="public-question" className="block text-sm font-medium text-slate-700">
                    Pregunta principal
                </label>
                <p className="mt-0.5 text-xs text-slate-400">
                    Opcional. Si la dejás vacía se genera con el nombre público.
                </p>
                <input
                    id="public-question"
                    type="text"
                    value={question}
                    onChange={(e) => onQuestionChange(e.target.value)}
                    maxLength={QUESTION_MAX}
                    placeholder={`¿Cómo fue tu experiencia en ${effectiveName}?`}
                    className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                />
                <p className="mt-1 text-[11px] text-slate-400 text-right">
                    {question.length}/{QUESTION_MAX}
                </p>
            </div>

            <div>
                <label htmlFor="public-subtitle" className="block text-sm font-medium text-slate-700">
                    Texto auxiliar
                </label>
                <p className="mt-0.5 text-xs text-slate-400">
                    Aparece debajo de la pregunta. Opcional.
                </p>
                <input
                    id="public-subtitle"
                    type="text"
                    value={subtitle}
                    onChange={(e) => onSubtitleChange(e.target.value)}
                    maxLength={SUBTITLE_MAX}
                    placeholder={DEFAULT_SUBTITLE}
                    className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                />
                <p className="mt-1 text-[11px] text-slate-400 text-right">
                    {subtitle.length}/{SUBTITLE_MAX}
                </p>
            </div>

            {/* Live preview */}
            <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    Vista previa
                </p>
                <div className="mt-2 space-y-1">
                    <p className="text-base font-semibold text-slate-900">{effectiveName}</p>
                    <p className="text-sm font-medium text-slate-700">{effectiveQuestion}</p>
                    <p className="text-xs text-slate-500">{effectiveSubtitle}</p>
                </div>
            </div>
        </div>
    );
}

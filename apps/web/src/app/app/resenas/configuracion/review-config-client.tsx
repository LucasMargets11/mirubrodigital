'use client';

import { useState, useEffect } from 'react';
import { getReviewSettings, updateReviewSettings } from '@/features/reviews/api';
import type { ReviewConfig } from '@/features/reviews/types';

export function ReviewConfigClient() {
    const [config, setConfig] = useState<ReviewConfig | null>(null);
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(true);
    const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

    // Form fields
    const [enabled, setEnabled] = useState(false);
    const [googlePlaceId, setGooglePlaceId] = useState('');
    const [googleReviewUrl, setGoogleReviewUrl] = useState('');
    const [customRedirectUrl, setCustomRedirectUrl] = useState('');
    const [redirectThreshold, setRedirectThreshold] = useState(4);
    const [collectContact, setCollectContact] = useState(false);
    const [thankYouMessage, setThankYouMessage] = useState('');

    useEffect(() => {
        getReviewSettings()
            .then((data) => {
                setConfig(data);
                setEnabled(data.enabled);
                setGooglePlaceId(data.google_place_id ?? '');
                setGoogleReviewUrl(data.google_review_url ?? '');
                setCustomRedirectUrl(data.custom_redirect_url ?? '');
                setRedirectThreshold(data.redirect_threshold ?? 4);
                setCollectContact(data.collect_contact ?? false);
                setThankYouMessage(data.thank_you_message ?? '');
            })
            .catch(() => {
                // First time — no config yet
            })
            .finally(() => setLoading(false));
    }, []);

    async function handleSave() {
        setSaving(true);
        setMessage(null);
        try {
            const updated = await updateReviewSettings({
                enabled,
                google_place_id: googlePlaceId || undefined,
                google_review_url: googleReviewUrl || undefined,
                custom_redirect_url: customRedirectUrl || undefined,
                redirect_threshold: redirectThreshold,
                collect_contact: collectContact,
                thank_you_message: thankYouMessage || undefined,
            });
            setConfig(updated);
            setMessage({ type: 'success', text: 'Configuración guardada correctamente.' });
        } catch {
            setMessage({ type: 'error', text: 'Error al guardar. Intentá de nuevo.' });
        } finally {
            setSaving(false);
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

                {/* Google */}
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <h2 className="text-sm font-semibold text-slate-900">Google</h2>

                    <div>
                        <label htmlFor="google-place-id" className="block text-sm font-medium text-slate-700">
                            Google Place ID
                        </label>
                        <p className="mt-0.5 text-xs text-slate-400">
                            Encontralo en{' '}
                            <a
                                href="https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-brand-600 underline"
                            >
                                Google Place ID Finder
                            </a>
                        </p>
                        <input
                            id="google-place-id"
                            type="text"
                            value={googlePlaceId}
                            onChange={(e) => setGooglePlaceId(e.target.value)}
                            placeholder="ChIJ..."
                            className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                        />
                    </div>

                    <div>
                        <label htmlFor="google-review-url" className="block text-sm font-medium text-slate-700">
                            URL de reseñas de Google
                        </label>
                        <p className="mt-0.5 text-xs text-slate-400">
                            URL directa para dejar una reseña. Si no la completás, se genera a partir del Place ID.
                        </p>
                        <input
                            id="google-review-url"
                            type="url"
                            value={googleReviewUrl}
                            onChange={(e) => setGoogleReviewUrl(e.target.value)}
                            placeholder="https://search.google.com/local/writereview?placeid=..."
                            className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
                        />
                    </div>
                </div>

                {/* Redirect */}
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

                {/* Feedback */}
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

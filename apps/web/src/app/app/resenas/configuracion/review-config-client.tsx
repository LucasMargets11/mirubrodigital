'use client';

import { useState, useEffect } from 'react';
import { getReviewSettings, updateReviewSettings } from '@/features/reviews/api';

export function ReviewConfigClient() {
    const [googlePlaceId, setGooglePlaceId] = useState('');
    const [reviewsEnabled, setReviewsEnabled] = useState(false);
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(true);
    const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

    useEffect(() => {
        getReviewSettings()
            .then((data) => {
                setGooglePlaceId(data.google_place_id ?? '');
                setReviewsEnabled(data.reviews_enabled);
            })
            .catch(() => {
                // First time — no settings yet
            })
            .finally(() => setLoading(false));
    }, []);

    async function handleSave() {
        setSaving(true);
        setMessage(null);
        try {
            await updateReviewSettings({
                google_place_id: googlePlaceId || null,
                reviews_enabled: reviewsEnabled,
            });
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
                    Conectá tu negocio con Google para recibir reseñas.
                </p>
            </header>

            <div className="max-w-xl space-y-6">
                <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                    <div>
                        <label
                            htmlFor="google-place-id"
                            className="block text-sm font-medium text-slate-700"
                        >
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

                    <div className="flex items-center gap-3">
                        <input
                            id="reviews-enabled"
                            type="checkbox"
                            checked={reviewsEnabled}
                            onChange={(e) => setReviewsEnabled(e.target.checked)}
                            className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                        />
                        <label htmlFor="reviews-enabled" className="text-sm text-slate-700">
                            Reseñas habilitadas
                        </label>
                    </div>

                    {message && (
                        <p
                            className={`text-sm ${
                                message.type === 'success' ? 'text-green-600' : 'text-red-600'
                            }`}
                        >
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
            </div>
        </>
    );
}

'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

/* ── Types ─────────────────────────────────────────────────── */

export interface GooglePlaceResult {
    placeId: string;
    displayName: string;
    formattedAddress: string;
    googleMapsURI: string;
    reviewUrl: string;
}

interface Props {
    onSelect: (place: GooglePlaceResult) => void;
    onCancel: () => void;
}

/* ── Script loader (singleton) ─────────────────────────────── */

let _loadPromise: Promise<void> | null = null;

function loadGoogleMapsScript(): Promise<void> {
    if (_loadPromise) return _loadPromise;

    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? '';
    if (!apiKey) {
        return Promise.reject(new Error('NEXT_PUBLIC_GOOGLE_MAPS_API_KEY no está configurada.'));
    }

    _loadPromise = new Promise<void>((resolve, reject) => {
        // Already loaded
        if (typeof google !== 'undefined' && typeof google.maps?.importLibrary === 'function') {
            resolve();
            return;
        }
        const script = document.createElement('script');
        script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&v=weekly&loading=async`;
        script.async = true;
        script.onload = () => resolve();
        script.onerror = () => {
            _loadPromise = null;
            reject(new Error('Error al cargar Google Maps.'));
        };
        document.head.appendChild(script);
    });

    return _loadPromise;
}

/* ── Component ─────────────────────────────────────────────── */

/**
 * Uses PlaceAutocompleteElement with the current `gmp-select` event API.
 *
 * NOTE: Google unified BasicPlaceAutocompleteElement into PlaceAutocompleteElement
 * (the "Basic" variant no longer exists in the current API). The event was
 * renamed from `gmp-placeselect` → `gmp-select` and now provides
 * `placePrediction.toPlace()` instead of the former `event.place`.
 *
 * The review URL is derived from the **verified** place_id returned by
 * Google's Places API (via `fetchFields`). The `writereview?placeid=` pattern
 * is the canonical format used by Google Business Profile. Additionally we
 * capture `googleMapsURI` — the official Google Maps page URL — as provenance.
 */
export function GooglePlaceAutocomplete({ onSelect, onCancel }: Props) {
    const containerRef = useRef<HTMLDivElement>(null);
    const autocompleteRef = useRef<google.maps.places.PlaceAutocompleteElement | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const handleSelect = useCallback(
        async (event: Event & { placePrediction?: { toPlace(): google.maps.places.Place } }) => {
            const prediction = event.placePrediction;
            if (!prediction) return;
            try {
                const place = prediction.toPlace();
                await place.fetchFields({
                    fields: ['displayName', 'formattedAddress', 'id', 'googleMapsURI'],
                });
                const placeId = place.id ?? '';
                const result: GooglePlaceResult = {
                    placeId,
                    displayName: place.displayName ?? '',
                    formattedAddress: place.formattedAddress ?? '',
                    googleMapsURI: place.googleMapsURI ?? '',
                    reviewUrl: placeId
                        ? `https://search.google.com/local/writereview?placeid=${placeId}`
                        : '',
                };
                onSelect(result);
            } catch {
                setError('No se pudieron obtener los datos del lugar.');
            }
        },
        [onSelect],
    );

    useEffect(() => {
        let cancelled = false;

        async function init() {
            try {
                await loadGoogleMapsScript();
                if (cancelled || !containerRef.current) return;

                let PlaceAutocompleteElement: typeof google.maps.places.PlaceAutocompleteElement;
                try {
                    const placesLib = await google.maps.importLibrary('places') as google.maps.PlacesLibrary;
                    PlaceAutocompleteElement = placesLib.PlaceAutocompleteElement;
                    if (!PlaceAutocompleteElement) {
                        throw new Error('PlaceAutocompleteElement no disponible.');
                    }
                } catch {
                    throw new Error(
                        'No se pudo cargar Google Places. Verificá que Maps JavaScript API y Places API (New) estén habilitadas.',
                    );
                }

                const el = new PlaceAutocompleteElement({});

                // Configure via properties (current API surface)
                (el as any).includedRegionCodes = ['ar'];
                (el as any).types = ['establishment'];

                // Style the inner <input> to match the app's design
                el.classList.add('gpa-element');

                el.addEventListener('gmp-select', handleSelect as EventListener);

                containerRef.current.innerHTML = '';
                containerRef.current.appendChild(el);
                autocompleteRef.current = el;
                setLoading(false);
            } catch (err) {
                if (!cancelled) {
                    setError(err instanceof Error ? err.message : 'Error al cargar Google Places.');
                    setLoading(false);
                }
            }
        }

        init();

        return () => {
            cancelled = true;
            if (autocompleteRef.current) {
                autocompleteRef.current.removeEventListener(
                    'gmp-select',
                    handleSelect as EventListener,
                );
                autocompleteRef.current = null;
            }
        };
    }, [handleSelect]);

    if (error) {
        return (
            <div className="space-y-3">
                <p className="text-sm text-red-600">{error}</p>
                <button
                    type="button"
                    onClick={onCancel}
                    className="text-sm text-slate-500 underline hover:text-slate-700"
                >
                    Cancelar
                </button>
            </div>
        );
    }

    return (
        <div className="space-y-3">
            <p className="text-xs text-slate-500">
                Escribí el nombre de tu negocio para buscarlo en Google.
            </p>
            {loading && (
                <p className="text-xs text-slate-400">Cargando buscador…</p>
            )}
            <div ref={containerRef} className="gpa-container" />
            <style jsx global>{`
                .gpa-container gmp-place-autocomplete {
                    width: 100%;
                }
                .gpa-container gmp-place-autocomplete input {
                    width: 100%;
                    border: 1px solid #cbd5e1;
                    border-radius: 0.5rem;
                    padding: 0.5rem 0.75rem;
                    font-size: 0.875rem;
                    line-height: 1.25rem;
                    outline: none;
                    transition: border-color 0.15s, box-shadow 0.15s;
                }
                .gpa-container gmp-place-autocomplete input:focus {
                    border-color: var(--color-brand-500, #6366f1);
                    box-shadow: 0 0 0 1px var(--color-brand-500, #6366f1);
                }
            `}</style>
            <button
                type="button"
                onClick={onCancel}
                className="text-sm text-slate-500 underline hover:text-slate-700"
            >
                Cancelar
            </button>
        </div>
    );
}

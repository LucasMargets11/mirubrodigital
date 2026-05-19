'use client';

import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import Image from 'next/image';

const PLACE_ID_FINDER_URL =
    'https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder';

interface Props {
    open: boolean;
    onClose: () => void;
}

export function PlaceIdHelpModal({ open, onClose }: Props) {
    useEffect(() => {
        if (!open) return;
        const handler = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [open, onClose]);

    if (!open || typeof document === 'undefined') return null;

    const modal = (
        <div
            className="fixed inset-0 z-50"
            role="dialog"
            aria-modal="true"
            aria-labelledby="place-id-help-title"
        >
            {/* Backdrop */}
            <button
                type="button"
                aria-label="Cerrar"
                onClick={onClose}
                className="absolute inset-0 h-full w-full bg-slate-900/60"
            />

            {/* Panel */}
            <div
                className="relative z-10 flex min-h-full items-center justify-center p-4"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl">
                    {/* Header */}
                    <div className="flex items-start justify-between border-b border-slate-100 px-6 py-4">
                        <div>
                            <p className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                                QR de Reseñas
                            </p>
                            <h3
                                id="place-id-help-title"
                                className="mt-0.5 text-lg font-bold text-slate-900"
                            >
                                Cómo obtener tu Place ID
                            </h3>
                        </div>
                        <button
                            type="button"
                            onClick={onClose}
                            className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                            aria-label="Cerrar"
                        >
                            <svg
                                className="h-5 w-5"
                                fill="none"
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                                strokeWidth={2}
                            >
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M6 18L18 6M6 6l12 12"
                                />
                            </svg>
                        </button>
                    </div>

                    {/* Scrollable body */}
                    <div className="max-h-[68vh] overflow-y-auto px-6 py-5 space-y-8">
                        {/* Step 1 — no image, action link */}
                        <div className="space-y-3">
                            <h4 className="text-sm font-semibold text-slate-900">
                                1. Abrí Google Place ID Finder
                            </h4>
                            <p className="text-sm text-slate-500">
                                Ingresá a la herramienta oficial de Google para buscar el Place ID de tu
                                negocio.
                            </p>
                            <a
                                href={PLACE_ID_FINDER_URL}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-4 py-2 text-sm font-semibold text-brand-700 transition hover:bg-brand-100"
                            >
                                <svg
                                    className="h-4 w-4 shrink-0"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    stroke="currentColor"
                                    strokeWidth={2}
                                >
                                    <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
                                    />
                                </svg>
                                Abrir Google Place ID Finder
                            </a>
                        </div>

                        {/* Step 2 — real image */}
                        <div className="space-y-3">
                            <h4 className="text-sm font-semibold text-slate-900">
                                2. Buscá tu negocio
                            </h4>
                            <p className="text-sm text-slate-500">
                                En el buscador del mapa, escribí el nombre o la dirección exacta de tu
                                negocio y seleccioná el resultado correcto.
                            </p>
                            <div className="overflow-hidden rounded-xl border border-slate-200">
                                <Image
                                    src="/images/help/place-id/ayudaplaceid2.jpg"
                                    alt="Buscar la dirección exacta del negocio en Google Place ID Finder"
                                    width={1200}
                                    height={800}
                                    className="w-full h-auto"
                                    style={{ height: 'auto' }}
                                />
                            </div>
                        </div>

                        {/* Step 3 — real image */}
                        <div className="space-y-3">
                            <h4 className="text-sm font-semibold text-slate-900">
                                3. Copiá el Place ID
                            </h4>
                            <p className="text-sm text-slate-500">
                                Cuando Google muestre el resultado, copiá el Place ID y pegalo en el
                                campo{' '}
                                <span className="font-medium text-slate-700">
                                    &ldquo;Google Place ID&rdquo;
                                </span>{' '}
                                de MiRubro.
                            </p>
                            <div className="overflow-hidden rounded-xl border border-slate-200">
                                <Image
                                    src="/images/help/place-id/ayudaplaceid3.jpg"
                                    alt="Copiar el Place ID del negocio desde Google Place ID Finder"
                                    width={1200}
                                    height={800}
                                    className="w-full h-auto"
                                    style={{ height: 'auto' }}
                                />
                            </div>
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="flex justify-end border-t border-slate-100 px-6 py-4">
                        <button
                            type="button"
                            onClick={onClose}
                            className="rounded-full bg-slate-100 px-5 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-200"
                        >
                            Cerrar
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );

    return createPortal(modal, document.body);
}

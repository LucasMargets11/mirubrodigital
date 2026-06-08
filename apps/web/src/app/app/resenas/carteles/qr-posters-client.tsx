'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';

import { getReviewSettings } from '@/features/reviews/api';
import type { ReviewConfig } from '@/features/reviews/types';
import { QrPosterEditor } from '@/features/reviews/qr-posters/components/QrPosterEditor';
import { QrPosterPreview } from '@/features/reviews/qr-posters/components/QrPosterPreview';
import { SavedDesignsPanel } from '@/features/reviews/qr-posters/components/SavedDesignsPanel';
import {
    DEFAULT_BACKGROUND,
    DEFAULT_MAIN_TEXT,
    DEFAULT_SUBTITLE,
    QR_BOTTOM_OFFSET_MM_DEFAULT,
} from '@/features/reviews/qr-posters/constants';
import type { GenerateQrPosterPayload } from '@/features/reviews/qr-posters/types';
import type { QrPosterDesignPayload } from '@/features/reviews/qr-posters/designs-types';

const INITIAL_PAYLOAD: GenerateQrPosterPayload = {
    poster_size: 'a4_portrait',
    template_code: 'simple_centered',
    main_text: DEFAULT_MAIN_TEXT,
    subtitle: DEFAULT_SUBTITLE,
    include_logo: true,
    logo_variant: 'default',
    background_color: DEFAULT_BACKGROUND,
    background_mode: 'color',
    title_font: 'sans_bold',
    font_family: 'montserrat',
    font_weight: 'bold',
    main_text_color: null,
    subtitle_text_color: null,
    main_text_outline_enabled: false,
    main_text_outline_color: '#000000',
    subtitle_text_outline_enabled: false,
    subtitle_text_outline_color: '#000000',
    text_outline_width: 0.4,
    qr_scale: 'medium',
    qr_vertical_align: 'center',
    qr_size_mm: 48,
    qr_bottom_offset_mm: QR_BOTTOM_OFFSET_MM_DEFAULT,
    text_spacing: 'normal',
    uppercase_mode: 'none',
};

interface Props {
    businessName: string;
}

export function QrPostersClient({ businessName: _businessName }: Props) {
    const [config, setConfig] = useState<ReviewConfig | null>(null);
    const [accessDenied, setAccessDenied] = useState(false);
    const [loadError, setLoadError] = useState(false);
    const [loading, setLoading] = useState(true);
    const [payload, setPayload] = useState<GenerateQrPosterPayload>(INITIAL_PAYLOAD);
    /**
     * URL de imagen de fondo guardada en el servidor, proveniente de un diseño cargado.
     * Se limpia cuando el usuario sube un nuevo File o cambia a fondo de color.
     */
    const [savedBgUrl, setSavedBgUrl] = useState<string | null>(null);

    useEffect(() => {
        getReviewSettings()
            .then((cfg) => {
                setConfig(cfg);
                // Carteles está incluido en QR de Reseñas Pro y en paquetes que
                // lo agrupan (Restaurante Inteligente). Si el plan no lo incluye,
                // mostramos un estado bloqueado claro — NO redirigimos a /qr.
                setAccessDenied(!cfg.print_posters_allowed);
            })
            .catch(() => {
                setLoadError(true);
            })
            .finally(() => setLoading(false));
    }, []);

    function handleChange(patch: Partial<GenerateQrPosterPayload>) {
        setPayload((prev) => ({ ...prev, ...patch }));
        // Si el usuario sube un nuevo archivo o cambia a fondo de color, la URL guardada ya no aplica
        if (patch.background_image instanceof File || patch.background_mode === 'color') {
            setSavedBgUrl(null);
        }
    }

    /**
     * Cuando se carga un diseño guardado se aplica su payload al editor.
     * La imagen de fondo (si existe) se guarda en savedBgUrl para mostrarla en la preview.
     * background_image queda null porque no tenemos el File local — el PDF con la imagen
     * guardada se descarga directo desde la card del diseño (endpoint generate-pdf).
     */
    const handleLoadDesign = useCallback(
        (designPayload: QrPosterDesignPayload, backgroundImageUrl?: string | null) => {
            setPayload({
                qr_scale: 'medium',
                qr_vertical_align: 'center',
                qr_size_mm: null,
                qr_bottom_offset_mm: QR_BOTTOM_OFFSET_MM_DEFAULT,
                text_spacing: 'normal',
                uppercase_mode: 'none',
                font_family: 'montserrat',
                font_weight: 'bold',
                ...designPayload,
                background_image: null,
            });
            setSavedBgUrl(backgroundImageUrl ?? null);
        },
        [],
    );

    // ── Loading skeleton ─────────────────────────────────────────────────────
    if (loading) {
        return (
            <div className="space-y-4">
                <div className="h-6 w-40 animate-pulse rounded-lg bg-slate-200" />
                <div className="h-64 w-full animate-pulse rounded-2xl bg-slate-100" />
            </div>
        );
    }

    // ── Error cargando configuración ─────────────────────────────────────────
    if (loadError || !config) {
        return (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm">
                <p className="text-sm text-slate-600">
                    No pudimos cargar la configuración de Carteles. Actualizá la página e intentá de nuevo.
                </p>
            </div>
        );
    }

    // ── Plan sin Carteles: estado bloqueado claro (no redirige a /qr) ────────
    if (accessDenied) {
        return (
            <div className="rounded-2xl border border-brand-100 bg-brand-50/60 p-8 text-center shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">
                    Función Pro
                </p>
                <h2 className="mt-2 text-xl font-display font-bold text-slate-900">
                    Carteles QR no está incluido en tu plan
                </h2>
                <p className="mx-auto mt-2 max-w-md text-sm text-slate-600">
                    Generá carteles imprimibles con tu QR de reseñas actualizando a QR de Reseñas Pro.
                </p>
                <Link
                    href="/app/resenas"
                    className="mt-5 inline-flex items-center justify-center rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-600"
                >
                    Volver al panel de Reseñas
                </Link>
            </div>
        );
    }

    // ── Editor + Preview + Diseños guardados (acceso a Carteles confirmado) ──
    return (
        <div className="space-y-6">
            {/* Aviso: diseño cargado con imagen de fondo guardada */}
            {savedBgUrl && payload.background_mode === 'image' && !payload.background_image && (
                <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                    <svg
                        className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                        aria-hidden="true"
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                    </svg>
                    <div>
                        <p className="text-sm font-medium text-amber-800">
                            Este diseño tiene una imagen de fondo guardada
                        </p>
                        <p className="mt-0.5 text-xs text-amber-700">
                            La preview ya la muestra. Para descargar el PDF con esta imagen
                            guardada, usá el botón &quot;Descargar PDF&quot; en la card del diseño.
                        </p>
                    </div>
                </div>
            )}

            {/* Fila principal: editor + preview */}
            {/*
              * Grid sin items-start para que el <aside> se estire a la altura
              * del editor (stretch por defecto). Eso le da espacio de viaje al
              * sticky interno. Si usáramos items-start, el aside tendría la
              * altura de la preview y sticky no podría desplazarse.
              */}
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(360px,520px)]">
                {/* Panel izquierdo: editor */}
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <QrPosterEditor payload={payload} onChange={handleChange} />
                </div>

                {/* Panel derecho: preview — desktop sticky
                  * lg:self-stretch: el aside ocupa la altura completa de la fila
                  *   → el sticky tiene espacio para moverse dentro de él.
                  * top calculado con 50vh para centrar visualmente la preview
                  *   en la pantalla mientras se scrollea. Usamos inline style
                  *   porque Tailwind JIT no compila calc() en clases arbitrarias
                  *   con fiabilidad en todos los entornos de build.
                  */}
                <aside className="hidden lg:block lg:self-stretch">
                    <div
                        className="sticky flex justify-center rounded-2xl border border-slate-100 bg-slate-50 p-6"
                        style={{ top: 'calc(50vh - 260px)' }}
                    >
                        <QrPosterPreview payload={payload} savedBgUrl={savedBgUrl} />
                    </div>
                </aside>

                {/* Preview — mobile (no sticky, apilada debajo del editor) */}
                <div className="flex items-start justify-center rounded-2xl border border-slate-100 bg-slate-50 p-6 lg:hidden">
                    <QrPosterPreview payload={payload} savedBgUrl={savedBgUrl} />
                </div>
            </div>

            {/* Panel de diseños guardados */}
            <SavedDesignsPanel currentPayload={payload} onLoad={handleLoadDesign} />
        </div>
    );
}

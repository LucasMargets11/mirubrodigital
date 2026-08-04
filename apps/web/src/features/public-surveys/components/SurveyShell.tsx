'use client';

import Image from 'next/image';
import type { ReactNode } from 'react';

interface Props {
    displayName: string;
    /** Subtítulo bajo la marca en el header (opcional). */
    headerTagline?: string;
    /** URL pública de la imagen del logo (servida desde `/public`). */
    brandLogoSrc?: string;
    /** Alto del logo en px (mobile-first). */
    brandLogoHeight?: number;
    /** Texto alternativo del logo. */
    brandLogoAlt?: string;
    /** Paso actual (1-based) usado para el progreso. `null` = sin progreso. */
    currentStep?: number | null;
    /** Total de pasos para el progreso. */
    totalSteps?: number | null;
    /** Si está presente, se renderiza el botón "← Atrás". */
    onBack?: (() => void) | null;
    /** Etiqueta tipo "eyebrow" debajo del header (ej: nombre de categoría activa). */
    eyebrow?: string | null;
    children: ReactNode;
}

/* ── SurveyShell ──────────────────────────────────────────────────────────
 *
 * Layout mobile del MVP demo. Estructura:
 *   ┌──────────────────────────────┐
 *   │  [M]  McDonald's Recoleta    │  ← header blanco compacto
 *   │       Queremos conocer …     │
 *   ├──────────────────────────────┤  ← línea roja full-width
 *   │  ← Atrás        Paso 1 de 3  │  ← toolbar discreta (solo si aplica)
 *   │  [EYEBROW]                   │
 *   │                              │
 *   │  contenido                   │
 *   │                              │
 *   └──────────────────────────────┘
 */
export function SurveyShell({
    displayName,
    headerTagline = 'Queremos conocer tu experiencia',
    brandLogoSrc,
    brandLogoHeight = 64,
    brandLogoAlt,
    currentStep = null,
    totalSteps = null,
    onBack = null,
    eyebrow = null,
    children,
}: Props) {
    const showProgress =
        currentStep !== null && totalSteps !== null && totalSteps > 0;
    const showToolbar = Boolean(onBack) || showProgress;
    // Aproximación de aspect ratio para la "M" de McDonald's (cuadrada).
    const logoWidth = brandLogoHeight;

    return (
        <div className="flex min-h-[100svh] flex-col bg-white text-slate-900">
            {/* Header blanco compacto + línea roja full-width */}
            <header className="bg-white">
                <div className="mx-auto flex w-full max-w-sm items-center gap-3 px-3 pt-3 pb-3">
                    {brandLogoSrc && (
                        <Image
                            src={brandLogoSrc}
                            alt={brandLogoAlt ?? displayName}
                            width={logoWidth}
                            height={brandLogoHeight}
                            priority
                            className="h-16 w-auto shrink-0"
                        />
                    )}
                    <div className="flex min-w-0 flex-1 flex-col items-center text-center">
                        <span className="w-full truncate text-[14px] font-bold leading-tight text-black">
                            {displayName}
                        </span>
                        {headerTagline && (
                            <span className="mt-0.5 w-full truncate text-[12px] font-medium leading-tight text-slate-700">
                                {headerTagline}
                            </span>
                        )}
                    </div>
                </div>
                <div
                    aria-hidden="true"
                    className="h-[3px] w-full bg-[#DA291C]"
                />
            </header>

            {/* Toolbar discreta (Atrás + progreso). Solo si corresponde. */}
            {showToolbar && (
                <div className="mx-auto w-full max-w-sm px-5 pt-3">
                    <div className="flex items-center justify-between">
                        {onBack ? (
                            <button
                                type="button"
                                onClick={onBack}
                                aria-label="Volver al paso anterior"
                                className="-ml-1 inline-flex items-center gap-1 rounded-md px-2 py-1 text-[13px] font-medium text-slate-600 transition-colors hover:text-black focus:outline-none focus-visible:ring-2 focus-visible:ring-[#DA291C] focus-visible:ring-offset-2"
                            >
                                <span aria-hidden="true">←</span>
                                Atrás
                            </button>
                        ) : (
                            <span aria-hidden="true" />
                        )}
                        {showProgress && (
                            <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
                                Paso {currentStep} de {totalSteps}
                            </span>
                        )}
                    </div>
                </div>
            )}

            {/* Contenido principal */}
            <main className="flex flex-1 justify-center px-5 pb-10 pt-5">
                <div className="flex w-full max-w-sm flex-col gap-5">
                    {eyebrow && (
                        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-[#DA291C]">
                            {eyebrow}
                        </p>
                    )}
                    {children}
                </div>
            </main>
        </div>
    );
}

'use client';

import { useState } from 'react';

import type { QrPosterDesign, QrPosterDesignPayload } from '../designs-types';
import { useQrPosterDesigns } from '../designs-hooks';
import { SavedDesignCard } from './SavedDesignCard';
import { SaveDesignDialog } from './SaveDesignDialog';
import type { GenerateQrPosterPayload } from '../types';

interface Props {
    /** El payload actual en el editor, para guardarlo como nuevo diseño. */
    currentPayload: GenerateQrPosterPayload;
    /** Callback cuando el usuario carga un diseño guardado. */
    onLoad: (payload: QrPosterDesignPayload, backgroundImageUrl?: string | null) => void;
}

/**
 * Panel lateral de diseños guardados para Carteles QR de Reseñas PRO.
 *
 * - Muestra contador X/5
 * - Botón "Guardar diseño actual" → abre diálogo con nombre
 * - Lista de cards: Cargar / Actualizar / Eliminar
 */
export function SavedDesignsPanel({ currentPayload, onLoad }: Props) {
    const {
        designs,
        limit,
        loading,
        saving,
        error,
        saveDesign,
        updateDesign,
        removeDesign,
        clearError,
    } = useQrPosterDesigns();

    const [dialogOpen, setDialogOpen] = useState(false);
    const [activeDesignId, setActiveDesignId] = useState<string | null>(null);

    const count = designs.length;
    const atLimit = count >= limit;

    // ── Guardar nuevo diseño ────────────────────────────────────────────────

    function openSaveDialog() {
        clearError();
        setDialogOpen(true);
    }

    async function handleSave(name: string) {
        const { background_image, ...payloadWithoutFile } = currentPayload;
        const result = await saveDesign({
            name,
            payload: payloadWithoutFile,
            background_image: background_image instanceof File ? background_image : null,
        });
        if (result) {
            setDialogOpen(false);
            setActiveDesignId(result.id);
            // Sync savedBgUrl to the persisted server URL so the preview
            // uses the stable media URL, not the in-memory blob URL.
            onLoad(result.payload, result.background_image_url);
        }
    }

    // ── Cargar diseño ───────────────────────────────────────────────────────

    function handleLoad(design: QrPosterDesign) {
        setActiveDesignId(design.id);
        onLoad(design.payload, design.background_image_url);
    }

    // ── Actualizar diseño activo ────────────────────────────────────────────

    async function handleUpdate(design: QrPosterDesign) {
        const { background_image, ...payloadWithoutFile } = currentPayload;
        const updated = await updateDesign(design.id, {
            payload: payloadWithoutFile,
            background_image: background_image instanceof File ? background_image : null,
        });
        if (updated) {
            // Keep savedBgUrl in sync after updating (especially when a new
            // image was uploaded — the old blob URL is now stale).
            onLoad(updated.payload, updated.background_image_url);
        }
    }

    // ── Eliminar diseño ─────────────────────────────────────────────────────

    async function handleDelete(id: string) {
        const ok = await removeDesign(id);
        if (ok && activeDesignId === id) {
            setActiveDesignId(null);
        }
    }

    // ── Render ──────────────────────────────────────────────────────────────

    return (
        <>
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                {/* Header */}
                <div className="mb-4 flex items-center justify-between">
                    <div>
                        <h2 className="text-sm font-semibold text-slate-900">Diseños guardados</h2>
                        <p className="mt-0.5 text-xs text-slate-500">
                            Guardá hasta {limit} diseños para reutilizarlos.
                        </p>
                    </div>
                    <span
                        className={[
                            'rounded-full px-2.5 py-0.5 text-xs font-medium',
                            atLimit
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-slate-100 text-slate-600',
                        ].join(' ')}
                    >
                        {count}/{limit}
                    </span>
                </div>

                {/* Error banner */}
                {error && (
                    <div className="mb-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5">
                        <p className="flex-1 text-sm text-red-700">{error}</p>
                        <button
                            type="button"
                            onClick={clearError}
                            className="shrink-0 text-red-400 hover:text-red-600"
                            aria-label="Cerrar error"
                        >
                            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                )}

                {/* Botón guardar */}
                <button
                    type="button"
                    onClick={openSaveDialog}
                    disabled={atLimit || saving}
                    title={atLimit ? 'Llegaste al límite de 5 diseños guardados' : undefined}
                    className="mb-4 flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    Guardar diseño actual
                    {atLimit && (
                        <span className="ml-1 text-xs text-amber-600">(límite alcanzado)</span>
                    )}
                </button>

                {/* Lista de diseños */}
                {loading ? (
                    <div className="space-y-2">
                        {[1, 2].map((i) => (
                            <div
                                key={i}
                                className="h-16 w-full animate-pulse rounded-xl bg-slate-100"
                            />
                        ))}
                    </div>
                ) : designs.length === 0 ? (
                    <p className="py-4 text-center text-sm text-slate-400">
                        No hay diseños guardados todavía.
                    </p>
                ) : (
                    <div className="space-y-2">
                        {designs.map((d) => (
                            <SavedDesignCard
                                key={d.id}
                                design={d}
                                isActive={d.id === activeDesignId}
                                onLoad={handleLoad}
                                onUpdate={handleUpdate}
                                onDelete={(id) => void handleDelete(id)}
                            />
                        ))}
                    </div>
                )}
            </div>

            {/* Diálogo de guardar */}
            <SaveDesignDialog
                open={dialogOpen}
                saving={saving}
                error={dialogOpen ? error : null}
                onSave={(name) => void handleSave(name)}
                onClose={() => {
                    setDialogOpen(false);
                    clearError();
                }}
            />
        </>
    );
}

'use client';

import { useState } from 'react';

import { generatePdfFromDesign } from '../designs-api';
import type { QrPosterDesign } from '../designs-types';

interface Props {
    design: QrPosterDesign;
    isActive: boolean;
    onLoad: (design: QrPosterDesign) => void;
    onUpdate: (design: QrPosterDesign) => void;
    onDelete: (id: string) => void;
}

function formatDate(iso: string): string {
    try {
        return new Date(iso).toLocaleDateString('es-AR', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
        });
    } catch {
        return iso;
    }
}

/**
 * Card individual de un diseño guardado.
 * Muestra mini-preview de color/imagen, nombre, fecha y acciones.
 */
export function SavedDesignCard({ design, isActive, onLoad, onUpdate, onDelete }: Props) {
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [downloading, setDownloading] = useState(false);
    const [downloadError, setDownloadError] = useState<string | null>(null);

    const { name, payload, background_image_url, updated_at } = design;
    const hasImageBg = payload.background_mode === 'image' && background_image_url;

    async function handleDownloadPdf() {
        setDownloading(true);
        setDownloadError(null);
        try {
            await generatePdfFromDesign(design.id);
        } catch (e) {
            setDownloadError((e as Error).message ?? 'Error al descargar PDF.');
        } finally {
            setDownloading(false);
        }
    }

    return (
        <div
            className={[
                'flex items-center gap-3 rounded-xl border p-3 transition-colors',
                isActive
                    ? 'border-slate-900 bg-slate-50'
                    : 'border-slate-200 bg-white',
            ].join(' ')}
        >
            {/* Mini color/image preview */}
            <div
                className="h-12 w-12 shrink-0 rounded-lg border border-slate-100 overflow-hidden"
                style={
                    hasImageBg
                        ? undefined
                        : { backgroundColor: payload.background_color ?? '#FFFFFF' }
                }
                aria-hidden="true"
            >
                {hasImageBg && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                        src={background_image_url!}
                        alt=""
                        className="h-full w-full object-cover"
                    />
                )}
            </div>

            {/* Info */}
            <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-slate-800">{name}</p>
                <p className="mt-0.5 text-xs text-slate-400">{formatDate(updated_at)}</p>
                {isActive && (
                    <p className="mt-0.5 text-xs font-medium text-slate-500">Cargado</p>
                )}
            </div>

            {/* Actions */}
            {confirmDelete ? (
                <div className="flex shrink-0 flex-col gap-1">
                    <p className="text-xs text-slate-500">¿Eliminar?</p>
                    <div className="flex gap-1">
                        <button
                            type="button"
                            onClick={() => onDelete(design.id)}
                            className="rounded-lg bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700"
                        >
                            Sí
                        </button>
                        <button
                            type="button"
                            onClick={() => setConfirmDelete(false)}
                            className="rounded-lg border border-slate-200 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                        >
                            No
                        </button>
                    </div>
                </div>
            ) : (
                <div className="flex shrink-0 flex-col gap-1">
                    {!isActive && (
                        <button
                            type="button"
                            onClick={() => onLoad(design)}
                            className="rounded-lg bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-700"
                        >
                            Cargar
                        </button>
                    )}
                    {isActive && (
                        <button
                            type="button"
                            onClick={() => onUpdate(design)}
                            className="rounded-lg border border-slate-900 px-2.5 py-1 text-xs font-medium text-slate-900 hover:bg-slate-100"
                        >
                            Actualizar
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={() => void handleDownloadPdf()}
                        disabled={downloading}
                        className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:border-slate-400 hover:text-slate-800 disabled:opacity-50"
                    >
                        {downloading ? 'Generando…' : 'Descargar PDF'}
                    </button>
                    {downloadError && (
                        <p className="max-w-[120px] text-xs text-red-600">{downloadError}</p>
                    )}
                    <button
                        type="button"
                        onClick={() => setConfirmDelete(true)}
                        className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-500 hover:border-red-300 hover:text-red-600"
                    >
                        Eliminar
                    </button>
                </div>
            )}
        </div>
    );
}

'use client';

import { useRef, useState } from 'react';
import { useBusinessBrandingQuery, useUploadBusinessLogoMutation, useUpdateBusinessBrandingMutation } from './hooks';

const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const ACCEPTED_TYPES_LABEL = 'PNG, JPG o WebP';

function validateImageFile(file: File): string | null {
    if (file.size > MAX_FILE_SIZE) return 'El archivo supera el límite de 5 MB.';
    if (!ACCEPTED_TYPES.includes(file.type)) return `Solo se aceptan ${ACCEPTED_TYPES_LABEL}.`;
    return null;
}

interface LogoSlotProps {
    label: string;
    hint: string;
    currentUrl: string | null | undefined;
    uploading: boolean;
    error: string | null;
    onFileChange: (file: File) => void;
    onClear?: () => void;
}

function LogoSlot({ label, hint, currentUrl, uploading, error, onFileChange, onClear }: LogoSlotProps) {
    const inputRef = useRef<HTMLInputElement>(null);
    const [localError, setLocalError] = useState<string | null>(null);
    const displayError = error ?? localError;

    function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
        const file = e.currentTarget.files?.[0];
        e.currentTarget.value = '';
        if (!file) return;
        const err = validateImageFile(file);
        if (err) { setLocalError(err); return; }
        setLocalError(null);
        onFileChange(file);
    }

    return (
        <div className="space-y-2">
            <p className="text-sm font-medium text-slate-700">{label}</p>
            <p className="text-xs text-slate-400">{hint}</p>

            <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="h-14 w-24 shrink-0 overflow-hidden rounded-lg border border-slate-200 bg-white flex items-center justify-center">
                    {currentUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                            src={currentUrl}
                            alt={label}
                            className="h-full w-full object-contain p-1"
                            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                        />
                    ) : (
                        <span className="text-[10px] text-slate-400 text-center leading-tight px-1">Sin logo</span>
                    )}
                </div>

                <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                        <button
                            type="button"
                            onClick={() => inputRef.current?.click()}
                            disabled={uploading}
                            className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors disabled:opacity-50"
                        >
                            {uploading ? 'Subiendo…' : currentUrl ? 'Reemplazar' : 'Subir logo'}
                        </button>

                        {currentUrl && onClear && (
                            <button
                                type="button"
                                onClick={onClear}
                                disabled={uploading}
                                className="rounded-full border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                            >
                                Quitar
                            </button>
                        )}
                    </div>

                    <p className="text-[11px] text-slate-400">{ACCEPTED_TYPES_LABEL} · máx 5 MB</p>
                </div>

                <input
                    ref={inputRef}
                    type="file"
                    accept={ACCEPTED_TYPES.join(',')}
                    className="hidden"
                    onChange={handleFile}
                    disabled={uploading}
                />
            </div>

            {displayError && (
                <p className="text-xs text-red-600">{displayError}</p>
            )}
        </div>
    );
}

interface ColorSwatchProps {
    value: string;
    onChange: (hex: string) => void;
    saving: boolean;
}

function ColorSwatch({ value, onChange, saving }: ColorSwatchProps) {
    const [localValue, setLocalValue] = useState(value);
    const [hexError, setHexError] = useState(false);

    function handleText(e: React.ChangeEvent<HTMLInputElement>) {
        const v = e.target.value;
        setLocalValue(v);
        const valid = /^#([0-9A-Fa-f]{3}){1,2}$/.test(v);
        setHexError(!valid);
        if (valid) onChange(v.toLowerCase());
    }

    return (
        <div className="flex items-center gap-2">
            <input
                type="color"
                value={!hexError ? localValue : '#000000'}
                onChange={(e) => {
                    setLocalValue(e.target.value);
                    setHexError(false);
                    onChange(e.target.value);
                }}
                disabled={saving}
                className="h-9 w-9 rounded-md cursor-pointer border border-slate-200 p-0 shadow-sm disabled:opacity-50"
            />
            <div className="relative flex-1 max-w-[120px]">
                <input
                    type="text"
                    value={localValue}
                    onChange={handleText}
                    disabled={saving}
                    maxLength={7}
                    className={`w-full rounded-md border px-2 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 disabled:opacity-50 ${
                        hexError ? 'border-red-400 focus:ring-red-200' : 'border-slate-200 focus:ring-brand-200'
                    }`}
                />
            </div>
            {hexError && <span className="text-[10px] text-red-500">Hex inválido</span>}
        </div>
    );
}

export interface BusinessBrandingPanelProps {
    /**
     * When set, the "no logo" warning in Carteles will link to this path.
     * Defaults to "/app/resenas/configuracion#marca".
     */
    brandingConfigPath?: string;
}

/**
 * Panel reutilizable para cargar y editar el branding global del negocio
 * (logo horizontal, logo vertical/cuadrado y color principal).
 *
 * Puede usarse en QR de Reseñas, Carta Online o cualquier producto sin
 * depender de Gestión Comercial.
 */
export function BusinessBrandingPanel(_props: BusinessBrandingPanelProps = {}) {
    const brandingQuery = useBusinessBrandingQuery();
    const uploadMutation = useUploadBusinessLogoMutation();
    const updateMutation = useUpdateBusinessBrandingMutation();

    const [horizontalError, setHorizontalError] = useState<string | null>(null);
    const [squareError, setSquareError] = useState<string | null>(null);
    const [colorSaved, setColorSaved] = useState(false);

    const branding = brandingQuery.data;

    async function handleUpload(file: File, type: 'horizontal' | 'square') {
        if (type === 'horizontal') setHorizontalError(null);
        else setSquareError(null);

        try {
            await uploadMutation.mutateAsync({ file, type });
        } catch {
            const msg = 'Error al subir el logo. Intentá de nuevo.';
            if (type === 'horizontal') setHorizontalError(msg);
            else setSquareError(msg);
        }
    }

    async function handleColorChange(hex: string) {
        setColorSaved(false);
        try {
            await updateMutation.mutateAsync({ accent_color: hex });
            setColorSaved(true);
            setTimeout(() => setColorSaved(false), 2000);
        } catch {
            // silent — color picker already has local state
        }
    }

    if (brandingQuery.isPending) {
        return (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm animate-pulse">
                <div className="h-4 w-32 bg-slate-200 rounded mb-4" />
                <div className="h-14 bg-slate-100 rounded-xl" />
            </div>
        );
    }

    return (
        <section id="marca" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-6">
            <div>
                <h2 className="text-sm font-semibold text-slate-900">Marca del negocio</h2>
                <p className="mt-1 text-xs text-slate-500">
                    Subí el logo de tu negocio para usarlo en tu página de reseñas, tus QR y los carteles imprimibles.
                </p>
            </div>

            {/* Logo horizontal */}
            <LogoSlot
                label="Logo horizontal"
                hint="Funciona mejor para encabezados y carteles anchos. Proporción recomendada: 3:1 a 5:1."
                currentUrl={branding?.logo_horizontal_url}
                uploading={uploadMutation.isPending && uploadMutation.variables?.type === 'horizontal'}
                error={horizontalError}
                onFileChange={(file) => void handleUpload(file, 'horizontal')}
            />

            {/* Logo vertical / cuadrado */}
            <LogoSlot
                label="Logo vertical / cuadrado"
                hint="Funciona mejor para QR, tarjetas, carteles compactos y vista mobile. Proporción recomendada: 1:1."
                currentUrl={branding?.logo_square_url}
                uploading={uploadMutation.isPending && uploadMutation.variables?.type === 'square'}
                error={squareError}
                onFileChange={(file) => void handleUpload(file, 'square')}
            />

            {/* Color principal */}
            <div className="space-y-2">
                <p className="text-sm font-medium text-slate-700">Color principal</p>
                <p className="text-xs text-slate-400">
                    Se usa en QR, carteles y la página de reseñas pública.
                </p>
                <div className="flex items-center gap-3">
                    <ColorSwatch
                        value={branding?.accent_color ?? '#2563eb'}
                        onChange={(hex) => void handleColorChange(hex)}
                        saving={updateMutation.isPending}
                    />
                    {colorSaved && (
                        <span className="text-xs text-emerald-600 font-medium">Guardado ✓</span>
                    )}
                    {updateMutation.isPending && (
                        <span className="text-xs text-slate-400">Guardando…</span>
                    )}
                </div>
            </div>

            {/* SVG advisory */}
            <p className="text-[11px] text-slate-400 border-t border-slate-100 pt-4">
                Tip: evitá subir SVG si vas a usar el logo en PDFs imprimibles. Usá PNG con fondo transparente para mejores resultados.
            </p>
        </section>
    );
}

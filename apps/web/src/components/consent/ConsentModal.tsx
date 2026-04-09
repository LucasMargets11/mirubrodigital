'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useConsent } from '@/lib/consent/ConsentProvider';

export function ConsentModal() {
    const { preferences, savePreferences, closePreferences } = useConsent();
    const [analytics, setAnalytics] = useState(preferences?.analytics ?? false);
    const [marketing, setMarketing] = useState(preferences?.marketing ?? false);
    const overlayRef = useRef<HTMLDivElement>(null);
    const panelRef = useRef<HTMLDivElement>(null);

    // Sync toggles to current preferences when modal opens.
    useEffect(() => {
        if (preferences) {
            setAnalytics(preferences.analytics);
            setMarketing(preferences.marketing);
        }
    }, [preferences]);

    // Trap focus inside modal.
    useEffect(() => {
        const prev = document.activeElement as HTMLElement | null;
        panelRef.current?.focus();
        return () => prev?.focus();
    }, []);

    // Close on Escape.
    useEffect(() => {
        function onKey(e: KeyboardEvent) {
            if (e.key === 'Escape') closePreferences();
        }
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [closePreferences]);

    const handleSave = useCallback(() => {
        savePreferences({ analytics, marketing });
    }, [analytics, marketing, savePreferences]);

    const handleOverlayClick = useCallback(
        (e: React.MouseEvent) => {
            if (e.target === overlayRef.current) closePreferences();
        },
        [closePreferences],
    );

    return (
        <div
            ref={overlayRef}
            onClick={handleOverlayClick}
            className="fixed inset-0 z-[10000] flex items-end sm:items-center justify-center bg-black/40"
            role="presentation"
        >
            <div
                ref={panelRef}
                role="dialog"
                aria-modal="true"
                aria-label="Configurar cookies"
                tabIndex={-1}
                className="w-full max-w-lg rounded-t-2xl sm:rounded-2xl bg-white p-5 sm:p-6 shadow-xl outline-none animate-in slide-in-from-bottom-4 sm:slide-in-from-bottom-0 sm:fade-in duration-200"
            >
                <h2 className="text-base font-semibold text-slate-900">
                    Preferencias de cookies
                </h2>
                <p className="mt-1 text-sm text-slate-500 leading-relaxed">
                    Elegí qué tipos de cookies querés permitir. Las necesarias no se pueden
                    desactivar.
                </p>

                <div className="mt-5 space-y-4">
                    {/* Necessary — always on */}
                    <CategoryRow
                        label="Necesarias"
                        description="Autenticación, seguridad y funcionamiento básico."
                        checked
                        disabled
                    />

                    {/* Analytics */}
                    <CategoryRow
                        label="Analíticas"
                        description="Nos ayudan a entender cómo se usa el sitio."
                        checked={analytics}
                        onChange={setAnalytics}
                    />

                    {/* Marketing */}
                    <CategoryRow
                        label="Marketing"
                        description="Permiten mostrar publicidad relevante."
                        checked={marketing}
                        onChange={setMarketing}
                    />
                </div>

                <div className="mt-6 flex items-center justify-end gap-3">
                    <button
                        type="button"
                        onClick={closePreferences}
                        className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2"
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        onClick={handleSave}
                        className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
                    >
                        Guardar preferencias
                    </button>
                </div>
            </div>
        </div>
    );
}

/* ── Toggle row ──────────────────────────────────────────────────── */

function CategoryRow({
    label,
    description,
    checked,
    disabled,
    onChange,
}: {
    label: string;
    description: string;
    checked: boolean;
    disabled?: boolean;
    onChange?: (val: boolean) => void;
}) {
    const id = `consent-${label.toLowerCase()}`;

    return (
        <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
                <label htmlFor={id} className="text-sm font-medium text-slate-800">
                    {label}
                </label>
                <p className="text-xs text-slate-500 leading-snug">{description}</p>
            </div>

            <button
                id={id}
                type="button"
                role="switch"
                aria-checked={checked}
                disabled={disabled}
                onClick={() => onChange?.(!checked)}
                className={`relative mt-0.5 inline-flex h-6 w-10 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 ${
                    disabled
                        ? 'cursor-not-allowed bg-slate-300'
                        : checked
                          ? 'cursor-pointer bg-slate-900'
                          : 'cursor-pointer bg-slate-200'
                }`}
            >
                <span
                    className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform ${
                        checked ? 'translate-x-[18px]' : 'translate-x-[3px]'
                    }`}
                />
            </button>
        </div>
    );
}

'use client';

import { useEffect, useRef, useState } from 'react';

interface Props {
    open: boolean;
    defaultName?: string;
    saving: boolean;
    error: string | null;
    onSave: (name: string) => void;
    onClose: () => void;
}

/**
 * Modal simple para nombrar un diseño antes de guardarlo.
 */
export function SaveDesignDialog({ open, defaultName = '', saving, error, onSave, onClose }: Props) {
    const [name, setName] = useState(defaultName);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (open) {
            setName(defaultName);
            // Focus the input after the dialog renders
            setTimeout(() => inputRef.current?.focus(), 50);
        }
    }, [open, defaultName]);

    if (!open) return null;

    function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        const trimmed = name.trim();
        if (!trimmed) return;
        onSave(trimmed);
    }

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
            role="dialog"
            aria-modal="true"
            aria-label="Guardar diseño"
        >
            <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl">
                <h2 className="mb-1 text-base font-semibold text-slate-900">Guardar diseño</h2>
                <p className="mb-4 text-sm text-slate-500">
                    Podrás cargar este diseño más adelante desde el historial.
                </p>

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label
                            htmlFor="design-name-input"
                            className="mb-1 block text-sm font-medium text-slate-700"
                        >
                            Nombre del diseño
                        </label>
                        <input
                            id="design-name-input"
                            ref={inputRef}
                            type="text"
                            value={name}
                            maxLength={100}
                            placeholder="Ej: Cartel navideño"
                            onChange={(e) => setName(e.target.value)}
                            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
                            disabled={saving}
                        />
                    </div>

                    {error && (
                        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                            {error}
                        </p>
                    )}

                    <div className="flex gap-2">
                        <button
                            type="button"
                            onClick={onClose}
                            disabled={saving}
                            className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
                        >
                            Cancelar
                        </button>
                        <button
                            type="submit"
                            disabled={saving || !name.trim()}
                            className="flex-1 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {saving ? 'Guardando…' : 'Guardar'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

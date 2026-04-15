'use client';

import { MenuLayoutEditor } from '@/components/app/menu-layout-editor';

interface EstructuraClientProps {
    canUploadImages: boolean;
}

export function EstructuraClient({ canUploadImages }: EstructuraClientProps) {
    return (
        <div className="p-6 space-y-6 animate-in fade-in">
            <div>
                <h1 className="text-2xl font-bold tracking-tight">Estructura de la Carta</h1>
                <p className="text-sm text-slate-500 mt-1">
                    Agrupá y ordená tus categorías en secciones (bloques). El orden se refleja inmediatamente en la carta pública.
                </p>
            </div>

            {!canUploadImages && (
                <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    <span>📷</span>
                    <p>
                        Las imágenes de categoría están disponibles en planes superiores.{' '}
                        <a href="/app/planes" className="font-semibold underline">Ver planes</a>
                    </p>
                </div>
            )}

            <div className="bg-white rounded-xl border shadow-sm p-5">
                <MenuLayoutEditor canUploadImages={canUploadImages} />
            </div>
        </div>
    );
}

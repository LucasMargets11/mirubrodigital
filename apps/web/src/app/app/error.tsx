'use client';

import { useEffect } from 'react';

export default function AppError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        console.error('[AppError]', error);
    }, [error]);

    return (
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center">
            <h2 className="text-2xl font-bold text-slate-900">Algo salió mal</h2>
            <p className="max-w-md text-slate-600">
                Ocurrió un error inesperado. Intentá nuevamente o recargá la página.
            </p>
            <button
                onClick={reset}
                className="rounded-full bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-brand-700"
            >
                Reintentar
            </button>
        </div>
    );
}

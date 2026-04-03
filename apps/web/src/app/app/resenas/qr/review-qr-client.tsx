'use client';

import { useState, useEffect } from 'react';
import { getReviewQrCode, type ReviewQrResponse } from '@/features/reviews/api';

interface Props {
    businessName: string;
}

export function ReviewQrClient({ businessName }: Props) {
    const [data, setData] = useState<ReviewQrResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [copied, setCopied] = useState(false);

    function fetchQr() {
        setLoading(true);
        setError(false);
        getReviewQrCode()
            .then(setData)
            .catch(() => setError(true))
            .finally(() => setLoading(false));
    }

    useEffect(() => {
        fetchQr();
    }, []);

    async function copyUrl() {
        if (!data?.public_url) return;
        await navigator.clipboard.writeText(data.public_url);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }

    function downloadSvg() {
        if (!data?.qr_svg) return;
        // qr_svg is a data URI: "data:image/svg+xml;base64,..."
        const base64 = data.qr_svg.split(',')[1];
        if (!base64) return;
        const blob = new Blob([atob(base64)], { type: 'image/svg+xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `qr-resenas-${data.slug}.svg`;
        a.click();
        URL.revokeObjectURL(url);
    }

    return (
        <>
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">
                    QR de Reseñas
                </p>
                <h1 className="text-3xl font-display font-bold text-slate-900">Mi QR</h1>
                <p className="text-sm text-slate-500">{businessName}</p>
            </header>

            {loading ? (
                <div className="flex h-64 items-center justify-center rounded-2xl border border-slate-200 bg-white">
                    <p className="text-sm text-slate-400">Generando código QR…</p>
                </div>
            ) : error ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
                    <p className="text-sm font-semibold text-red-700">
                        No se pudo generar el QR. Verificá que tu negocio tenga un slug configurado.
                    </p>
                    <button
                        onClick={fetchQr}
                        className="mt-3 rounded-full border border-red-300 px-4 py-2 text-xs font-semibold text-red-700 hover:bg-red-100 transition-colors"
                    >
                        Reintentar
                    </button>
                </div>
            ) : data ? (
                <div className="grid gap-6 lg:grid-cols-2">
                    <div className="flex flex-col items-center gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        {data.qr_svg && (
                            <img
                                src={data.qr_svg}
                                alt="Código QR de reseñas"
                                className="h-56 w-56 rounded-xl"
                            />
                        )}
                        <div className="flex flex-wrap gap-2">
                            <button
                                onClick={downloadSvg}
                                className="rounded-full bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors"
                            >
                                Descargar SVG
                            </button>
                            <button
                                onClick={fetchQr}
                                className="rounded-full border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
                            >
                                Regenerar
                            </button>
                        </div>
                    </div>

                    <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        <h2 className="text-lg font-semibold text-slate-900">Enlace público</h2>
                        <p className="text-sm text-slate-500">
                            Tus clientes escanean el QR o visitan este link y son redirigidos
                            a la página de reseñas de Google de tu negocio.
                        </p>
                        <div className="flex items-center gap-2">
                            <code className="flex-1 truncate rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700">
                                {data.public_url}
                            </code>
                            <button
                                onClick={copyUrl}
                                className="shrink-0 rounded-full border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
                            >
                                {copied ? '¡Copiado!' : 'Copiar'}
                            </button>
                        </div>
                    </div>
                </div>
            ) : null}
        </>
    );
}

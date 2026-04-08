'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import type { Route } from 'next';
import { getReviewQrCode, getReviewSettings } from '@/features/reviews/api';
import type { ReviewQrResponse, ReviewConfig } from '@/features/reviews/types';
import { PRODUCT, PRODUCT_FLOW_STEPS, SMART_FILTER } from '@/features/reviews/product';

interface Props {
    businessName: string;
}

export function ReviewQrClient({ businessName }: Props) {
    const [data, setData] = useState<ReviewQrResponse | null>(null);
    const [config, setConfig] = useState<ReviewConfig | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [copied, setCopied] = useState(false);

    function fetchData() {
        setLoading(true);
        setError(false);
        Promise.all([
            getReviewQrCode(),
            getReviewSettings().catch(() => null),
        ])
            .then(([qr, cfg]) => {
                setData(qr);
                setConfig(cfg);
            })
            .catch(() => setError(true))
            .finally(() => setLoading(false));
    }

    useEffect(() => {
        fetchData();
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

    /* ── Config warnings ───────────────────────────────────── */
    const warnings: string[] = [];
    if (config && !config.enabled) {
        warnings.push('Las reseñas están desactivadas. Aunque el QR funciona, tus clientes no podrán dejar opiniones hasta que actives el servicio.');
    }
    if (config && !config.redirect_url) {
        warnings.push('No tenés una URL de redirección a Google configurada. Las calificaciones altas quedarán como feedback interno.');
    }

    return (
        <>
            <header className="space-y-1">
                <h1 className="text-3xl font-display font-bold text-slate-900">Mi QR</h1>
                <p className="text-sm text-slate-500">
                    Compartí este código para invitar a tus clientes a dejar una reseña ·{' '}
                    <span className="font-medium text-slate-700">{businessName}</span>
                </p>
            </header>

            {/* Warnings */}
            {warnings.map((msg, i) => (
                <div key={i} className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                    <span className="mt-0.5 shrink-0 text-amber-500">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                    </span>
                    <div className="flex-1">
                        <p className="text-sm text-amber-800">{msg}</p>
                        <Link
                            href={'/app/resenas/configuracion' as Route}
                            className="mt-1 inline-block text-xs font-semibold text-amber-700 underline underline-offset-2 hover:text-amber-900"
                        >
                            Ir a Configuración →
                        </Link>
                    </div>
                </div>
            ))}

            {loading ? (
                <div className="flex h-64 items-center justify-center rounded-2xl border border-slate-200 bg-white">
                    <p className="text-sm text-slate-400 animate-pulse">Generando código QR…</p>
                </div>
            ) : error ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
                    <p className="text-sm font-semibold text-red-700">
                        No se pudo generar el QR. Verificá que tu negocio tenga un slug configurado.
                    </p>
                    <button
                        onClick={fetchData}
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
                                onClick={fetchData}
                                className="rounded-full border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
                            >
                                Regenerar
                            </button>
                        </div>
                    </div>

                    <div className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        <div>
                            <h2 className="text-lg font-semibold text-slate-900">¿Cómo funciona?</h2>
                            <p className="mt-1 text-xs text-slate-500">{PRODUCT.tagline}</p>
                        </div>
                        <div className="space-y-3 text-sm text-slate-600">
                            {PRODUCT_FLOW_STEPS.map((step, i) => (
                                <div key={i} className="flex items-start gap-2">
                                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[10px] font-bold text-brand-700">{i + 1}</span>
                                    <div>
                                        <p className="font-medium text-slate-700">{step.title}</p>
                                        <p className="text-slate-500">{step.description}</p>
                                    </div>
                                </div>
                            ))}
                        </div>

                        <hr className="border-slate-100" />

                        {/* Smart filter */}
                        <div className="space-y-2">
                            <h3 className="text-sm font-bold text-slate-800">{SMART_FILTER.headline}</h3>
                            <p className="text-xs text-slate-600">{SMART_FILTER.description}</p>
                            <div className="grid gap-2">
                                {SMART_FILTER.bullets.map((b) => (
                                    <div key={b.label} className="flex items-center gap-2 rounded-lg bg-indigo-50/50 p-2.5 border border-indigo-100">
                                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-bold text-indigo-700">
                                            {b.label.startsWith('≥') ? '★' : '☆'}
                                        </span>
                                        <div className="text-xs">
                                            <p className="font-semibold text-slate-700">{b.label}</p>
                                            <p className="text-slate-500">{b.result}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <hr className="border-slate-100" />

                        <h3 className="text-sm font-semibold text-slate-700">Enlace público</h3>
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

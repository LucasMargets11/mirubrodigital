'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { Route } from 'next';

import { useMenuQrCode } from '@/features/menu/hooks';

interface Props {
    businessId: number;
    businessName: string;
}

export function MenuQrPageClient({ businessId, businessName }: Props) {
    const { data, isLoading, isError, refetch, isFetching } = useMenuQrCode(businessId);
    const [copied, setCopied] = useState(false);

    async function copyUrl() {
        if (!data?.public_url) return;
        await navigator.clipboard.writeText(data.public_url);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }

    function downloadSvg() {
        if (!data?.qr_svg) return;
        const blob = new Blob([atob(data.qr_svg)], { type: 'image/svg+xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `qr-menu-${businessId}.svg`;
        a.click();
        URL.revokeObjectURL(url);
    }

    return (
        <section className="space-y-6">
            <header>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-500">Menú Digital</p>
                <h1 className="text-3xl font-display font-bold text-slate-900">Código QR del menú</h1>
                <p className="text-sm text-slate-500">{businessName}</p>
            </header>

            {isLoading ? (
                <div className="flex h-64 items-center justify-center rounded-2xl border border-slate-200 bg-white">
                    <p className="text-sm text-slate-400">Generando código QR…</p>
                </div>
            ) : isError ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
                    <p className="text-sm font-semibold text-red-700">No se pudo obtener el código QR.</p>
                    <button
                        onClick={() => refetch()}
                        className="mt-3 rounded-full border border-red-300 px-4 py-2 text-xs font-semibold text-red-700 hover:bg-red-100 transition-colors"
                    >
                        Reintentar
                    </button>
                </div>
            ) : data ? (
                <div className="grid gap-6 lg:grid-cols-2">
                    {/* QR Display */}
                    <div className="flex flex-col items-center gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        {data.qr_svg && (
                            <img
                                src={`data:image/svg+xml;base64,${data.qr_svg}`}
                                alt="Código QR del menú"
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
                                onClick={() => refetch()}
                                disabled={isFetching}
                                className="rounded-full border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50"
                            >
                                {isFetching ? 'Generando…' : 'Regenerar QR'}
                            </button>
                        </div>
                        {data.generated_at && (
                            <p className="text-xs text-slate-400">
                                Generado: {new Date(data.generated_at).toLocaleString('es-AR')}
                            </p>
                        )}
                    </div>

                    {/* URL & Actions */}
                    <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">URL del menú público</p>
                            <div className="mt-1 flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                                <span className="flex-1 truncate text-sm text-slate-700">{data.public_url}</span>
                                <button
                                    onClick={copyUrl}
                                    className="shrink-0 rounded-md bg-white px-2 py-1 text-xs font-semibold text-slate-600 shadow-sm ring-1 ring-slate-200 hover:bg-slate-50 transition-colors"
                                >
                                    {copied ? '✓ Copiado' : 'Copiar'}
                                </button>
                            </div>
                        </div>

                        <div className="flex flex-col gap-2">
                            <a
                                href={data.public_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="rounded-full border border-brand-300 px-4 py-2.5 text-center text-sm font-semibold text-brand-700 hover:bg-brand-50 transition-colors"
                            >
                                Ver menú en línea ↗
                            </a>
                            <Link
                                href={'/app/menu/preview' as Route}
                                className="rounded-full border border-slate-300 px-4 py-2.5 text-center text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                            >
                                Vista previa completa
                            </Link>
                            <Link
                                href="/app/settings/online-menu"
                                className="rounded-full border border-slate-300 px-4 py-2.5 text-center text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                            >
                                Personalizar branding
                            </Link>
                        </div>
                    </div>
                </div>
            ) : null}
        </section>
    );
}

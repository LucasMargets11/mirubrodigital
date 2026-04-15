'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { getPublicMenuConfig, updatePublicMenuConfig } from '@/features/menu/api';
import { useMenuQrCode } from '@/features/menu/hooks';
import type { PublicMenuConfig, MenuQrResponse } from '@/features/menu/types';

function normalizeQrSrc(value?: string | null): string {
    if (!value) return '';
    const trimmed = value.trim();
    if (trimmed.startsWith('data:image/')) return trimmed;
    if (trimmed.startsWith('<svg')) return `data:image/svg+xml;utf8,${encodeURIComponent(trimmed)}`;
    return `data:image/svg+xml;base64,${trimmed}`;
}

interface Props {
    businessId: number;
    businessName: string;
    initialQrData: MenuQrResponse | null;
    customDomainAllowed?: boolean;
}

export function PublicacionClient({ businessId, businessName, initialQrData, customDomainAllowed }: Props) {
    const [config, setConfig] = useState<PublicMenuConfig | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [copied, setCopied] = useState(false);

    const { data: qrData, isLoading: qrLoading, refetch: refetchQr, isFetching: qrFetching } = useMenuQrCode(businessId);
    const qr = qrData ?? initialQrData;

    useEffect(() => {
        loadConfig();
    }, []);

    async function loadConfig() {
        try {
            const data = await getPublicMenuConfig();
            setConfig(data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    }

    async function handleSaveConfig() {
        if (!config) return;
        setSaving(true);
        try {
            const updated = await updatePublicMenuConfig({
                enabled: config.enabled,
                slug: config.slug,
            });
            setConfig(updated);
        } catch (e) {
            console.error(e);
        } finally {
            setSaving(false);
        }
    }

    async function copyUrl() {
        const url = qr?.public_url || (config ? `${window.location.origin}/m/${config.slug}` : '');
        if (!url) return;
        await navigator.clipboard.writeText(url);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }

    function downloadSvg() {
        if (!qr?.qr_svg) return;
        const src = normalizeQrSrc(qr.qr_svg);
        const base64 = src.includes(',') ? src.split(',')[1] : src;
        if (!base64) return;
        const blob = new Blob([atob(base64)], { type: 'image/svg+xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `qr-carta-${businessId}.svg`;
        a.click();
        URL.revokeObjectURL(url);
    }

    if (loading) return <div className="p-8">Cargando configuración...</div>;
    if (!config) return <div className="p-8">Error cargando configuración.</div>;

    const origin = typeof window !== 'undefined' ? window.location.origin : 'https://mirubro.digital';
    const publicUrl = qr?.public_url || `${origin}/m/${config.slug}`;

    return (
        <div className="p-6 space-y-8 animate-in fade-in">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Publicación</h1>
                    <p className="text-sm text-slate-500 mt-1">
                        Gestioná el QR, la URL pública y la vista previa de tu carta.
                    </p>
                </div>
                <Button onClick={handleSaveConfig} disabled={saving}>
                    {saving ? 'Guardando...' : 'Guardar Cambios'}
                </Button>
            </div>

            {/* ── Two-column layout ──────────────────────────────────── */}
            <div className="grid xl:grid-cols-[1fr_minmax(320px,400px)] gap-8">
                {/* ── Left column: configuration ─────────────────────────── */}
                <div className="space-y-6">

            {/* ── Habilitar / Deshabilitar ──────────────────────────────────── */}
            <div className="flex items-center space-x-4 bg-white p-4 rounded-lg border shadow-sm">
                <Switch
                    checked={config.enabled}
                    onCheckedChange={(c: boolean) => setConfig({ ...config, enabled: c })}
                />
                <div>
                    <label className="text-sm font-medium">Habilitar Carta Pública</label>
                    <p className="text-xs text-slate-500">Cuando está activa, tu carta es visible para cualquier persona con el enlace.</p>
                </div>
            </div>

            {!config.enabled && (
                <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-3 text-center text-sm text-slate-500">
                    Activá la carta pública para generar el QR y compartir el enlace.
                </div>
            )}

            {/* ── Slug ──────────────────────────────────────────────────────── */}
            <div className="bg-white p-4 rounded-lg border shadow-sm space-y-4">
                <h2 className="text-lg font-semibold">Dirección web</h2>
                <div>
                    <label className="block text-sm font-medium mb-1">Slug URL</label>
                    <div className="flex items-center gap-2">
                        <span className="text-slate-500 text-sm whitespace-nowrap">{origin}/m/</span>
                        <input
                            value={config.slug}
                            onChange={(e) => setConfig({ ...config, slug: e.target.value })}
                            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                    </div>
                    <p className="text-xs text-slate-500 mt-1">Identificador único para tu carta.</p>
                </div>
            </div>

            {/* ── URL pública ───────────────────────────────────────────────── */}
            <div className="bg-white p-4 rounded-lg border shadow-sm space-y-3">
                <h2 className="text-lg font-semibold">URL pública</h2>
                <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                    <span className="flex-1 truncate text-sm text-slate-700">{publicUrl}</span>
                    <button
                        onClick={copyUrl}
                        className="shrink-0 rounded-md bg-white px-2 py-1 text-xs font-semibold text-slate-600 shadow-sm ring-1 ring-slate-200 hover:bg-slate-50 transition-colors"
                    >
                        {copied ? '✓ Copiado' : 'Copiar'}
                    </button>
                </div>
                <div className="flex flex-wrap gap-2">
                    {config.enabled && (
                        <a
                            href={publicUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors"
                        >
                            Ver carta pública ↗
                        </a>
                    )}
                </div>
            </div>

            {/* ── Dominio personalizado ──────────────────────────────────── */}
            <div className="bg-white p-4 rounded-lg border shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold">Dominio personalizado</h2>
                    <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-500">Próximamente</span>
                </div>
                {customDomainAllowed ? (
                    <p className="text-sm text-slate-500">
                        Tu plan incluye dominio personalizado. Pronto vas a poder conectar tu propio dominio (ej. <span className="font-mono text-xs">carta.tunegocio.com</span>) a tu carta pública.
                    </p>
                ) : (
                    <p className="text-sm text-slate-500">
                        Conectá tu propio dominio a tu carta pública. Disponible en el{' '}
                        <a href="/app/planes" className="font-semibold text-amber-600 underline">plan Premium</a>.
                    </p>
                )}
            </div>

                </div>

                {/* ── Right column: QR + Preview (sticky) ────────────────── */}
                <div className="xl:sticky xl:top-6 self-start space-y-6">

            {/* ── QR ────────────────────────────────────────────────────────── */}
            <div className="bg-white p-4 rounded-lg border shadow-sm space-y-4">
                <h2 className="text-lg font-semibold">Código QR</h2>
                {qrLoading && !qr ? (
                    <div className="flex h-48 items-center justify-center">
                        <p className="text-sm text-slate-400">Generando código QR…</p>
                    </div>
                ) : qr?.qr_svg ? (
                    <div className="flex flex-col items-center gap-4">
                        <img
                            src={normalizeQrSrc(qr.qr_svg)}
                            alt="Código QR de la carta"
                            className="h-48 w-48 rounded-xl"
                        />
                        <div className="flex flex-wrap gap-2">
                            <button
                                onClick={downloadSvg}
                                className="rounded-full bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors"
                            >
                                Descargar SVG
                            </button>
                            <button
                                onClick={() => refetchQr()}
                                disabled={qrFetching}
                                className="rounded-full border border-slate-300 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50"
                            >
                                {qrFetching ? 'Generando…' : 'Regenerar QR'}
                            </button>
                        </div>
                        {qr.generated_at && (
                            <p className="text-xs text-slate-400">
                                Generado: {new Date(qr.generated_at).toLocaleString('es-AR')}
                            </p>
                        )}
                    </div>
                ) : (
                    <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center">
                        <p className="text-sm text-slate-500">Todavía no se generó un código QR.</p>
                        <button
                            onClick={() => refetchQr()}
                            disabled={qrFetching}
                            className="mt-3 rounded-full bg-brand-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors disabled:opacity-50"
                        >
                            {qrFetching ? 'Generando…' : 'Generar QR'}
                        </button>
                    </div>
                )}
            </div>

            {/* ── Vista previa ──────────────────────────────────────────────── */}
            {config.enabled && (
                <div className="bg-white p-4 rounded-lg border shadow-sm space-y-3">
                    <h2 className="text-lg font-semibold">Vista previa</h2>
                    <div className="w-full overflow-hidden rounded-2xl border border-slate-200 shadow-sm">
                        <iframe
                            src={publicUrl}
                            title="Vista previa de la carta"
                            className="h-[60vh] w-full"
                            style={{ border: 'none' }}
                        />
                    </div>
                </div>
            )}

                </div>
            </div>
        </div>
    );
}

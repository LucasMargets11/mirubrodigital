'use client'

import { useState, useEffect, useRef } from 'react'
import { Switch } from '@/components/ui/switch'
import { Button } from '@/components/ui/button'
import {
    getMenuEngagementSettings,
    updateMenuEngagementSettings,
    uploadEngagementQRImage,
    getMercadoPagoConnectionStatus,
    startMercadoPagoOAuth,
    disconnectMercadoPago,
} from '@/features/menu/api'
import type { MenuEngagementSettings, MercadoPagoConnectionStatus } from '@/features/menu/types'

// ─── tiny icon helpers ────────────────────────────────────────────────────────
function CheckIcon() {
    return (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
    )
}

function ExternalLinkIcon() {
    return (
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
    )
}

// ─── MP connection badge ───────────────────────────────────────────────────────
function MPConnectionBadge({ status }: { status: MercadoPagoConnectionStatus | null }) {
    if (!status) return <span className="text-xs text-slate-400">Cargando...</span>
    if (status.connected) {
        return (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-medium text-green-700 border border-green-200">
                <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
                Conectado {status.mp_user_id ? `· ID ${status.mp_user_id}` : ''}
            </span>
        )
    }
    const labels: Record<string, string> = {
        expired: 'Token expirado',
        revoked: 'Acceso revocado',
        error: 'Error de conexión',
    }
    return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700 border border-amber-200">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            {labels[status.status ?? ''] ?? 'No conectado'}
        </span>
    )
}

// ─── main section ─────────────────────────────────────────────────────────────
export function EngagementSettingsSection() {
    const [eng, setEng] = useState<MenuEngagementSettings | null>(null)
    const [mpStatus, setMpStatus] = useState<MercadoPagoConnectionStatus | null>(null)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [uploadingQR, setUploadingQR] = useState(false)
    const [saved, setSaved] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const qrFileRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        Promise.all([
            getMenuEngagementSettings().catch(() => null),
            getMercadoPagoConnectionStatus().catch(() => null),
        ]).then(([engData, mpData]) => {
            if (engData) setEng(engData)
            if (mpData) setMpStatus(mpData)
        }).finally(() => setLoading(false))
    }, [])

    // Read MP connection/error status from URL after OAuth callback
    useEffect(() => {
        if (typeof window === 'undefined') return
        const params = new URLSearchParams(window.location.search)
        if (params.get('mp_connected')) {
            getMercadoPagoConnectionStatus().then(setMpStatus).catch(() => null)
            // Clean URL
            const url = new URL(window.location.href)
            url.searchParams.delete('mp_connected')
            window.history.replaceState({}, '', url.toString())
        }
        if (params.get('mp_error')) {
            setError(`Error al conectar Mercado Pago: ${params.get('mp_error')}`)
            const url = new URL(window.location.href)
            url.searchParams.delete('mp_error')
            window.history.replaceState({}, '', url.toString())
        }
    }, [])

    async function handleSave() {
        if (!eng) return
        setSaving(true)
        setError(null)
        try {
            const updated = await updateMenuEngagementSettings({
                tips_enabled: eng.tips_enabled,
                tips_mode: eng.tips_mode,
                mp_tip_url: eng.mp_tip_url,
                reviews_enabled: eng.reviews_enabled,
                google_place_id: eng.google_place_id,
                google_review_url: eng.google_review_url,
            })
            setEng(updated)
            setSaved(true)
            setTimeout(() => setSaved(false), 2500)
        } catch (e: any) {
            const detail = e?.payload?.detail ?? e?.payload?.mp_tip_url?.[0] ?? e?.payload?.google_place_id?.[0] ?? 'Error al guardar'
            setError(detail)
        } finally {
            setSaving(false)
        }
    }

    async function handleQRUpload(file: File) {
        setUploadingQR(true)
        setError(null)
        try {
            const { url } = await uploadEngagementQRImage(file)
            setEng(prev => prev ? { ...prev, mp_qr_image_url: url } : prev)
        } catch (e: any) {
            setError(e?.payload?.detail ?? 'Error al subir imagen QR')
        } finally {
            setUploadingQR(false)
        }
    }

    async function handleConnectMP() {
        setError(null)
        try {
            const { auth_url } = await startMercadoPagoOAuth()
            window.location.href = auth_url
        } catch (e: any) {
            setError(e?.payload?.detail ?? 'Error al iniciar conexión con Mercado Pago')
        }
    }

    async function handleDisconnectMP() {
        if (!confirm('¿Desconectar Mercado Pago? Las propinas dinámicas dejarán de funcionar.')) return
        setError(null)
        try {
            await disconnectMercadoPago()
            setMpStatus({ connected: false, status: null, mp_user_id: null, updated_at: null })
        } catch {
            setError('Error al desconectar')
        }
    }

    if (loading) return <div className="bg-white p-4 rounded-lg border shadow-sm text-sm text-slate-500">Cargando configuración...</div>
    if (!eng) return null

    return (
        <div className="space-y-6">

            {/* ── Errores ─────────────────────────────────────────────────── */}
            {error && (
                <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                    {error}
                </div>
            )}

            {/* ── Sección Propinas ─────────────────────────────────────────── */}
            <div className="bg-white p-5 rounded-lg border shadow-sm space-y-4">
                <div className="flex items-center justify-between gap-4">
                    <div>
                        <h3 className="font-semibold text-base">Propinas con Mercado Pago</h3>
                        <p className="text-xs text-slate-500 mt-0.5">Mostrá un botón de propina en la carta pública.</p>
                    </div>
                    <Switch
                        checked={eng.tips_enabled}
                        onCheckedChange={(v) => setEng({ ...eng, tips_enabled: v })}
                        aria-label="Habilitar propinas"
                    />
                </div>

                {eng.tips_enabled && (
                    <div className="space-y-4 pt-2 border-t">
                        {/* Mode selector */}
                        <div>
                            <label className="block text-xs font-medium mb-2">Modo de propina</label>
                            <div className="flex flex-col gap-2 sm:flex-row">
                                {[
                                    { value: 'mp_link', label: 'Link de MP', desc: 'Botón que abre tu link de cobro de MP' },
                                    { value: 'mp_qr_image', label: 'QR de MP', desc: 'Modal con imagen QR que escaneado paga' },
                                    { value: 'mp_oauth_checkout', label: 'Propina dinámica (Fase 2)', desc: 'Monto seleccionable + checkout MP conectado' },
                                ].map(({ value, label, desc }) => (
                                    <button
                                        key={value}
                                        type="button"
                                        onClick={() => setEng({ ...eng, tips_mode: value as any })}
                                        className={`flex-1 text-left rounded-lg border px-3 py-2.5 text-xs transition-all ${eng.tips_mode === value
                                                ? 'border-violet-500 bg-violet-50 ring-1 ring-violet-200'
                                                : 'border-slate-200 hover:border-slate-300'
                                            }`}
                                    >
                                        <div className="font-semibold">{label}</div>
                                        <div className="text-slate-500 mt-0.5">{desc}</div>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* MP Link URL */}
                        {(eng.tips_mode === 'mp_link' || eng.tips_mode === 'mp_qr_image') && (
                            <div>
                                <label className="block text-xs font-medium mb-1">
                                    URL de tu link de Mercado Pago
                                    {eng.tips_mode === 'mp_qr_image' && <span className="text-slate-400"> (opcional — para botón "Abrir MP")</span>}
                                    {eng.tips_mode === 'mp_link' && <span className="text-red-500"> *</span>}
                                </label>
                                <input
                                    type="url"
                                    value={eng.mp_tip_url ?? ''}
                                    onChange={(e) => setEng({ ...eng, mp_tip_url: e.target.value || null })}
                                    placeholder="https://mpago.la/tu-link"
                                    className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400"
                                />
                                {eng.mp_tip_url && (
                                    <a
                                        href={eng.mp_tip_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="mt-1 inline-flex items-center gap-1 text-xs text-violet-600 hover:underline"
                                    >
                                        Probar link <ExternalLinkIcon />
                                    </a>
                                )}
                            </div>
                        )}

                        {/* QR Image upload */}
                        {eng.tips_mode === 'mp_qr_image' && (
                            <div>
                                <label className="block text-xs font-medium mb-1">
                                    Imagen QR de Mercado Pago <span className="text-red-500">*</span>
                                </label>
                                {eng.mp_qr_image_url && (
                                    <div className="mb-2 flex items-center gap-3">
                                        <img
                                            src={eng.mp_qr_image_url}
                                            alt="QR actual"
                                            className="h-24 w-24 rounded border object-contain bg-white"
                                        />
                                        <span className="text-xs text-slate-500">QR cargado</span>
                                    </div>
                                )}
                                <input
                                    ref={qrFileRef}
                                    type="file"
                                    accept="image/jpeg,image/png,image/webp"
                                    className="hidden"
                                    onChange={(e) => {
                                        const file = e.target.files?.[0]
                                        if (file) handleQRUpload(file)
                                    }}
                                />
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    onClick={() => qrFileRef.current?.click()}
                                    disabled={uploadingQR}
                                >
                                    {uploadingQR ? 'Subiendo...' : eng.mp_qr_image_url ? 'Cambiar imagen QR' : 'Subir imagen QR'}
                                </Button>
                                <p className="text-xs text-slate-400 mt-1">
                                    Descargá la imagen QR desde la app de Mercado Pago → Mi código QR → Compartir.
                                </p>
                            </div>
                        )}

                        {/* Phase 2: MP OAuth */}
                        {eng.tips_mode === 'mp_oauth_checkout' && (
                            <div className="rounded-lg border bg-slate-50 p-4 space-y-3">
                                <div className="flex items-start justify-between gap-4">
                                    <div>
                                        <p className="text-xs font-semibold mb-1">Conexión con Mercado Pago</p>
                                        <MPConnectionBadge status={mpStatus} />
                                    </div>
                                    <div className="flex gap-2 flex-shrink-0">
                                        {mpStatus?.connected ? (
                                            <Button
                                                type="button"
                                                variant="outline"
                                                size="sm"
                                                onClick={handleDisconnectMP}
                                                className="text-red-600 border-red-200 hover:bg-red-50"
                                            >
                                                Desconectar
                                            </Button>
                                        ) : (
                                            <Button
                                                type="button"
                                                size="sm"
                                                onClick={handleConnectMP}
                                                className="bg-[#009ee3] hover:bg-[#007ab8] text-white"
                                            >
                                                Conectar Mercado Pago
                                            </Button>
                                        )}
                                    </div>
                                </div>
                                {!mpStatus?.connected && (
                                    <p className="text-xs text-slate-500">
                                        Conectá tu cuenta de Mercado Pago para recibir propinas con monto variable directamente. Los clientes eligen el monto y pagan con cualquier método de MP.
                                    </p>
                                )}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* ── Sección Reseñas Google ────────────────────────────────────── */}
            <div className="bg-white p-5 rounded-lg border shadow-sm space-y-4">
                <div className="flex items-center justify-between gap-4">
                    <div>
                        <h3 className="font-semibold text-base">Reseñas en Google</h3>
                        <p className="text-xs text-slate-500 mt-0.5">Mostrá un botón para que tus clientes dejen una reseña.</p>
                    </div>
                    <Switch
                        checked={eng.reviews_enabled}
                        onCheckedChange={(v) => setEng({ ...eng, reviews_enabled: v })}
                        aria-label="Habilitar reseñas"
                    />
                </div>

                {eng.reviews_enabled && (
                    <div className="space-y-4 pt-2 border-t">
                        <div>
                            <label className="block text-xs font-medium mb-1">
                                Google Place ID <span className="text-slate-400">(recomendado)</span>
                            </label>
                            <input
                                type="text"
                                value={eng.google_place_id ?? ''}
                                onChange={(e) => setEng({ ...eng, google_place_id: e.target.value || null })}
                                placeholder="ChIJN1t_tDeuEmsRUsoyG83frY4"
                                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400 font-mono"
                            />
                            <p className="text-xs text-slate-400 mt-1">
                                Encontralo en Google Maps → Compartir → Copia la URL y buscá el <code>place_id</code> o usá{' '}
                                <a href="https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder" target="_blank" rel="noopener noreferrer" className="text-violet-600 hover:underline">Place ID Finder</a>.
                            </p>
                            {eng.google_place_id && (
                                <a
                                    href={`https://search.google.com/local/writereview?placeid=${eng.google_place_id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="mt-1.5 inline-flex items-center gap-1 text-xs text-violet-600 hover:underline"
                                >
                                    Probar link reseña <ExternalLinkIcon />
                                </a>
                            )}
                        </div>

                        <div>
                            <label className="block text-xs font-medium mb-1">
                                URL directa de reseña <span className="text-slate-400">(alternativa si no tenés Place ID)</span>
                            </label>
                            <input
                                type="url"
                                value={eng.google_review_url ?? ''}
                                onChange={(e) => setEng({ ...eng, google_review_url: e.target.value || null })}
                                placeholder="https://g.page/r/tu-negocio/review"
                                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400"
                            />
                            {eng.google_review_url && (
                                <a
                                    href={eng.google_review_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="mt-1 inline-flex items-center gap-1 text-xs text-violet-600 hover:underline"
                                >
                                    Probar URL <ExternalLinkIcon />
                                </a>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* ── Save button ───────────────────────────────────────────────── */}
            <div className="flex items-center justify-end gap-3">
                {saved && (
                    <span className="flex items-center gap-1.5 text-sm text-green-600">
                        <CheckIcon /> Guardado
                    </span>
                )}
                <Button onClick={handleSave} disabled={saving}>
                    {saving ? 'Guardando...' : 'Guardar Configuración'}
                </Button>
            </div>
        </div>
    )
}

'use client';

import { useEffect, useState } from 'react';

import { fetchBusinessBranding, updateBusinessBranding } from '@/features/gestion/api';
import { ApiError } from '@/lib/api/client';

/**
 * WhatsApp público del negocio (Slice 6D). Se guarda en el branding del
 * Business y el backend lo normaliza; los clientes lo ven solo como botón
 * "Abrir WhatsApp" en la página de su reserva. No se envía nada automático.
 */
export function WhatsappContactCard() {
    const [value, setValue] = useState('');
    const [saved, setSaved] = useState('');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');

    useEffect(() => {
        let active = true;
        fetchBusinessBranding()
            .then((branding) => {
                if (!active) return;
                setValue(branding.whatsapp_phone ?? '');
                setSaved(branding.whatsapp_phone ?? '');
            })
            .catch(() => {
                if (active) setError('No pudimos cargar el WhatsApp del negocio.');
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => {
            active = false;
        };
    }, []);

    async function handleSubmit(event: React.FormEvent) {
        event.preventDefault();
        setSaving(true);
        setError('');
        setNotice('');
        try {
            const branding = await updateBusinessBranding({ whatsapp_phone: value.trim() });
            setValue(branding.whatsapp_phone ?? '');
            setSaved(branding.whatsapp_phone ?? '');
            setNotice(branding.whatsapp_phone ? 'WhatsApp guardado.' : 'WhatsApp eliminado.');
        } catch (err) {
            const payload = err instanceof ApiError ? (err.payload as { whatsapp_phone?: string[] } | undefined) : undefined;
            setError(payload?.whatsapp_phone?.[0] ?? 'No pudimos guardar el WhatsApp.');
        } finally {
            setSaving(false);
        }
    }

    return (
        <form onSubmit={handleSubmit} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div>
                <h2 className="text-sm font-semibold text-slate-800">WhatsApp de contacto</h2>
                <p className="text-xs text-slate-500">
                    Tus clientes podrán abrir WhatsApp con un mensaje prearmado desde la página de su reserva.
                    Dejalo vacío para no mostrar el botón.
                </p>
            </div>
            <label className="block text-sm text-slate-600">
                Número
                <input
                    type="tel"
                    inputMode="tel"
                    value={value}
                    disabled={loading || saving}
                    onChange={(event) => setValue(event.target.value)}
                    placeholder="+54 9 11 1234-5678"
                    maxLength={32}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                />
            </label>
            {error && <p role="alert" className="text-sm text-rose-600">{error}</p>}
            {notice && <p className="text-sm text-slate-500">{notice}</p>}
            <button
                type="submit"
                disabled={loading || saving || value.trim() === saved}
                className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
                {saving ? 'Guardando…' : 'Guardar'}
            </button>
        </form>
    );
}

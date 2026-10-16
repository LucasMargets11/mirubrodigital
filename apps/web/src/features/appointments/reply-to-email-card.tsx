'use client';

import { useState } from 'react';

import { ApiError } from '@/lib/api/client';

import { useCustomerCommunicationSettings, useUpdateCustomerCommunicationSettings } from './hooks';

// Mismo criterio práctico que el backend (EmailField): algo@dominio.tld, sin espacios.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateReplyToEmail(raw: string): string | null {
    const value = raw.trim();
    if (!value) return null; // vacío = sin Reply-To
    return EMAIL_PATTERN.test(value) ? null : 'Ingresá un email válido (por ejemplo, hola@tunegocio.com).';
}

function apiErrorMessage(error: unknown) {
    if (error instanceof ApiError && error.status === 403) return 'Tu rol no puede cambiar esta configuración.';
    if (error instanceof ApiError && error.payload && typeof error.payload === 'object') {
        const first = Object.values(error.payload as Record<string, unknown>).find((v) => Array.isArray(v) && v.length > 0);
        if (Array.isArray(first) && typeof first[0] === 'string') return first[0];
    }
    return 'No pudimos guardar la configuración. Intentá nuevamente.';
}

/**
 * "Email para respuestas" (CUSTOMER 07D.3A.1): Reply-To de los emails que
 * MiRubro envía a los clientes en nombre del negocio. El remitente (From) no
 * se configura acá. Vacío = sin Reply-To.
 *
 * Lectura: `manage_settings` (owner/admin/manager). Edición:
 * `manage_reminder_automations` (owner/admin); el backend lo vuelve a exigir.
 */
export function ReplyToEmailCard({ canManage }: { canManage: boolean }) {
    const query = useCustomerCommunicationSettings();
    const mutation = useUpdateCustomerCommunicationSettings();
    const [edit, setEdit] = useState<string | null>(null);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const server = query.data?.reply_to_email ?? null;
    const value = edit ?? server ?? '';
    const validation = validateReplyToEmail(value);
    const dirty = server !== null && value.trim() !== server;

    const handleSave = async () => {
        if (validation) return;
        setError(null);
        try {
            await mutation.mutateAsync({ reply_to_email: value.trim() });
            setEdit(null);
            setSaved(true);
        } catch (err) {
            setError(apiErrorMessage(err));
        }
    };

    return (
        <section aria-labelledby="reply-to-email-title" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div>
                <h2 id="reply-to-email-title" className="text-sm font-semibold text-slate-800">
                    Email para respuestas
                </h2>
                <p className="text-xs text-slate-500">
                    Cuando un cliente responda a un correo enviado por MiRubro, la respuesta llegará a esta dirección.
                </p>
            </div>

            {query.isLoading ? (
                <p className="text-sm text-slate-500">Cargando configuración...</p>
            ) : query.isError || server === null ? (
                <p role="alert" className="text-sm text-rose-600">
                    No pudimos cargar la configuración.
                </p>
            ) : (
                <>
                    {!canManage ? (
                        <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                            Solo el dueño o un administrador pueden cambiar esta configuración.
                        </p>
                    ) : null}
                    <div>
                        <label htmlFor="reply-to-email" className="block text-sm text-slate-700">
                            Email
                        </label>
                        <input
                            id="reply-to-email"
                            type="email"
                            inputMode="email"
                            autoComplete="email"
                            placeholder="hola@tunegocio.com"
                            value={value}
                            disabled={!canManage || mutation.isPending}
                            aria-invalid={Boolean(validation)}
                            aria-describedby={validation ? 'reply-to-email-error' : 'reply-to-email-help'}
                            onChange={(event) => {
                                setSaved(false);
                                setError(null);
                                setEdit(event.target.value);
                            }}
                            className="mt-1 min-h-11 w-full max-w-md rounded-lg border border-slate-200 px-3 text-sm text-slate-900 focus:border-slate-900 focus:outline-none disabled:bg-slate-50 disabled:text-slate-500 sm:min-h-0 sm:py-1.5"
                        />
                        {validation ? (
                            <p id="reply-to-email-error" role="alert" className="mt-1 text-xs text-rose-600">
                                {validation}
                            </p>
                        ) : (
                            <p id="reply-to-email-help" className="mt-1 text-xs text-slate-400">
                                Si lo dejás vacío, los correos salen sin dirección de respuesta.
                            </p>
                        )}
                    </div>

                    {canManage ? (
                        <div className="flex flex-wrap items-center gap-3">
                            <button
                                type="button"
                                onClick={handleSave}
                                disabled={!dirty || Boolean(validation) || mutation.isPending}
                                className="min-h-11 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 sm:min-h-0 sm:py-1.5"
                            >
                                {mutation.isPending ? 'Guardando...' : 'Guardar'}
                            </button>
                            {saved && !dirty ? (
                                <span role="status" className="text-xs text-emerald-600">
                                    Configuración guardada.
                                </span>
                            ) : null}
                            {error ? (
                                <span role="alert" className="text-xs text-rose-600">
                                    {error}
                                </span>
                            ) : null}
                        </div>
                    ) : null}
                </>
            )}
        </section>
    );
}

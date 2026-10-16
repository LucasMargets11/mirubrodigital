'use client';

import { useState } from 'react';

import { ApiError } from '@/lib/api/client';

import { useCommunicationAutomationSettings, useUpdateCommunicationAutomationSettings } from './hooks';
import type { CommunicationAutomationSettings } from './types';

type Draft = Pick<CommunicationAutomationSettings, 'appointment_email_enabled' | 'no_show_email_enabled'>;

function toDraft(settings: CommunicationAutomationSettings): Draft {
    return {
        appointment_email_enabled: settings.appointment_email_enabled,
        no_show_email_enabled: settings.no_show_email_enabled,
    };
}

function apiErrorMessage(error: unknown) {
    if (error instanceof ApiError && error.status === 403) return 'Tu rol no puede cambiar esta configuración.';
    return 'No pudimos guardar la configuración. Intentá nuevamente.';
}

/**
 * "Comunicaciones automáticas" (CUSTOMER 07D.4A): cuando vence un recordatorio
 * automático de Turnos, MiRubro prepara un email al cliente (si tiene Email
 * permitido y consentimiento vigente). Apagado por defecto. Depende de que el
 * recordatorio interno automático exista (tarjeta "Recordatorios automáticos").
 *
 * El modo (simulación / real) lo informa el backend según su proveedor
 * configurado; nunca se asume real porque exista el código.
 *
 * Lectura: `manage_settings` (owner/admin/manager). Edición:
 * `manage_reminder_automations` (owner/admin); el backend lo vuelve a exigir.
 */
export function CommunicationAutomationCard({ canManage }: { canManage: boolean }) {
    const query = useCommunicationAutomationSettings();
    const mutation = useUpdateCommunicationAutomationSettings();
    const [edits, setEdits] = useState<Draft | null>(null);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const server = query.data ? toDraft(query.data) : null;
    const draft = edits ?? server;
    const dirty = Boolean(server && draft && JSON.stringify(server) !== JSON.stringify(draft));
    const disabled = !canManage || mutation.isPending;
    const simulation = query.data?.email_delivery_mode !== 'live';

    const update = (patch: Partial<Draft>) => {
        setSaved(false);
        setError(null);
        if (draft) setEdits({ ...draft, ...patch });
    };

    const handleSave = async () => {
        if (!draft) return;
        setError(null);
        try {
            await mutation.mutateAsync(draft);
            setEdits(null);
            setSaved(true);
        } catch (err) {
            setError(apiErrorMessage(err));
        }
    };

    return (
        <section aria-labelledby="communication-automation-title" className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                    <h2 id="communication-automation-title" className="text-sm font-semibold text-slate-800">
                        Comunicaciones automáticas
                    </h2>
                    <p className="text-xs text-slate-500">Mensajes que MiRubro prepara para tus clientes a partir de los recordatorios automáticos.</p>
                </div>
                {query.data && simulation ? (
                    <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">Modo simulación</span>
                ) : null}
            </div>

            {query.isLoading || (!draft && !query.isError) ? (
                <p className="text-sm text-slate-500">Cargando configuración...</p>
            ) : query.isError || !draft ? (
                <p role="alert" className="text-sm text-rose-600">
                    No pudimos cargar la configuración.
                </p>
            ) : (
                <>
                    <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                        Los canales externos todavía dependen de la configuración del proveedor.
                        {simulation ? ' Por ahora los envíos se simulan: no le llega nada al cliente.' : null}
                    </p>
                    {!canManage ? (
                        <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                            Solo el dueño o un administrador pueden cambiar esta configuración.
                        </p>
                    ) : null}

                    <fieldset className="space-y-2 rounded-xl border border-slate-100 p-3">
                        <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Recordatorios de turnos</legend>
                        <label className="flex min-h-11 items-start gap-3 text-sm text-slate-700">
                            <input
                                type="checkbox"
                                className="mt-0.5 h-5 w-5 shrink-0 accent-slate-900"
                                checked={draft.appointment_email_enabled}
                                disabled={disabled}
                                onChange={(event) => update({ appointment_email_enabled: event.target.checked })}
                            />
                            <span>Enviar email automáticamente</span>
                        </label>
                        <p className="text-xs text-slate-400">
                            Cuando llegue la hora del recordatorio, MiRubro preparará un email si el cliente tiene Email permitido y consentimiento
                            vigente. Requiere el recordatorio automático antes del turno activo.
                        </p>
                    </fieldset>

                    <fieldset className="space-y-2 rounded-xl border border-slate-100 p-3">
                        <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Inasistencias</legend>
                        <label className="flex min-h-11 items-start gap-3 text-sm text-slate-700">
                            <input
                                type="checkbox"
                                className="mt-0.5 h-5 w-5 shrink-0 accent-slate-900"
                                checked={draft.no_show_email_enabled}
                                disabled={disabled}
                                onChange={(event) => update({ no_show_email_enabled: event.target.checked })}
                            />
                            <span>Enviar seguimiento por email</span>
                        </label>
                        <p className="text-xs text-slate-400">Requiere el seguimiento automático después de un no-show activo.</p>
                    </fieldset>

                    {canManage ? (
                        <div className="flex flex-wrap items-center gap-3">
                            <button
                                type="button"
                                onClick={handleSave}
                                disabled={!dirty || mutation.isPending}
                                className="min-h-11 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 sm:min-h-0 sm:py-1.5"
                            >
                                {mutation.isPending ? 'Guardando...' : 'Guardar cambios'}
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

'use client';

import { useState } from 'react';

import { ApiError } from '@/lib/api/client';

import { useReminderAutomationSettings, useUpdateReminderAutomationSettings } from './hooks';
import { REMINDER_AUTOMATION_LIMITS, type ReminderAutomationSettings } from './types';

type Draft = {
    appointment_reminder_enabled: boolean;
    appointment_reminder_hours_before: string;
    no_show_followup_enabled: boolean;
    no_show_followup_delay_hours: string;
};

type HoursField = 'appointment_reminder_hours_before' | 'no_show_followup_delay_hours';

function toDraft(settings: ReminderAutomationSettings): Draft {
    return {
        appointment_reminder_enabled: settings.appointment_reminder_enabled,
        appointment_reminder_hours_before: String(settings.appointment_reminder_hours_before),
        no_show_followup_enabled: settings.no_show_followup_enabled,
        no_show_followup_delay_hours: String(settings.no_show_followup_delay_hours),
    };
}

/** Entero dentro de los límites del backend; si no, el mensaje de error. */
export function validateHours(field: HoursField, raw: string): string | null {
    const { min, max } = REMINDER_AUTOMATION_LIMITS[field];
    if (!/^\d+$/.test(raw.trim())) return `Ingresá un número entero de horas (${min} a ${max}).`;
    const value = Number(raw);
    if (value < min || value > max) return `Debe estar entre ${min} y ${max} horas.`;
    return null;
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
 * Recordatorios automáticos de Turnos (CUSTOMER 07B). Solo crean
 * recordatorios INTERNOS en la ficha del cliente; MiRubro no le envía nada.
 *
 * Lectura: `manage_settings` (owner/admin/manager). Edición:
 * `manage_reminder_automations` (owner/admin); el backend lo vuelve a exigir.
 */
export function ReminderAutomationCard({ canManage }: { canManage: boolean }) {
    const query = useReminderAutomationSettings();
    const mutation = useUpdateReminderAutomationSettings();
    // `edits` = cambios sin guardar; sin edits el formulario refleja el servidor.
    const [edits, setEdits] = useState<Draft | null>(null);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const server = query.data ? toDraft(query.data) : null;
    const draft = edits ?? server;

    const hoursError = draft ? validateHours('appointment_reminder_hours_before', draft.appointment_reminder_hours_before) : null;
    const delayError = draft ? validateHours('no_show_followup_delay_hours', draft.no_show_followup_delay_hours) : null;
    const dirty = Boolean(server && draft && JSON.stringify(server) !== JSON.stringify(draft));
    const disabled = !canManage || mutation.isPending;

    const update = (patch: Partial<Draft>) => {
        setSaved(false);
        setError(null);
        if (draft) setEdits({ ...draft, ...patch });
    };

    const handleSave = async () => {
        if (!draft || hoursError || delayError) return;
        setError(null);
        try {
            await mutation.mutateAsync({
                appointment_reminder_enabled: draft.appointment_reminder_enabled,
                appointment_reminder_hours_before: Number(draft.appointment_reminder_hours_before),
                no_show_followup_enabled: draft.no_show_followup_enabled,
                no_show_followup_delay_hours: Number(draft.no_show_followup_delay_hours),
            });
            setEdits(null);
            setSaved(true);
        } catch (err) {
            setError(apiErrorMessage(err));
        }
    };

    return (
        <section aria-labelledby="reminder-automation-title" className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div>
                <h2 id="reminder-automation-title" className="text-sm font-semibold text-slate-800">
                    Recordatorios automáticos
                </h2>
                <p className="text-xs text-slate-500">
                    Estos recordatorios son internos. MiRubro no enviará mensajes al cliente: aparecen en la ficha del cliente para tu equipo.
                </p>
            </div>

            {query.isLoading || (!draft && !query.isError) ? (
                <p className="text-sm text-slate-500">Cargando configuración...</p>
            ) : query.isError || !draft ? (
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

                    <fieldset className="space-y-2 rounded-xl border border-slate-100 p-3">
                        <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Antes del turno</legend>
                        <label className="flex min-h-11 items-start gap-3 text-sm text-slate-700">
                            <input
                                type="checkbox"
                                className="mt-0.5 h-5 w-5 shrink-0 accent-slate-900"
                                checked={draft.appointment_reminder_enabled}
                                disabled={disabled}
                                onChange={(event) => update({ appointment_reminder_enabled: event.target.checked })}
                            />
                            <span>Crear recordatorio interno antes de cada turno confirmado</span>
                        </label>
                        <HoursInput
                            id="reminder-automation-hours-before"
                            label="Anticipación"
                            suffix="horas antes"
                            value={draft.appointment_reminder_hours_before}
                            limits={REMINDER_AUTOMATION_LIMITS.appointment_reminder_hours_before}
                            error={hoursError}
                            disabled={disabled}
                            onChange={(value) => update({ appointment_reminder_hours_before: value })}
                        />
                        <p className="text-xs text-slate-400">
                            Si el turno se reserva con menos anticipación, no se crea el recordatorio. Los turnos con seña lo reciben al confirmarse el pago.
                        </p>
                    </fieldset>

                    <fieldset className="space-y-2 rounded-xl border border-slate-100 p-3">
                        <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Inasistencias</legend>
                        <label className="flex min-h-11 items-start gap-3 text-sm text-slate-700">
                            <input
                                type="checkbox"
                                className="mt-0.5 h-5 w-5 shrink-0 accent-slate-900"
                                checked={draft.no_show_followup_enabled}
                                disabled={disabled}
                                onChange={(event) => update({ no_show_followup_enabled: event.target.checked })}
                            />
                            <span>Crear seguimiento después de un no-show</span>
                        </label>
                        <HoursInput
                            id="reminder-automation-no-show-delay"
                            label="Después de"
                            suffix="horas"
                            value={draft.no_show_followup_delay_hours}
                            limits={REMINDER_AUTOMATION_LIMITS.no_show_followup_delay_hours}
                            error={delayError}
                            disabled={disabled}
                            onChange={(value) => update({ no_show_followup_delay_hours: value })}
                        />
                    </fieldset>

                    {canManage ? (
                        <div className="flex flex-wrap items-center gap-3">
                            <button
                                type="button"
                                onClick={handleSave}
                                disabled={!dirty || Boolean(hoursError || delayError) || mutation.isPending}
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

function HoursInput({
    id,
    label,
    suffix,
    value,
    limits,
    error,
    disabled,
    onChange,
}: {
    id: string;
    label: string;
    suffix: string;
    value: string;
    limits: { min: number; max: number };
    error: string | null;
    disabled: boolean;
    onChange: (value: string) => void;
}) {
    return (
        <div>
            <div className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
                <label htmlFor={id}>{label}</label>
                <input
                    id={id}
                    type="number"
                    inputMode="numeric"
                    min={limits.min}
                    max={limits.max}
                    step={1}
                    value={value}
                    disabled={disabled}
                    aria-invalid={Boolean(error)}
                    aria-describedby={error ? `${id}-error` : undefined}
                    onChange={(event) => onChange(event.target.value)}
                    className="min-h-11 w-24 rounded-lg border border-slate-200 px-3 text-sm text-slate-900 focus:border-slate-900 focus:outline-none disabled:bg-slate-50 disabled:text-slate-500 sm:min-h-0 sm:py-1.5"
                />
                <span className="text-slate-500">{suffix}</span>
            </div>
            {error ? (
                <p id={`${id}-error`} role="alert" className="mt-1 text-xs text-rose-600">
                    {error}
                </p>
            ) : null}
        </div>
    );
}

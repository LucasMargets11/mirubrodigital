"use client";

import { useId } from 'react';

import { useLeadAssignees } from '@/features/leads/hooks';
import type { LeadUserRef } from '@/features/leads/types';

const OUTLINE_BUTTON =
    'rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50';
const DANGER_LINK = 'text-xs font-semibold text-rose-600 hover:text-rose-800 disabled:cursor-not-allowed disabled:opacity-50';

/**
 * Selector de asignación (LEADS 05B.1). Solo ofrece las personas que devuelve
 * `GET /leads/assignees/` (misma regla que valida el PATCH). Carga y error son
 * locales: el resto del detalle no espera esta lista. "Quitar asignación" no
 * depende de la lista, así que sigue disponible aunque falle.
 */
export function LeadAssigneeSelect({
    assignedTo,
    currentUserId,
    pending,
    onAssign,
}: {
    assignedTo: LeadUserRef | null;
    currentUserId: number | null;
    pending: boolean;
    /** Devuelve `false` si el PATCH falló (el error lo muestra la tarjeta). */
    onAssign: (userId: number | null) => Promise<boolean>;
}) {
    const selectId = useId();
    const assignees = useLeadAssignees();
    const options = assignees.data ?? [];
    const listed = (id: number | null | undefined) => id != null && options.some((person) => person.id === id);
    const assignedToMe = currentUserId != null && assignedTo?.id === currentUserId;
    const currentListed = listed(assignedTo?.id);

    const assign = async (userId: number | null) => {
        const ok = await onAssign(userId);
        // Un 400 suele ser alguien que perdió acceso entre la carga y el guardado.
        if (!ok && userId != null) void assignees.refetch();
    };

    return (
        <div className="space-y-2 pt-1">
            {assignees.isLoading ? (
                <p role="status" className="text-xs text-slate-500">Cargando personas asignables…</p>
            ) : assignees.isError ? (
                <div role="alert" className="flex flex-wrap items-center gap-2 text-xs text-rose-700">
                    <span>No pudimos cargar las personas asignables.</span>
                    <button type="button" onClick={() => void assignees.refetch()} className="font-semibold underline">
                        Reintentar
                    </button>
                </div>
            ) : options.length === 0 ? (
                <p className="text-xs text-slate-500">No hay personas con acceso a Leads para asignar.</p>
            ) : (
                <div className="space-y-1">
                    <label htmlFor={selectId} className="text-xs text-slate-500">
                        {assignedTo ? 'Reasignar a' : 'Asignar a'}
                    </label>
                    <select
                        id={selectId}
                        value={currentListed && assignedTo ? String(assignedTo.id) : ''}
                        disabled={pending}
                        onChange={(event) => {
                            const value = Number(event.target.value);
                            if (Number.isInteger(value) && value > 0 && value !== assignedTo?.id) void assign(value);
                        }}
                        className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {!currentListed ? <option value="" disabled>Elegí una persona…</option> : null}
                        {options.map((person) => (
                            <option key={person.id} value={String(person.id)}>
                                {person.display_name}
                                {person.id === currentUserId ? ' (vos)' : ''}
                            </option>
                        ))}
                    </select>
                    {assignedTo && !currentListed ? (
                        <p className="text-xs text-amber-700">
                            {assignedTo.display_name} ya no figura entre las personas asignables. Podés reasignar o quitar la asignación.
                        </p>
                    ) : null}
                </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
                {listed(currentUserId) && !assignedToMe ? (
                    <button type="button" disabled={pending} onClick={() => void assign(currentUserId)} className={OUTLINE_BUTTON}>
                        {assignedTo ? 'Tomar el lead' : 'Asignarme'}
                    </button>
                ) : null}
                {assignedTo ? (
                    <button type="button" disabled={pending} onClick={() => void assign(null)} className={DANGER_LINK}>
                        Quitar asignación
                    </button>
                ) : null}
            </div>
        </div>
    );
}

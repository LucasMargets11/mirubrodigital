"use client";

import { useMemo, useState } from 'react';
import { z } from 'zod';

import { Modal } from '@/components/ui/modal';
import {
    useAppointmentSchedules,
    useCreateAppointmentSchedule,
    useDeleteAppointmentSchedule,
    useUpdateAppointmentSchedule,
} from '@/features/appointments/hooks';
import type { AppointmentSchedule, Weekday } from '@/features/appointments/types';
import { WEEKDAYS } from '@/features/appointments/types';
import { ApiError } from '@/lib/api/client';

const blockFormSchema = z.object({
    weekday: z.coerce.number().int().min(0).max(6),
    start_time: z.string().min(1, 'Ingresá la hora de inicio'),
    end_time: z.string().min(1, 'Ingresá la hora de fin'),
});

type FormState = z.infer<typeof blockFormSchema>;

const emptyForm: FormState = { weekday: 0, start_time: '09:00', end_time: '13:00' };

function formatTime(value: string) {
    return value.slice(0, 5);
}

type ScheduleWeekEditorProps = {
    professionalId: string | null;
    canManage: boolean;
};

export function ScheduleWeekEditor({ professionalId, canManage }: ScheduleWeekEditorProps) {
    const schedulesQuery = useAppointmentSchedules(professionalId);
    const createMutation = useCreateAppointmentSchedule();
    const updateMutation = useUpdateAppointmentSchedule();
    const deleteMutation = useDeleteAppointmentSchedule();

    const [modalOpen, setModalOpen] = useState(false);
    const [editing, setEditing] = useState<AppointmentSchedule | null>(null);
    const [form, setForm] = useState<FormState>(emptyForm);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [feedback, setFeedback] = useState('');
    const [deletingId, setDeletingId] = useState<string | null>(null);

    const isSaving = createMutation.isPending || updateMutation.isPending;
    const schedules = useMemo(() => schedulesQuery.data ?? [], [schedulesQuery.data]);

    const blocksByWeekday = useMemo(() => {
        const map = new Map<Weekday, AppointmentSchedule[]>();
        WEEKDAYS.forEach(({ value }) => map.set(value, []));
        for (const block of schedules) {
            map.get(block.weekday)?.push(block);
        }
        for (const list of map.values()) {
            list.sort((a, b) => a.start_time.localeCompare(b.start_time));
        }
        return map;
    }, [schedules]);

    const handleOpenCreate = (weekday: Weekday) => {
        setEditing(null);
        setForm({ ...emptyForm, weekday });
        setErrors({});
        setFeedback('');
        setModalOpen(true);
    };

    const handleOpenEdit = (block: AppointmentSchedule) => {
        setEditing(block);
        setForm({
            weekday: block.weekday,
            start_time: formatTime(block.start_time),
            end_time: formatTime(block.end_time),
        });
        setErrors({});
        setFeedback('');
        setModalOpen(true);
    };

    const handleClose = () => setModalOpen(false);

    async function handleSubmit() {
        const parsed = blockFormSchema.safeParse(form);
        if (!parsed.success) {
            const fieldErrors: Record<string, string> = {};
            parsed.error.errors.forEach((err) => {
                if (err.path[0]) fieldErrors[err.path[0] as string] = err.message;
            });
            setErrors(fieldErrors);
            return;
        }
        setErrors({});

        const payload = {
            professional_id: professionalId,
            weekday: parsed.data.weekday as Weekday,
            start_time: parsed.data.start_time,
            end_time: parsed.data.end_time,
        };

        try {
            if (editing) {
                await updateMutation.mutateAsync({ id: editing.id, payload });
                setFeedback('Bloque actualizado.');
            } else {
                await createMutation.mutateAsync(payload);
                setFeedback('Bloque creado.');
            }
            setModalOpen(false);
        } catch (error) {
            if (error instanceof ApiError && error.status === 400 && error.payload && typeof error.payload === 'object') {
                const data = error.payload as Record<string, unknown>;
                const fieldErrors: Record<string, string> = {};
                for (const [field, value] of Object.entries(data)) {
                    if (Array.isArray(value) && value.length > 0) {
                        fieldErrors[field === 'non_field_errors' ? 'end_time' : field] = String(value[0]);
                    } else if (typeof value === 'string') {
                        fieldErrors.end_time = value;
                    }
                }
                setErrors(Object.keys(fieldErrors).length > 0 ? fieldErrors : {});
                if (Object.keys(fieldErrors).length === 0) {
                    setFeedback('No pudimos guardar el bloque.');
                }
            } else {
                setFeedback('No pudimos guardar el bloque.');
            }
        }
    }

    async function handleDelete(id: string) {
        setDeletingId(id);
        try {
            await deleteMutation.mutateAsync(id);
            setFeedback('Bloque eliminado.');
        } catch {
            setFeedback('No pudimos eliminar el bloque.');
        } finally {
            setDeletingId(null);
        }
    }

    if (schedulesQuery.isLoading) {
        return <div className="py-8 text-center text-sm text-slate-500">Cargando horarios...</div>;
    }

    return (
        <div className="space-y-3">
            {feedback && <p className="text-sm text-slate-500">{feedback}</p>}
            {schedulesQuery.isError && <p className="text-sm text-rose-600">No pudimos cargar los horarios.</p>}

            <div className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
                {WEEKDAYS.map(({ value, label }) => {
                    const blocks = blocksByWeekday.get(value) ?? [];
                    return (
                        <div key={value} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-start sm:justify-between">
                            <p className="w-28 shrink-0 text-sm font-medium text-slate-700">{label}</p>
                            <div className="flex flex-1 flex-wrap items-center gap-2">
                                {blocks.length === 0 && <span className="text-sm text-slate-400">Sin horario</span>}
                                {blocks.map((block) => (
                                    <span
                                        key={block.id}
                                        className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-800"
                                    >
                                        {formatTime(block.start_time)} - {formatTime(block.end_time)}
                                        {canManage && (
                                            <span className="flex items-center gap-1">
                                                <button
                                                    type="button"
                                                    onClick={() => handleOpenEdit(block)}
                                                    className="text-slate-500 hover:text-slate-900"
                                                    aria-label={`Editar bloque ${label} ${formatTime(block.start_time)}-${formatTime(block.end_time)}`}
                                                >
                                                    ✎
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => handleDelete(block.id)}
                                                    disabled={deletingId === block.id}
                                                    className="text-slate-500 hover:text-rose-600 disabled:opacity-50"
                                                    aria-label={`Eliminar bloque ${label} ${formatTime(block.start_time)}-${formatTime(block.end_time)}`}
                                                >
                                                    ✕
                                                </button>
                                            </span>
                                        )}
                                    </span>
                                ))}
                                {canManage && (
                                    <button
                                        type="button"
                                        onClick={() => handleOpenCreate(value)}
                                        className="rounded-full border border-dashed border-slate-300 px-3 py-1 text-xs font-semibold text-slate-500 hover:border-slate-900 hover:text-slate-900"
                                    >
                                        + Agregar bloque
                                    </button>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            <Modal open={modalOpen} onClose={handleClose} title={editing ? 'Editar bloque' : 'Nuevo bloque'}>
                <fieldset disabled={isSaving} className="space-y-4">
                    <legend className="sr-only">{editing ? 'Formulario para editar bloque' : 'Formulario para crear bloque'}</legend>
                    <label className="block text-sm font-medium text-slate-700">
                        Día
                        <select
                            value={form.weekday}
                            onChange={(event) => setForm((prev) => ({ ...prev, weekday: Number(event.target.value) as Weekday }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                        >
                            {WEEKDAYS.map(({ value, label }) => (
                                <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                    </label>

                    <div className="grid gap-4 md:grid-cols-2">
                        <label className="text-sm font-medium text-slate-700">
                            Desde
                            <input
                                type="time"
                                value={form.start_time}
                                onChange={(event) => setForm((prev) => ({ ...prev, start_time: event.target.value }))}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                            />
                            {errors.start_time && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.start_time}</span>}
                        </label>
                        <label className="text-sm font-medium text-slate-700">
                            Hasta
                            <input
                                type="time"
                                value={form.end_time}
                                onChange={(event) => setForm((prev) => ({ ...prev, end_time: event.target.value }))}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                            />
                            {errors.end_time && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.end_time}</span>}
                        </label>
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={handleClose}
                            className="rounded-full border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 disabled:opacity-50"
                            disabled={isSaving}
                        >
                            Cancelar
                        </button>
                        <button
                            type="button"
                            onClick={handleSubmit}
                            disabled={isSaving}
                            className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                            aria-busy={isSaving}
                        >
                            {isSaving ? 'Guardando...' : 'Guardar'}
                        </button>
                    </div>
                </fieldset>
            </Modal>
        </div>
    );
}

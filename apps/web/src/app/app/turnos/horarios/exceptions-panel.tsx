"use client";

import { useMemo, useState } from 'react';
import { z } from 'zod';

import { Modal } from '@/components/ui/modal';
import {
    useAppointmentExceptions,
    useCreateAppointmentException,
    useDeleteAppointmentException,
    useUpdateAppointmentException,
} from '@/features/appointments/hooks';
import type { AppointmentException } from '@/features/appointments/types';
import { ApiError } from '@/lib/api/client';

const exceptionFormSchema = z.object({
    date: z.string().min(1, 'Ingresá una fecha'),
    is_closed: z.boolean(),
    start_time: z.string().optional(),
    end_time: z.string().optional(),
    note: z.string().max(255, 'La nota es muy larga').optional(),
});

type FormState = z.infer<typeof exceptionFormSchema>;

const emptyForm: FormState = { date: '', is_closed: true, start_time: '', end_time: '', note: '' };

function formatDate(value: string) {
    const [year, month, day] = value.split('-');
    if (!year || !month || !day) return value;
    return `${day}/${month}/${year}`;
}

function formatTime(value: string | null) {
    return value ? value.slice(0, 5) : '';
}

type ExceptionsPanelProps = {
    professionalId: string | null;
    canManage: boolean;
};

export function ExceptionsPanel({ professionalId, canManage }: ExceptionsPanelProps) {
    const exceptionsQuery = useAppointmentExceptions(professionalId);
    const createMutation = useCreateAppointmentException();
    const updateMutation = useUpdateAppointmentException();
    const deleteMutation = useDeleteAppointmentException();

    const [modalOpen, setModalOpen] = useState(false);
    const [editing, setEditing] = useState<AppointmentException | null>(null);
    const [form, setForm] = useState<FormState>(emptyForm);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [feedback, setFeedback] = useState('');
    const [deletingId, setDeletingId] = useState<string | null>(null);

    const isSaving = createMutation.isPending || updateMutation.isPending;
    const exceptions = useMemo(
        () => [...(exceptionsQuery.data ?? [])].sort((a, b) => b.date.localeCompare(a.date)),
        [exceptionsQuery.data],
    );

    const handleOpenCreate = () => {
        setEditing(null);
        setForm({ ...emptyForm });
        setErrors({});
        setFeedback('');
        setModalOpen(true);
    };

    const handleOpenEdit = (exception: AppointmentException) => {
        setEditing(exception);
        setForm({
            date: exception.date,
            is_closed: exception.is_closed,
            start_time: formatTime(exception.start_time),
            end_time: formatTime(exception.end_time),
            note: exception.note ?? '',
        });
        setErrors({});
        setFeedback('');
        setModalOpen(true);
    };

    const handleClose = () => setModalOpen(false);

    async function handleSubmit() {
        const parsed = exceptionFormSchema.safeParse(form);
        if (!parsed.success) {
            const fieldErrors: Record<string, string> = {};
            parsed.error.errors.forEach((err) => {
                if (err.path[0]) fieldErrors[err.path[0] as string] = err.message;
            });
            setErrors(fieldErrors);
            return;
        }
        if (!parsed.data.is_closed && (!parsed.data.start_time || !parsed.data.end_time)) {
            setErrors({ end_time: 'Indicá hora de inicio y fin, o marcá el día como cerrado.' });
            return;
        }
        setErrors({});

        const payload = {
            professional_id: professionalId,
            date: parsed.data.date,
            is_closed: parsed.data.is_closed,
            start_time: parsed.data.is_closed ? null : parsed.data.start_time,
            end_time: parsed.data.is_closed ? null : parsed.data.end_time,
            note: parsed.data.note?.trim() ?? '',
        };

        try {
            if (editing) {
                await updateMutation.mutateAsync({ id: editing.id, payload });
                setFeedback('Excepción actualizada.');
            } else {
                await createMutation.mutateAsync(payload);
                setFeedback('Excepción creada.');
            }
            setModalOpen(false);
        } catch (error) {
            if (error instanceof ApiError && error.status === 400 && error.payload && typeof error.payload === 'object') {
                const data = error.payload as Record<string, unknown>;
                const fieldErrors: Record<string, string> = {};
                for (const [field, value] of Object.entries(data)) {
                    if (Array.isArray(value) && value.length > 0) {
                        fieldErrors[field === 'non_field_errors' ? 'date' : field] = String(value[0]);
                    } else if (typeof value === 'string') {
                        fieldErrors.date = value;
                    }
                }
                if (Object.keys(fieldErrors).length > 0) {
                    setErrors(fieldErrors);
                } else {
                    setFeedback('No pudimos guardar la excepción.');
                }
            } else {
                setFeedback('No pudimos guardar la excepción.');
            }
        }
    }

    async function handleDelete(id: string) {
        setDeletingId(id);
        try {
            await deleteMutation.mutateAsync(id);
            setFeedback('Excepción eliminada.');
        } catch {
            setFeedback('No pudimos eliminar la excepción.');
        } finally {
            setDeletingId(null);
        }
    }

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between">
                <div className="text-sm">
                    {exceptionsQuery.isError && <p className="text-rose-600">No pudimos cargar las excepciones.</p>}
                    {feedback && <p className="text-slate-500">{feedback}</p>}
                </div>
                {canManage && (
                    <button
                        type="button"
                        onClick={handleOpenCreate}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                    >
                        Nueva excepción
                    </button>
                )}
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white">
                {exceptionsQuery.isLoading ? (
                    <div className="py-8 text-center text-sm text-slate-500">Cargando excepciones...</div>
                ) : exceptions.length === 0 ? (
                    <div className="py-8 text-center text-sm text-slate-500">No hay excepciones cargadas para este alcance.</div>
                ) : (
                    <ul className="divide-y divide-slate-100">
                        {exceptions.map((exception) => (
                            <li key={exception.id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
                                <div>
                                    <p className="text-sm font-medium text-slate-800">{formatDate(exception.date)}</p>
                                    <p className="text-xs text-slate-500">
                                        {exception.is_closed
                                            ? 'Cerrado'
                                            : `${formatTime(exception.start_time)} - ${formatTime(exception.end_time)}`}
                                        {exception.note && ` · ${exception.note}`}
                                    </p>
                                </div>
                                {canManage && (
                                    <div className="flex gap-2 text-xs font-semibold">
                                        <button
                                            type="button"
                                            onClick={() => handleOpenEdit(exception)}
                                            className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 hover:border-slate-900 hover:text-slate-900"
                                        >
                                            Editar
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => handleDelete(exception.id)}
                                            disabled={deletingId === exception.id}
                                            className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 hover:border-rose-600 hover:text-rose-600 disabled:opacity-50"
                                        >
                                            Eliminar
                                        </button>
                                    </div>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
            </div>

            <Modal open={modalOpen} onClose={handleClose} title={editing ? 'Editar excepción' : 'Nueva excepción'}>
                <fieldset disabled={isSaving} className="space-y-4">
                    <legend className="sr-only">{editing ? 'Formulario para editar excepción' : 'Formulario para crear excepción'}</legend>
                    <label className="block text-sm font-medium text-slate-700">
                        Fecha <span className="text-rose-600" aria-hidden="true">*</span>
                        <input
                            type="date"
                            value={form.date}
                            onChange={(event) => setForm((prev) => ({ ...prev, date: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                            required
                        />
                        {errors.date && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.date}</span>}
                    </label>

                    <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                        <input
                            type="checkbox"
                            checked={form.is_closed}
                            onChange={(event) => setForm((prev) => ({ ...prev, is_closed: event.target.checked }))}
                            className="size-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
                        />
                        Día cerrado
                    </label>

                    {!form.is_closed && (
                        <div className="grid gap-4 md:grid-cols-2">
                            <label className="text-sm font-medium text-slate-700">
                                Desde
                                <input
                                    type="time"
                                    value={form.start_time}
                                    onChange={(event) => setForm((prev) => ({ ...prev, start_time: event.target.value }))}
                                    className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                                />
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
                    )}

                    <label className="block text-sm font-medium text-slate-700">
                        Nota (opcional)
                        <input
                            type="text"
                            value={form.note}
                            onChange={(event) => setForm((prev) => ({ ...prev, note: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                            placeholder="Ej: Feriado nacional"
                        />
                        {errors.note && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.note}</span>}
                    </label>

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

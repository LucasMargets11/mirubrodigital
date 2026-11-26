"use client";

import { useState, type ReactNode } from 'react';

import { Modal } from '@/components/ui/modal';
import { resolveLeadApiError } from '@/features/leads/errors';
import { useCreateLeadNote, useDeleteLeadNote, useLeadNotes, useUpdateLeadNote } from '@/features/leads/hooks';
import { LEAD_NOTE_MAX_LENGTH, type LeadNote } from '@/features/leads/types';
import { dateTimeInTimeZone } from '@/lib/business-time';

export const LEAD_NOTES_PAGE_SIZE = 20;

/** `created_at`/`updated_at` difieren en microsegundos al crear: solo cuenta una edición real. */
function wasEdited(note: LeadNote) {
    return Date.parse(note.updated_at) - Date.parse(note.created_at) > 1000;
}

type Editing = { mode: 'create' } | { mode: 'edit'; note: LeadNote };

/**
 * Notas internas del Lead (`/api/v1/leads/{id}/notes/`), mismo patrón que las
 * notas de la ficha de cliente. Lectura con `view_leads`; crear/editar/borrar
 * con `manage_leads` (el contrato no restringe por autor). No es un chat.
 */
export function LeadNotes({ leadId, canManage, timeZone }: { leadId: string; canManage: boolean; timeZone: string }) {
    const [limit, setLimit] = useState(LEAD_NOTES_PAGE_SIZE);
    const [editing, setEditing] = useState<Editing | null>(null);
    const [deleting, setDeleting] = useState<LeadNote | null>(null);

    const query = useLeadNotes(leadId, { limit });
    const notes = query.data?.results ?? [];
    const total = query.data?.count ?? 0;

    return (
        <section aria-label="Notas internas" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Notas internas</h3>
                    <p className="text-xs text-slate-400">Solo las ve tu equipo.</p>
                </div>
                {canManage ? (
                    <button
                        type="button"
                        onClick={() => setEditing({ mode: 'create' })}
                        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900"
                    >
                        + Agregar nota
                    </button>
                ) : null}
            </div>

            {query.isLoading ? (
                <p className="mt-3 text-sm text-slate-500">Cargando notas...</p>
            ) : query.isError ? (
                <p role="alert" className="mt-3 text-sm text-rose-600">
                    {resolveLeadApiError(query.error, 'No pudimos cargar las notas.')}{' '}
                    <button type="button" onClick={() => void query.refetch()} className="font-semibold underline">
                        Reintentar
                    </button>
                </p>
            ) : notes.length === 0 ? (
                <p className="mt-3 text-sm text-slate-500">Todavía no hay notas para este lead.</p>
            ) : (
                <ul className="mt-3 divide-y divide-slate-100">
                    {notes.map((note) => (
                        <li key={note.id} data-testid="lead-note" className="py-3">
                            <p className="text-xs text-slate-400">
                                {dateTimeInTimeZone(note.created_at, timeZone)} · {note.author?.name ?? 'Usuario eliminado'}
                                {wasEdited(note) ? ' · editada' : ''}
                            </p>
                            <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-800">{note.body}</p>
                            {canManage ? (
                                <div className="mt-1 flex gap-3 text-xs font-semibold">
                                    <button
                                        type="button"
                                        onClick={() => setEditing({ mode: 'edit', note })}
                                        className="text-slate-500 hover:text-slate-900"
                                    >
                                        Editar
                                    </button>
                                    <button type="button" onClick={() => setDeleting(note)} className="text-rose-500 hover:text-rose-700">
                                        Eliminar
                                    </button>
                                </div>
                            ) : null}
                        </li>
                    ))}
                </ul>
            )}

            {notes.length < total ? (
                <button
                    type="button"
                    onClick={() => setLimit((current) => current + LEAD_NOTES_PAGE_SIZE)}
                    className="mt-2 text-sm font-semibold text-slate-500 hover:text-slate-900"
                >
                    Ver más notas
                </button>
            ) : null}

            {canManage && editing ? <LeadNoteFormModal leadId={leadId} editing={editing} onClose={() => setEditing(null)} /> : null}
            {canManage && deleting ? <DeleteLeadNoteModal leadId={leadId} note={deleting} onClose={() => setDeleting(null)} /> : null}
        </section>
    );
}

function ModalFooter({
    error,
    onCancel,
    confirm,
}: {
    error: string | null;
    onCancel: () => void;
    confirm: ReactNode;
}) {
    return (
        <div className="space-y-3">
            {error ? (
                <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                    {error}
                </p>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
                <button
                    type="button"
                    onClick={onCancel}
                    className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 sm:py-2"
                >
                    Cancelar
                </button>
                {confirm}
            </div>
        </div>
    );
}

function LeadNoteFormModal({ leadId, editing, onClose }: { leadId: string; editing: Editing; onClose: () => void }) {
    const [body, setBody] = useState(editing.mode === 'edit' ? editing.note.body : '');
    const [error, setError] = useState<string | null>(null);
    const createMutation = useCreateLeadNote(leadId);
    const updateMutation = useUpdateLeadNote(leadId);
    const isPending = createMutation.isPending || updateMutation.isPending;
    const trimmed = body.trim();

    const handleSave = async () => {
        if (!trimmed) {
            setError('La nota no puede estar vacía.');
            return;
        }
        setError(null);
        try {
            if (editing.mode === 'create') {
                await createMutation.mutateAsync(trimmed);
            } else {
                await updateMutation.mutateAsync({ noteId: editing.note.id, body: trimmed });
            }
            onClose();
        } catch (err) {
            setError(resolveLeadApiError(err, 'No pudimos guardar la nota. Intentá nuevamente.'));
        }
    };

    const footer = (
        <ModalFooter
            error={error}
            onCancel={onClose}
            confirm={
                <button
                    type="button"
                    disabled={isPending || !trimmed}
                    onClick={handleSave}
                    className="rounded-full border border-slate-900 bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200 sm:py-2"
                >
                    {isPending ? 'Guardando...' : editing.mode === 'create' ? 'Agregar nota' : 'Guardar cambios'}
                </button>
            }
        />
    );

    return (
        <Modal open eyebrow={null} title={editing.mode === 'create' ? 'Nueva nota interna' : 'Editar nota'} onClose={onClose} footer={footer}>
            <label className="block text-sm font-medium text-slate-700" htmlFor="lead-note-body">
                Nota
            </label>
            <textarea
                id="lead-note-body"
                value={body}
                onChange={(event) => setBody(event.target.value)}
                maxLength={LEAD_NOTE_MAX_LENGTH}
                rows={5}
                autoFocus
                placeholder="Ej.: Le escribimos por WhatsApp, espera confirmación."
                className="w-full resize-y rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
            />
            <p className="text-right text-xs text-slate-400">
                {body.length}/{LEAD_NOTE_MAX_LENGTH}
            </p>
        </Modal>
    );
}

function DeleteLeadNoteModal({ leadId, note, onClose }: { leadId: string; note: LeadNote; onClose: () => void }) {
    const [error, setError] = useState<string | null>(null);
    const deleteMutation = useDeleteLeadNote(leadId);

    const handleDelete = async () => {
        setError(null);
        try {
            await deleteMutation.mutateAsync(note.id);
            onClose();
        } catch (err) {
            setError(resolveLeadApiError(err, 'No pudimos eliminar la nota. Intentá nuevamente.'));
        }
    };

    const footer = (
        <ModalFooter
            error={error}
            onCancel={onClose}
            confirm={
                <button
                    type="button"
                    disabled={deleteMutation.isPending}
                    onClick={handleDelete}
                    className="rounded-full border border-rose-600 bg-rose-600 px-5 py-2.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60 sm:py-2"
                >
                    {deleteMutation.isPending ? 'Eliminando...' : 'Eliminar nota'}
                </button>
            }
        />
    );

    return (
        <Modal open eyebrow={null} title="¿Eliminar esta nota?" onClose={onClose} footer={footer}>
            <p className="text-sm text-slate-600">Esta acción no se puede deshacer.</p>
            <blockquote className="whitespace-pre-wrap break-words rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-800">
                {note.body}
            </blockquote>
        </Modal>
    );
}

"use client";

import { useState } from 'react';

import { Modal } from '@/components/ui/modal';
import {
    useCreateCustomerNote,
    useCustomerNotes,
    useDeleteCustomerNote,
    useUpdateCustomerNote,
} from '@/features/customers/hooks';
import { CUSTOMER_NOTE_MAX_LENGTH, type CustomerNote } from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';
import { calendarParts, dateInTimeZone } from '@/lib/business-time';

import { MONTHS } from './customer-upcoming-appointments';

export const NOTES_PAGE_SIZE = 20;

/** "02 oct 2026" en la zona del Business. */
function formatNoteDay(iso: string, timeZone: string) {
    const { year, monthIndex, day } = calendarParts(dateInTimeZone(iso, timeZone));
    return `${String(day).padStart(2, '0')} ${MONTHS[monthIndex]} ${year}`;
}

function resolveNoteApiError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.payload && typeof error.payload === 'object') {
        const payload = error.payload as Record<string, unknown>;
        if (typeof payload.detail === 'string') return payload.detail;
        if (typeof payload.message === 'string') return payload.message;
        const first = Object.values(payload).find((value) => Array.isArray(value) && value.length > 0);
        if (Array.isArray(first) && typeof first[0] === 'string') return first[0];
    }
    return fallback;
}

/** `created_at`/`updated_at` difieren en microsegundos al crear: solo cuenta una edición real. */
function wasEdited(note: CustomerNote) {
    return Date.parse(note.updated_at) - Date.parse(note.created_at) > 1000;
}

type Editing = { mode: 'create' } | { mode: 'edit'; note: CustomerNote };

/**
 * Notas internas del equipo (CUSTOMER 04C), sección propia de la ficha: NO
 * entran en la timeline todavía. Lectura con `view_customers`; las acciones
 * solo se muestran con `manage_customer_notes` (`canManage`: owner/admin/
 * manager, CUSTOMER 04C.1; NO `manage_customers`) y el backend lo vuelve a exigir. Las mutaciones solo refrescan esta lista.
 */
export function CustomerNotes({
    customerId,
    canManage,
    timeZone,
    creating: creatingProp,
    onCreatingChange,
}: {
    customerId: string;
    canManage: boolean;
    timeZone: string;
    /**
     * CUSTOMER 06: alta controlada desde afuera (botón "Agregar nota" del
     * header de la ficha). Sin estas props la sección maneja su propio estado.
     */
    creating?: boolean;
    onCreatingChange?: (creating: boolean) => void;
}) {
    const [limit, setLimit] = useState(NOTES_PAGE_SIZE);
    const [editing, setEditing] = useState<Editing | null>(null);
    const [creatingLocal, setCreatingLocal] = useState(false);
    const creating = creatingProp ?? creatingLocal;
    const setCreating = onCreatingChange ?? setCreatingLocal;
    const formTarget: Editing | null = creating ? { mode: 'create' } : editing;
    const [deleting, setDeleting] = useState<CustomerNote | null>(null);

    const query = useCustomerNotes(customerId, { limit });
    const notes = query.data?.results ?? [];
    const total = query.data?.count ?? 0;

    return (
        <section aria-label="Notas internas" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Notas internas</h3>
                    <p className="text-xs text-slate-400">Solo las ve tu equipo, nunca el cliente.</p>
                </div>
                {canManage ? (
                    <button
                        type="button"
                        onClick={() => {
                            setEditing(null);
                            setCreating(true);
                        }}
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
                    {resolveNoteApiError(query.error, 'No pudimos cargar las notas.')}
                </p>
            ) : notes.length === 0 ? (
                <p className="mt-3 text-sm text-slate-500">No hay notas internas para este cliente.</p>
            ) : (
                <ul className="mt-3 divide-y divide-slate-100">
                    {notes.map((note) => (
                        <li key={note.id} data-testid="customer-note" className="py-3">
                            <p className="text-xs text-slate-400">
                                {formatNoteDay(note.created_at, timeZone)} · {note.author?.name ?? 'Usuario eliminado'}
                                {wasEdited(note) ? ' · editada' : ''}
                            </p>
                            <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-800">{note.body}</p>
                            {canManage ? (
                                <div className="mt-1 flex gap-3 text-xs font-semibold">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setCreating(false);
                                            setEditing({ mode: 'edit', note });
                                        }}
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
                    onClick={() => setLimit((current) => current + NOTES_PAGE_SIZE)}
                    className="mt-2 text-sm font-semibold text-slate-500 hover:text-slate-900"
                >
                    Ver más notas
                </button>
            ) : null}

            {canManage && formTarget ? (
                <CustomerNoteFormModal
                    customerId={customerId}
                    editing={formTarget}
                    onClose={() => (formTarget.mode === 'create' ? setCreating(false) : setEditing(null))}
                />
            ) : null}
            {canManage && deleting ? (
                <DeleteCustomerNoteModal customerId={customerId} note={deleting} onClose={() => setDeleting(null)} />
            ) : null}
        </section>
    );
}

function CustomerNoteFormModal({ customerId, editing, onClose }: { customerId: string; editing: Editing; onClose: () => void }) {
    const [body, setBody] = useState(editing.mode === 'edit' ? editing.note.body : '');
    const [error, setError] = useState<string | null>(null);
    const createMutation = useCreateCustomerNote(customerId);
    const updateMutation = useUpdateCustomerNote(customerId);
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
            setError(resolveNoteApiError(err, 'No pudimos guardar la nota. Intentá nuevamente.'));
        }
    };

    const footer = (
        <div className="space-y-3">
            {error ? (
                <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                    {error}
                </p>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
                <button
                    type="button"
                    onClick={onClose}
                    className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 sm:py-2"
                >
                    Cancelar
                </button>
                <button
                    type="button"
                    disabled={isPending || !trimmed}
                    onClick={handleSave}
                    className="rounded-full border border-slate-900 bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200 sm:py-2"
                >
                    {isPending ? 'Guardando...' : editing.mode === 'create' ? 'Agregar nota' : 'Guardar cambios'}
                </button>
            </div>
        </div>
    );

    return (
        <Modal open eyebrow={null} title={editing.mode === 'create' ? 'Nueva nota interna' : 'Editar nota'} onClose={onClose} footer={footer}>
            <label className="block text-sm font-medium text-slate-700" htmlFor="customer-note-body">
                Nota
            </label>
            <textarea
                id="customer-note-body"
                value={body}
                onChange={(event) => setBody(event.target.value)}
                maxLength={CUSTOMER_NOTE_MAX_LENGTH}
                rows={5}
                autoFocus
                placeholder="Ej.: Prefiere turnos después de las 17."
                className="w-full resize-y rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
            />
            <p className="text-right text-xs text-slate-400">
                {body.length}/{CUSTOMER_NOTE_MAX_LENGTH}
            </p>
        </Modal>
    );
}

function DeleteCustomerNoteModal({ customerId, note, onClose }: { customerId: string; note: CustomerNote; onClose: () => void }) {
    const [error, setError] = useState<string | null>(null);
    const deleteMutation = useDeleteCustomerNote(customerId);

    const handleDelete = async () => {
        setError(null);
        try {
            await deleteMutation.mutateAsync(note.id);
            onClose();
        } catch (err) {
            setError(resolveNoteApiError(err, 'No pudimos eliminar la nota. Intentá nuevamente.'));
        }
    };

    const footer = (
        <div className="space-y-3">
            {error ? (
                <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                    {error}
                </p>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-3">
                <button
                    type="button"
                    onClick={onClose}
                    className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 sm:py-2"
                >
                    Cancelar
                </button>
                <button
                    type="button"
                    disabled={deleteMutation.isPending}
                    onClick={handleDelete}
                    className="rounded-full border border-rose-600 bg-rose-600 px-5 py-2.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60 sm:py-2"
                >
                    {deleteMutation.isPending ? 'Eliminando...' : 'Eliminar nota'}
                </button>
            </div>
        </div>
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

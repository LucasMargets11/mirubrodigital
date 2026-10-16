"use client";

import { useState } from 'react';

import { DatePicker, formatLongDate } from '@/components/ui/date-picker';
import { Modal } from '@/components/ui/modal';
import { reminderPresets, REMINDER_DEFAULT_TIME, toRemindAt } from '@/features/customers/reminder-presets';
import {
    useCreateCustomerReminder,
    useCustomerAppointments,
    useCustomerReminders,
    useUpdateCustomerReminder,
} from '@/features/customers/hooks';
import {
    CUSTOMER_REMINDER_DESCRIPTION_MAX_LENGTH,
    CUSTOMER_REMINDER_TITLE_MAX_LENGTH,
    type CustomerReminder,
    type CustomerReminderPayload,
} from '@/features/customers/types';
import { ApiError } from '@/lib/api/client';
import { addCalendarDays, dateInTimeZone, timeInTimeZone, todayInTimeZone } from '@/lib/business-time';

import { formatAppointmentWhen } from './customer-upcoming-appointments';

export const REMINDERS_PAGE_SIZE = 20;
export const CLOSED_REMINDERS_PAGE_SIZE = 10;

function resolveReminderApiError(error: unknown, fallback: string) {
    if (error instanceof ApiError && error.payload && typeof error.payload === 'object') {
        const payload = error.payload as Record<string, unknown>;
        if (typeof payload.detail === 'string') return payload.detail;
        if (typeof payload.message === 'string') return payload.message;
        const first = Object.values(payload).find((value) => Array.isArray(value) && value.length > 0);
        if (Array.isArray(first) && typeof first[0] === 'string') return first[0];
    }
    return fallback;
}

const STATUS_BADGE: Record<CustomerReminder['status'], string> = {
    pending: 'bg-sky-100 text-sky-700',
    completed: 'bg-emerald-100 text-emerald-700',
    cancelled: 'bg-slate-200 text-slate-600',
};

/** Estado visible: "Vencido" es derivado (`is_overdue`), nunca un estado guardado. */
export function ReminderStatusBadge({ reminder }: { reminder: CustomerReminder }) {
    if (reminder.status === 'pending' && reminder.is_overdue) {
        return <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-semibold text-rose-700">Vencido</span>;
    }
    return (
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_BADGE[reminder.status]}`}>
            {reminder.status_display}
        </span>
    );
}

type FormTarget = { mode: 'create' } | { mode: 'edit'; reminder: CustomerReminder };

/**
 * Recordatorios internos del equipo (CUSTOMER 07A), sección propia de la
 * ficha (NO entran en la timeline). Pendientes arriba (el backend los ordena
 * por `remind_at`, así que los vencidos quedan primero); completados y
 * cancelados detrás de "Ver anteriores", que recién ahí se piden.
 *
 * Lectura con `view_customers`; acciones solo con `manage_customer_reminders`
 * (`canManage`: owner/admin/manager) y el backend lo vuelve a exigir. Las
 * fechas se muestran en `Business.timezone`.
 */
export function CustomerReminders({
    customerId,
    canManage,
    timeZone,
    appointmentsEnabled = false,
    creating: creatingProp,
    onCreatingChange,
}: {
    customerId: string;
    canManage: boolean;
    timeZone: string;
    /** El rol ve Turnos del cliente (`appointments_summary` presente): habilita vincular un turno. */
    appointmentsEnabled?: boolean;
    /** Alta controlada desde afuera (acción "Nuevo recordatorio" del header). */
    creating?: boolean;
    onCreatingChange?: (creating: boolean) => void;
}) {
    const [limit, setLimit] = useState(REMINDERS_PAGE_SIZE);
    const [closedOpen, setClosedOpen] = useState(false);
    const [closedLimit, setClosedLimit] = useState(CLOSED_REMINDERS_PAGE_SIZE);
    const [editing, setEditing] = useState<CustomerReminder | null>(null);
    const [cancelling, setCancelling] = useState<CustomerReminder | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);
    const [creatingLocal, setCreatingLocal] = useState(false);
    const creating = creatingProp ?? creatingLocal;
    const setCreating = onCreatingChange ?? setCreatingLocal;
    const formTarget: FormTarget | null = creating ? { mode: 'create' } : editing ? { mode: 'edit', reminder: editing } : null;

    const pendingQuery = useCustomerReminders(customerId, { scope: 'pending', limit });
    const closedQuery = useCustomerReminders(customerId, { scope: 'closed', limit: closedLimit }, { enabled: closedOpen });
    const updateMutation = useUpdateCustomerReminder(customerId);

    const pending = pendingQuery.data?.results ?? [];
    const pendingTotal = pendingQuery.data?.count ?? 0;
    const closedTotal = pendingQuery.data?.counts?.closed ?? 0;
    const closed = closedQuery.data?.results ?? [];
    const overdueCount = pending.filter((reminder) => reminder.is_overdue).length;

    const complete = async (reminder: CustomerReminder) => {
        setActionError(null);
        try {
            await updateMutation.mutateAsync({ reminderId: reminder.id, payload: { status: 'completed' } });
        } catch (err) {
            setActionError(resolveReminderApiError(err, 'No pudimos completar el recordatorio. Intentá nuevamente.'));
        }
    };

    return (
        <section aria-label="Recordatorios" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Recordatorios</h3>
                    <p className="text-xs text-slate-400">Tareas internas del equipo. No se envían al cliente.</p>
                </div>
                {canManage ? (
                    <button
                        type="button"
                        onClick={() => {
                            setEditing(null);
                            setCreating(true);
                        }}
                        className="min-h-11 rounded-full border border-slate-200 px-4 text-sm font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900 md:min-h-0 md:py-2"
                    >
                        + Nuevo recordatorio
                    </button>
                ) : null}
            </div>

            {actionError ? (
                <p role="alert" className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                    {actionError}
                </p>
            ) : null}

            <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Pendientes{pendingTotal > 0 ? ` (${pendingTotal})` : ''}
                {overdueCount > 0 ? <span className="ml-2 normal-case tracking-normal text-rose-600">· {overdueCount} vencido{overdueCount === 1 ? '' : 's'}</span> : null}
            </h4>
            {pendingQuery.isLoading ? (
                <p className="mt-2 text-sm text-slate-500">Cargando recordatorios...</p>
            ) : pendingQuery.isError ? (
                <p role="alert" className="mt-2 text-sm text-rose-600">
                    {resolveReminderApiError(pendingQuery.error, 'No pudimos cargar los recordatorios.')}
                </p>
            ) : pending.length === 0 ? (
                <p className="mt-2 text-sm text-slate-500">No hay recordatorios pendientes.</p>
            ) : (
                <ul className="mt-1 divide-y divide-slate-100" data-testid="pending-reminders">
                    {pending.map((reminder) => (
                        <li key={reminder.id} data-testid="customer-reminder" className="py-3">
                            <ReminderBody reminder={reminder} timeZone={timeZone} />
                            {canManage ? (
                                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs font-semibold">
                                    <button
                                        type="button"
                                        disabled={updateMutation.isPending}
                                        onClick={() => complete(reminder)}
                                        className="min-h-9 text-emerald-700 hover:text-emerald-900 disabled:opacity-50"
                                    >
                                        Marcar como completado
                                    </button>
                                    {/* CUSTOMER 07B: los automáticos no se editan (la automatización los pisaría). */}
                                    {reminder.is_automatic ? null : (
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setCreating(false);
                                                setEditing(reminder);
                                            }}
                                            className="min-h-9 text-slate-500 hover:text-slate-900"
                                        >
                                            Editar
                                        </button>
                                    )}
                                    <button type="button" onClick={() => setCancelling(reminder)} className="min-h-9 text-rose-500 hover:text-rose-700">
                                        Cancelar
                                    </button>
                                </div>
                            ) : null}
                        </li>
                    ))}
                </ul>
            )}
            {pending.length < pendingTotal ? (
                <button
                    type="button"
                    onClick={() => setLimit((current) => current + REMINDERS_PAGE_SIZE)}
                    className="mt-2 text-sm font-semibold text-slate-500 hover:text-slate-900"
                >
                    Ver más pendientes
                </button>
            ) : null}

            {closedTotal > 0 ? (
                <div className="mt-4 border-t border-slate-100 pt-3">
                    <button
                        type="button"
                        aria-expanded={closedOpen}
                        onClick={() => setClosedOpen((open) => !open)}
                        className="text-sm font-semibold text-slate-500 hover:text-slate-900"
                    >
                        {closedOpen ? 'Ocultar anteriores' : `Ver anteriores (${closedTotal})`}
                    </button>
                    {closedOpen ? (
                        closedQuery.isLoading ? (
                            <p className="mt-2 text-sm text-slate-500">Cargando...</p>
                        ) : closedQuery.isError ? (
                            <p role="alert" className="mt-2 text-sm text-rose-600">
                                No pudimos cargar los recordatorios anteriores.
                            </p>
                        ) : (
                            <>
                                <h4 className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Completados y cancelados</h4>
                                <ul className="mt-1 divide-y divide-slate-100" data-testid="closed-reminders">
                                    {closed.map((reminder) => (
                                        <li key={reminder.id} data-testid="customer-reminder" className="py-3 opacity-80">
                                            <ReminderBody reminder={reminder} timeZone={timeZone} />
                                        </li>
                                    ))}
                                </ul>
                                {closed.length < (closedQuery.data?.count ?? 0) ? (
                                    <button
                                        type="button"
                                        onClick={() => setClosedLimit((current) => current + CLOSED_REMINDERS_PAGE_SIZE)}
                                        className="mt-2 text-sm font-semibold text-slate-500 hover:text-slate-900"
                                    >
                                        Ver más anteriores
                                    </button>
                                ) : null}
                            </>
                        )
                    ) : null}
                </div>
            ) : null}

            {canManage && formTarget ? (
                <CustomerReminderFormModal
                    customerId={customerId}
                    timeZone={timeZone}
                    editing={formTarget.mode === 'edit' ? formTarget.reminder : null}
                    appointmentsEnabled={appointmentsEnabled}
                    onClose={() => (formTarget.mode === 'create' ? setCreating(false) : setEditing(null))}
                />
            ) : null}
            {canManage && cancelling ? (
                <CancelCustomerReminderModal customerId={customerId} reminder={cancelling} timeZone={timeZone} onClose={() => setCancelling(null)} />
            ) : null}
        </section>
    );
}

function ReminderBody({ reminder, timeZone }: { reminder: CustomerReminder; timeZone: string }) {
    return (
        <>
            <div className="flex flex-wrap items-center gap-2">
                <p className="break-words text-sm font-semibold text-slate-900">{reminder.title}</p>
                <ReminderStatusBadge reminder={reminder} />
                {/* CUSTOMER 07C: el aviso interno ya salió; sigue pendiente hasta completarlo/cancelarlo. */}
                {reminder.status === 'pending' && reminder.notified_at ? (
                    <span
                        title={`Aviso enviado al equipo el ${formatAppointmentWhen(reminder.notified_at, timeZone)}`}
                        className="rounded-full border border-slate-200 px-2 py-0.5 text-[11px] font-semibold text-slate-500"
                    >
                        Avisado
                    </span>
                ) : null}
                {reminder.is_automatic ? (
                    <span
                        title={reminder.source_display}
                        className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[11px] font-semibold text-violet-700"
                    >
                        Automático
                    </span>
                ) : null}
            </div>
            <p className={`mt-0.5 text-xs ${reminder.status === 'pending' && reminder.is_overdue ? 'font-semibold text-rose-600' : 'text-slate-500'}`}>
                <time dateTime={reminder.remind_at}>{formatAppointmentWhen(reminder.remind_at, timeZone)}</time>
                {reminder.status === 'completed' && reminder.completed_at ? (
                    <span className="font-normal text-slate-400"> · completado {formatAppointmentWhen(reminder.completed_at, timeZone)}</span>
                ) : null}
            </p>
            {reminder.description ? <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-700">{reminder.description}</p> : null}
            <p className="mt-1 text-xs text-slate-400">
                {reminder.appointment_start_at ? `Turno del ${formatAppointmentWhen(reminder.appointment_start_at, timeZone)} · ` : ''}
                {reminder.is_automatic ? reminder.source_display : `Creado por ${reminder.created_by?.name ?? 'usuario eliminado'}`}
            </p>
        </>
    );
}

/**
 * Formulario único de recordatorio (alta y edición). Lo usan la sección y la
 * acción rápida del header; `appointmentId` deja preparado abrirlo desde un
 * turno (CUSTOMER 07B) con el vínculo ya elegido.
 *
 * Fecha (DatePicker de Turnos) + hora se interpretan en `Business.timezone`:
 * se envía `remind_at` sin offset y el backend lo resuelve en esa zona.
 */
export function CustomerReminderFormModal({
    customerId,
    timeZone,
    editing = null,
    appointmentId = null,
    appointmentsEnabled = false,
    onClose,
    onSaved,
    now,
}: {
    customerId: string;
    timeZone: string;
    editing?: CustomerReminder | null;
    /** Turno preseleccionado (p.ej. abierto desde la agenda). */
    appointmentId?: string | null;
    appointmentsEnabled?: boolean;
    onClose: () => void;
    onSaved?: (reminder: CustomerReminder) => void;
    /** Inyectable para tests; por defecto el reloj real. */
    now?: Date;
}) {
    const [clock] = useState(() => now ?? new Date());
    const today = todayInTimeZone(timeZone, clock);
    const [title, setTitle] = useState(editing?.title ?? '');
    const [description, setDescription] = useState(editing?.description ?? '');
    const [date, setDate] = useState(editing ? dateInTimeZone(editing.remind_at, timeZone) : addCalendarDays(today, 1));
    const [time, setTime] = useState(editing ? timeInTimeZone(editing.remind_at, timeZone) : REMINDER_DEFAULT_TIME);
    const initialAppointment = editing ? editing.appointment_id : appointmentId;
    const [linkedAppointment, setLinkedAppointment] = useState<string>(initialAppointment ?? '');
    const [error, setError] = useState<string | null>(null);

    const appointmentsQuery = useCustomerAppointments(customerId, { scope: 'upcoming', limit: 25 }, { enabled: appointmentsEnabled });
    // Gate explícito además de `enabled`: un query deshabilitado igual devuelve lo que haya en caché.
    const upcomingAppointments = appointmentsEnabled ? (appointmentsQuery.data?.results ?? []) : [];
    const appointmentOptions = upcomingAppointments.map((appt) => ({
        id: appt.id,
        label: `${formatAppointmentWhen(appt.start_at, timeZone)} · ${appt.service_name}`,
    }));
    if (initialAppointment && !appointmentOptions.some((option) => option.id === initialAppointment)) {
        // Turno ya vinculado que no está entre los próximos (pasado o no visible): se conserva.
        const start = editing?.appointment_start_at;
        appointmentOptions.unshift({ id: initialAppointment, label: start ? formatAppointmentWhen(start, timeZone) : 'Turno vinculado' });
    }
    const showAppointmentField = appointmentOptions.length > 0;

    const createMutation = useCreateCustomerReminder(customerId);
    const updateMutation = useUpdateCustomerReminder(customerId);
    const isPending = createMutation.isPending || updateMutation.isPending;
    const trimmedTitle = title.trim();
    const presets = reminderPresets(timeZone, clock);

    const handleSave = async () => {
        if (!trimmedTitle) {
            setError('El título es obligatorio.');
            return;
        }
        if (!date || !/^\d{2}:\d{2}$/.test(time)) {
            setError('Elegí fecha y hora.');
            return;
        }
        setError(null);
        const payload: CustomerReminderPayload = {
            title: trimmedTitle,
            description: description.trim(),
            remind_at: toRemindAt(date, time),
        };
        if (showAppointmentField || editing?.appointment_id) payload.appointment_id = linkedAppointment || null;
        try {
            const saved = editing
                ? await updateMutation.mutateAsync({ reminderId: editing.id, payload })
                : await createMutation.mutateAsync(payload);
            onSaved?.(saved);
            onClose();
        } catch (err) {
            setError(resolveReminderApiError(err, 'No pudimos guardar el recordatorio. Intentá nuevamente.'));
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
                    disabled={isPending || !trimmedTitle}
                    onClick={handleSave}
                    className="rounded-full border border-slate-900 bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-200 sm:py-2"
                >
                    {isPending ? 'Guardando...' : editing ? 'Guardar cambios' : 'Crear recordatorio'}
                </button>
            </div>
        </div>
    );

    return (
        <Modal open eyebrow={null} title={editing ? 'Editar recordatorio' : 'Nuevo recordatorio'} onClose={onClose} footer={footer}>
            <div className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-slate-700" htmlFor="customer-reminder-title">
                        Título <span className="text-rose-600" aria-hidden="true">*</span>
                    </label>
                    <input
                        id="customer-reminder-title"
                        value={title}
                        onChange={(event) => setTitle(event.target.value)}
                        maxLength={CUSTOMER_REMINDER_TITLE_MAX_LENGTH}
                        autoFocus
                        required
                        placeholder="Ej.: Llamar para confirmar el turno"
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2.5 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
                    />
                </div>

                <div>
                    <p className="text-sm font-medium text-slate-700">Accesos rápidos</p>
                    <div className="mt-1 flex flex-wrap gap-2" role="group" aria-label="Accesos rápidos de fecha">
                        {presets.map((preset) => {
                            const active = preset.date === date && preset.time === time;
                            return (
                                <button
                                    key={preset.key}
                                    type="button"
                                    aria-pressed={active}
                                    onClick={() => {
                                        setDate(preset.date);
                                        setTime(preset.time);
                                    }}
                                    className={`min-h-9 rounded-full border px-3 text-xs font-semibold ${
                                        active ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-600 hover:border-slate-900 hover:text-slate-900'
                                    }`}
                                >
                                    {preset.label}
                                </button>
                            );
                        })}
                    </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_9rem]">
                    <div className="block min-w-0 text-sm font-medium text-slate-700">
                        <span aria-hidden="true">
                            Fecha <span className="text-rose-600">*</span>
                        </span>
                        <DatePicker
                            label="Fecha del recordatorio"
                            value={date}
                            onChange={setDate}
                            today={today}
                            formatValue={formatLongDate}
                            triggerClassName="mt-1 py-2 font-normal"
                            sheetTitle="Fecha del recordatorio"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700" htmlFor="customer-reminder-time">
                            Hora <span className="text-rose-600" aria-hidden="true">*</span>
                        </label>
                        <input
                            id="customer-reminder-time"
                            type="time"
                            step={300}
                            value={time}
                            onChange={(event) => setTime(event.target.value)}
                            required
                            className="mt-1 min-h-11 w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
                        />
                    </div>
                </div>
                <p className="-mt-2 text-xs text-slate-400">Horario del negocio ({timeZone}).</p>

                {showAppointmentField ? (
                    <div>
                        <label className="block text-sm font-medium text-slate-700" htmlFor="customer-reminder-appointment">
                            Turno relacionado <span className="font-normal text-slate-400">(opcional)</span>
                        </label>
                        <select
                            id="customer-reminder-appointment"
                            value={linkedAppointment}
                            onChange={(event) => setLinkedAppointment(event.target.value)}
                            className="mt-1 min-h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
                        >
                            <option value="">Sin turno</option>
                            {appointmentOptions.map((option) => (
                                <option key={option.id} value={option.id}>
                                    {option.label}
                                </option>
                            ))}
                        </select>
                    </div>
                ) : null}

                <div>
                    <label className="block text-sm font-medium text-slate-700" htmlFor="customer-reminder-description">
                        Descripción <span className="font-normal text-slate-400">(opcional)</span>
                    </label>
                    <textarea
                        id="customer-reminder-description"
                        value={description}
                        onChange={(event) => setDescription(event.target.value)}
                        maxLength={CUSTOMER_REMINDER_DESCRIPTION_MAX_LENGTH}
                        rows={3}
                        placeholder="Ej.: Pedir el comprobante de la seña."
                        className="mt-1 w-full resize-y rounded-2xl border border-slate-200 px-4 py-3 text-sm text-slate-900 focus:border-slate-900 focus:outline-none"
                    />
                </div>
            </div>
        </Modal>
    );
}

function CancelCustomerReminderModal({
    customerId,
    reminder,
    timeZone,
    onClose,
}: {
    customerId: string;
    reminder: CustomerReminder;
    timeZone: string;
    onClose: () => void;
}) {
    const [error, setError] = useState<string | null>(null);
    const updateMutation = useUpdateCustomerReminder(customerId);

    const handleCancel = async () => {
        setError(null);
        try {
            await updateMutation.mutateAsync({ reminderId: reminder.id, payload: { status: 'cancelled' } });
            onClose();
        } catch (err) {
            setError(resolveReminderApiError(err, 'No pudimos cancelar el recordatorio. Intentá nuevamente.'));
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
                    Volver
                </button>
                <button
                    type="button"
                    disabled={updateMutation.isPending}
                    onClick={handleCancel}
                    className="rounded-full border border-rose-600 bg-rose-600 px-5 py-2.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-60 sm:py-2"
                >
                    {updateMutation.isPending ? 'Cancelando...' : 'Cancelar recordatorio'}
                </button>
            </div>
        </div>
    );

    return (
        <Modal open eyebrow={null} title="¿Cancelar este recordatorio?" onClose={onClose} footer={footer}>
            <p className="text-sm text-slate-600">Queda en “anteriores” como cancelado y no se puede reabrir.</p>
            <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm">
                <p className="font-semibold text-slate-900">{reminder.title}</p>
                <p className="text-xs text-slate-500">{formatAppointmentWhen(reminder.remind_at, timeZone)}</p>
            </div>
        </Modal>
    );
}

"use client";

import { useMemo, useState } from 'react';

import { Modal } from '@/components/ui/modal';
import {
    useAppointmentProfessionals,
    useAppointments,
    useCancelAppointment,
    useUpdateAppointment,
} from '@/features/appointments/hooks';
import type { Appointment, AppointmentStatus } from '@/features/appointments/types';
import { formatAppointmentCount, formatWeekLabel, weekRange, type AppointmentsView } from '@/features/appointments/week';
import { addCalendarDays, calendarParts, resolveBusinessTimeZone, todayInTimeZone } from '@/lib/business-time';

import { AppointmentFormModal } from './appointment-form-modal';
import { AppointmentsToolbar } from './appointments-toolbar';
import { DayView } from './day-view';
import { WeekView } from './week-view';

/** "lunes, 5 de octubre" de una fecha de calendario (sin depender de ninguna zona). */
function formatDateLabel(date: string): string {
    const { year, monthIndex, day } = calendarParts(date);
    return new Date(Date.UTC(year, monthIndex, day, 12)).toLocaleDateString('es-AR', {
        timeZone: 'UTC',
        weekday: 'long',
        day: 'numeric',
        month: 'long',
    });
}

/**
 * Refleja vista/fecha en la URL (`?view=week&date=…`) sin navegar: refresh y
 * back conservan el contexto. Conserva el resto de los query params.
 */
function syncUrl(view: AppointmentsView, date: string) {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    url.searchParams.set('date', date);
    if (view === 'week') {
        url.searchParams.set('view', 'week');
    } else {
        url.searchParams.delete('view');
    }
    window.history.replaceState(window.history.state, '', url.toString());
}

type TurnosClientProps = {
    canManage: boolean;
    /**
     * CUSTOMER 05: muestra el CustomerPicker (requiere `manage_appointments` +
     * `view_customers` + Clientes en el plan). Sin él, el turno se vincula por
     * teléfono como en CUSTOMER 01.
     */
    canPickCustomer?: boolean;
    /** Alta inline de Customer desde el picker (`manage_customers`/`create_sales`). */
    canCreateCustomer?: boolean;
    /**
     * Timezone IANA del Business (`session.current.business.timezone`, 7D.1).
     * "Hoy", días y horas del panel usan esta zona, nunca la del navegador.
     * Sin valor (sesión vieja) → default explícito del proyecto.
     */
    timeZone?: string;
    /** Vista inicial (Slice 7D); por defecto Día. */
    initialView?: AppointmentsView;
    /** Fecha inicial (YYYY-MM-DD), p.ej. desde el link de una notificación. */
    initialDate?: string;
    /** Turno a resaltar en la lista (id), desde el link de una notificación. */
    highlightId?: string;
};

export function TurnosClient({
    canManage,
    canPickCustomer = false,
    canCreateCustomer = false,
    timeZone: timeZoneProp,
    initialView = 'day',
    initialDate,
    highlightId,
}: TurnosClientProps) {
    const timeZone = resolveBusinessTimeZone(timeZoneProp);
    const [view, setViewState] = useState<AppointmentsView>(initialView);
    // En Semana, `date` es el ancla: la semana mostrada es la que la contiene
    // y al volver a Día se abre ese mismo día.
    const [date, setDateState] = useState(() => initialDate ?? todayInTimeZone(timeZone));
    const [professionalFilter, setProfessionalFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState<AppointmentStatus | ''>('');

    const [modalOpen, setModalOpen] = useState(false);
    const [editing, setEditing] = useState<Appointment | null>(null);
    const [feedback, setFeedback] = useState('');
    const [permissionNotice, setPermissionNotice] = useState('');
    const [cancelTarget, setCancelTarget] = useState<Appointment | null>(null);
    const [statusTarget, setStatusTarget] = useState<{ appointment: Appointment; status: 'completed' | 'no_show' } | null>(null);

    const week = useMemo(() => weekRange(date), [date]);

    function changeView(nextView: AppointmentsView) {
        setViewState(nextView);
        syncUrl(nextView, date);
    }

    function changeDate(nextDate: string) {
        if (!nextDate) return;
        setDateState(nextDate);
        syncUrl(view, nextDate);
    }

    // Una sola request: el día, o la semana entera como rango inclusive.
    const appointmentsQuery = useAppointments({
        ...(view === 'week' ? { date_from: week.from, date_to: week.to } : { date }),
        professional: professionalFilter || undefined,
        status: statusFilter || undefined,
    });
    const professionalsQuery = useAppointmentProfessionals('', false);

    const updateMutation = useUpdateAppointment();
    const cancelMutation = useCancelAppointment();

    const appointments = useMemo(() => appointmentsQuery.data ?? [], [appointmentsQuery.data]);
    const professionals = useMemo(() => professionalsQuery.data ?? [], [professionalsQuery.data]);

    function handleOpenCreate() {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para crear turnos.');
            return;
        }
        setEditing(null);
        setFeedback('');
        setModalOpen(true);
    }

    function handleOpenEdit(appointment: Appointment) {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para editar turnos.');
            return;
        }
        setEditing(appointment);
        setFeedback('');
        setModalOpen(true);
    }

    function handleCloseModal() {
        setModalOpen(false);
    }

    function handleSaved(_appointment: Appointment, mode: 'create' | 'edit') {
        setFeedback(mode === 'edit' ? 'Turno actualizado.' : 'Turno creado.');
        setModalOpen(false);
    }

    function handleAskCancel(appointment: Appointment) {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para cancelar turnos.');
            return;
        }
        setCancelTarget(appointment);
    }

    async function handleConfirmCancel() {
        if (!cancelTarget) return;
        try {
            await cancelMutation.mutateAsync(cancelTarget.id);
            setFeedback('Turno cancelado.');
        } catch {
            setFeedback('No pudimos cancelar el turno.');
        } finally {
            setCancelTarget(null);
        }
    }

    function handleAskStatus(appointment: Appointment, status: 'completed' | 'no_show') {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para esta acción.');
            return;
        }
        setStatusTarget({ appointment, status });
    }

    async function handleConfirmStatus() {
        if (!statusTarget) return;
        try {
            await updateMutation.mutateAsync({ id: statusTarget.appointment.id, payload: { status: statusTarget.status } });
            setFeedback(statusTarget.status === 'completed' ? 'Turno marcado como completado.' : 'Turno marcado como no asistió.');
        } catch {
            setFeedback('No pudimos actualizar el turno.');
        } finally {
            setStatusTarget(null);
        }
    }

    const isLoading = appointmentsQuery.isLoading;
    const hasAppointments = appointments.length > 0;
    const today = todayInTimeZone(timeZone);
    const hasFilters = Boolean(professionalFilter || statusFilter);
    const actionHandlers = canManage
        ? { onEdit: handleOpenEdit, onStatus: handleAskStatus, onCancel: handleAskCancel }
        : undefined;
    const step = view === 'week' ? 7 : 1;

    const emptyState = (
        <div className="py-10 text-center" data-testid="appointments-empty">
            <p className="font-medium text-slate-700">
                {view === 'week' ? 'No hay turnos esta semana.' : 'No hay turnos para este día.'}
            </p>
            {hasFilters ? <p className="mt-1 text-sm text-slate-500">Con los filtros seleccionados.</p> : null}
            {canManage && (
                <button
                    type="button"
                    onClick={handleOpenCreate}
                    className="mt-4 rounded-full border border-slate-300 bg-white px-5 py-2 text-sm font-semibold text-slate-700 hover:border-slate-900 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-1"
                >
                    Crear turno
                </button>
            )}
        </div>
    );

    return (
        <>
            {!canManage && (
                <p className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                    Tu rol puede consultar los turnos pero no crear ni editar.
                </p>
            )}

            <div className="text-sm" role="status" aria-live="polite">
                {appointmentsQuery.isError && <p className="text-rose-600">No pudimos cargar los turnos.</p>}
                {feedback && <p className="text-slate-500">{feedback}</p>}
                {permissionNotice && <p className="text-rose-600">{permissionNotice}</p>}
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
                <AppointmentsToolbar
                    view={view}
                    onViewChange={changeView}
                    date={date}
                    onDateChange={changeDate}
                    today={today}
                    onPrevious={() => changeDate(addCalendarDays(date, -step))}
                    onNext={() => changeDate(addCalendarDays(date, step))}
                    onToday={() => changeDate(today)}
                    periodLabel={view === 'week' ? formatWeekLabel(week) : formatDateLabel(date)}
                    isCurrentPeriod={view === 'week' ? week.days.includes(today) : date === today}
                    countLabel={!isLoading && hasAppointments ? formatAppointmentCount(appointments.length) : undefined}
                    professionals={professionals}
                    professionalFilter={professionalFilter}
                    onProfessionalFilterChange={setProfessionalFilter}
                    statusFilter={statusFilter}
                    onStatusFilterChange={setStatusFilter}
                    onCreate={canManage ? handleOpenCreate : undefined}
                />

                <div className="p-3 sm:p-4">
                    {isLoading ? (
                        <div className="py-8 text-center text-sm text-slate-500">Cargando turnos...</div>
                    ) : view === 'week' ? (
                        <>
                            {!hasAppointments ? <div className="mb-3 rounded-xl border border-dashed border-slate-200">{emptyState}</div> : null}
                            <WeekView
                                range={week}
                                appointments={appointments}
                                timeZone={timeZone}
                                highlightId={highlightId}
                                onOpen={canManage ? handleOpenEdit : undefined}
                            />
                        </>
                    ) : !hasAppointments ? (
                        emptyState
                    ) : (
                        <DayView appointments={appointments} timeZone={timeZone} highlightId={highlightId} actions={actionHandlers} />
                    )}
                </div>
            </div>

            {modalOpen ? (
                <AppointmentFormModal
                    editing={editing}
                    defaultDate={date}
                    canPickCustomer={canPickCustomer}
                    canCreateCustomer={canCreateCustomer}
                    timeZone={timeZone}
                    onClose={handleCloseModal}
                    onSaved={handleSaved}
                    onPermissionDenied={() => setPermissionNotice('Tu rol no tiene permiso para esta acción.')}
                />
            ) : null}

            <Modal open={!!cancelTarget} onClose={() => setCancelTarget(null)} title="Cancelar turno">
                <p className="mb-4 text-sm text-slate-600">
                    ¿Estás seguro de cancelar el turno de &quot;{cancelTarget?.customer_name}&quot;?
                </p>
                <div className="flex justify-end gap-3">
                    <button
                        type="button"
                        onClick={() => setCancelTarget(null)}
                        className="rounded-full border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                    >
                        Volver
                    </button>
                    <button
                        type="button"
                        onClick={handleConfirmCancel}
                        disabled={cancelMutation.isPending}
                        className="rounded-full bg-rose-600 px-5 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {cancelMutation.isPending ? 'Cancelando...' : 'Cancelar turno'}
                    </button>
                </div>
            </Modal>

            <Modal
                open={!!statusTarget}
                onClose={() => setStatusTarget(null)}
                title={statusTarget?.status === 'completed' ? 'Marcar como completado' : 'Marcar como no asistió'}
            >
                <p className="mb-4 text-sm text-slate-600">
                    ¿Confirmás este cambio de estado para &quot;{statusTarget?.appointment.customer_name}&quot;?
                </p>
                <div className="flex justify-end gap-3">
                    <button
                        type="button"
                        onClick={() => setStatusTarget(null)}
                        className="rounded-full border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                    >
                        Volver
                    </button>
                    <button
                        type="button"
                        onClick={handleConfirmStatus}
                        disabled={updateMutation.isPending}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {updateMutation.isPending ? 'Guardando...' : 'Confirmar'}
                    </button>
                </div>
            </Modal>
        </>
    );
}

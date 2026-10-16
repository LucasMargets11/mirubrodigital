"use client";

import Link from 'next/link';
import { useState } from 'react';

import { AppointmentFormModal } from '@/app/app/turnos/turnos/appointment-form-modal';
import { APPOINTMENT_STATUS_LABELS, type Appointment } from '@/features/appointments/types';
import { CustomerFormModal } from '@/features/customers/components/customer-form-modal';
import { useCustomer, useCustomerContactPreferences, useRefreshCustomerAppointmentViews } from '@/features/customers/hooks';
import type { CustomerAppointmentRef, CustomerAppointmentsSummary } from '@/features/customers/types';
import { dateInTimeZone, dateTimeInTimeZone, resolveBusinessTimeZone } from '@/lib/business-time';

import { CustomerContactPreferences } from './customer-contact-preferences';
import { CustomerDeliveries } from './customer-deliveries';
import { CustomerNotes } from './customer-notes';
import { CustomerQuickActions } from './customer-quick-actions';
import { CustomerReminders } from './customer-reminders';
import { CustomerTimeline } from './customer-timeline';
import { agendaHref, CustomerUpcomingAppointments, formatAppointmentWhen } from './customer-upcoming-appointments';

type CustomerDetailClientProps = {
    customerId: string;
    canManage: boolean;
    /** CUSTOMER 04C.1: `manage_customer_notes` (owner/admin/manager), distinto de `manage_customers`. */
    canManageNotes?: boolean;
    /** CUSTOMER 07A: `manage_customer_reminders` (owner/admin/manager). Leer recordatorios solo pide `view_customers`. */
    canManageReminders?: boolean;
    /** CUSTOMER 07D.1: `manage_customer_contact_preferences` (owner/admin/manager). Leer pide solo `view_customers`. */
    canManageContactPreferences?: boolean;
    /** Gate de UI para pedir la timeline; el backend decide igual las fuentes (CUSTOMER 04A). */
    canViewSales: boolean;
    canViewQuotes: boolean;
    /** CUSTOMER 04B: Pedidos comerciales (flag `orders` + `view_orders`). */
    canViewOrders?: boolean;
    /** `session.current.business.timezone` (7D.1); fechas de Turnos en la zona del Business. */
    businessTimeZone?: string | null;
    /**
     * CUSTOMER 06: "Nuevo turno" desde la ficha. Requiere Turnos en el
     * Business + `manage_appointments` (y `view_customers`, ya exigido por la página).
     */
    canCreateAppointments?: boolean;
    /** Alta inline de otro Customer desde el picker del turno (`manage_customers`/`create_sales`). */
    canCreateCustomer?: boolean;
};

export function CustomerDetailClient({
    customerId,
    canManage,
    canManageNotes = false,
    canManageReminders = false,
    canManageContactPreferences = false,
    canViewSales,
    canViewQuotes,
    canViewOrders = false,
    businessTimeZone,
    canCreateAppointments = false,
    canCreateCustomer = false,
}: CustomerDetailClientProps) {
    const timeZone = resolveBusinessTimeZone(businessTimeZone);
    const [editOpen, setEditOpen] = useState(false);
    const [noteCreateOpen, setNoteCreateOpen] = useState(false);
    const [reminderCreateOpen, setReminderCreateOpen] = useState(false);
    const [appointmentOpen, setAppointmentOpen] = useState(false);
    const [createdAppointment, setCreatedAppointment] = useState<Appointment | null>(null);

    const customerQuery = useCustomer(customerId);
    const customer = customerQuery.data;
    // Misma query que la sección de preferencias (react-query la comparte).
    const doNotContact = useCustomerContactPreferences(customerId).data?.do_not_contact ?? false;

    if (customerQuery.isLoading) {
        return (
            <section className="space-y-4">
                <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                    <p className="text-sm text-slate-500">Cargando cliente...</p>
                </div>
            </section>
        );
    }

    if (!customer) {
        return (
            <section className="space-y-4">
                <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                    <p className="text-sm text-slate-500">Cliente no encontrado.</p>
                </div>
            </section>
        );
    }

    return (
        <section className="space-y-4">
            {/* Header */}
            <header className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-4 shadow-sm lg:flex-row lg:items-start lg:justify-between">
                <div className="flex flex-col gap-1">
                    <Link
                        href={'/app/clientes' as any}
                        className="text-xs font-semibold uppercase tracking-wide text-slate-400 hover:text-slate-700"
                    >
                        ← Clientes
                    </Link>
                    <h2 className="text-2xl font-semibold text-slate-900">{customer.name}</h2>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-500">
                        {customer.email ? <span>{customer.email}</span> : null}
                        {customer.phone ? <span>{customer.phone}</span> : null}
                        {customer.doc_number ? (
                            <span>
                                {customer.doc_type?.toUpperCase() ?? ''} {customer.doc_number}
                            </span>
                        ) : null}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-slate-500">
                        <span
                            className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${customer.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'}`}
                        >
                            {customer.is_active ? 'Activo' : 'Inactivo'}
                        </span>
                        {doNotContact ? (
                            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-semibold text-rose-700">No contactar</span>
                        ) : null}
                        {customer.tags.map((tag) => (
                            <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                                {tag}
                            </span>
                        ))}
                        <span>Alta: {formatDay(customer.created_at, timeZone)}</span>
                    </div>
                </div>
                {/* CUSTOMER 06: cada acción solo con su permiso y si el dato existe. Un Customer inactivo no admite turnos nuevos (400 del backend). */}
                <CustomerQuickActions
                    phone={customer.phone}
                    email={customer.email}
                    onNewAppointment={
                        canCreateAppointments && customer.is_active
                            ? () => {
                                  setCreatedAppointment(null);
                                  setAppointmentOpen(true);
                              }
                            : undefined
                    }
                    onEdit={canManage ? () => setEditOpen(true) : undefined}
                    onAddNote={canManageNotes ? () => setNoteCreateOpen(true) : undefined}
                    onNewReminder={canManageReminders ? () => setReminderCreateOpen(true) : undefined}
                    doNotContact={doNotContact}
                />
            </header>

            {createdAppointment ? (
                <div
                    role="status"
                    className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"
                >
                    <span>
                        Turno creado: <span className="font-semibold">{formatAppointmentWhen(createdAppointment.start_at, timeZone)}</span>
                    </span>
                    <span className="flex items-center gap-3">
                        <Link href={agendaHref(createdAppointment, timeZone) as any} className="font-semibold underline-offset-2 hover:underline">
                            Ver en agenda
                        </Link>
                        <button
                            type="button"
                            aria-label="Cerrar aviso"
                            onClick={() => setCreatedAppointment(null)}
                            className="rounded-full px-2 text-emerald-700 hover:bg-emerald-100"
                        >
                            ✕
                        </button>
                    </span>
                </div>
            ) : null}

            {/* Recordatorios (CUSTOMER 07A): sección propia, fuera de la timeline; el header abre el mismo formulario. */}
            <CustomerReminders
                customerId={customer.id}
                canManage={canManageReminders}
                timeZone={timeZone}
                appointmentsEnabled={Boolean(customer.appointments_summary)}
                creating={reminderCreateOpen}
                onCreatingChange={setReminderCreateOpen}
            />

            {/* Notas internas (CUSTOMER 04C): sección propia, fuera de la timeline. */}
            <CustomerNotes
                customerId={customer.id}
                canManage={canManageNotes}
                timeZone={timeZone}
                creating={noteCreateOpen}
                onCreatingChange={setNoteCreateOpen}
            />

            {/* Preferencias y consentimiento de contacto (CUSTOMER 07D.1): nada se envía todavía. */}
            <CustomerContactPreferences
                customerId={customer.id}
                phone={customer.phone}
                email={customer.email}
                canManage={canManageContactPreferences}
                timeZone={timeZone}
            />

            {/* Comunicaciones externas (CUSTOMER 07D.2): solo historial, sin "Enviar". */}
            <CustomerDeliveries customerId={customer.id} timeZone={timeZone} />

            {/* `appointments_summary` solo llega si el Business tiene Turnos y el rol ve turnos: mismo gate que los turnos de la timeline. */}
            {customer.appointments_summary ? (
                <>
                    <AppointmentsSummarySection summary={customer.appointments_summary} timeZone={timeZone} />
                    <CustomerUpcomingAppointments customerId={customer.id} timeZone={timeZone} />
                </>
            ) : null}

            {/* Historial unificado (CUSTOMER 04A): solo si alguna fuente puede ser visible. */}
            {customer.appointments_summary || canViewSales || canViewQuotes || canViewOrders ? (
                <CustomerTimeline customerId={customer.id} timeZone={timeZone} />
            ) : null}

            {/* Mismo modal que el listado (CUSTOMER 02B); al guardar, el hook invalida y la ficha se re-fetchea. */}
            {canManage && editOpen ? (
                <CustomerFormModal mode="edit" customer={customer} canSubmit={canManage} onClose={() => setEditOpen(false)} />
            ) : null}

            {/* Mismo formulario que la agenda (CUSTOMER 06), con este Customer ya elegido. */}
            {canCreateAppointments && appointmentOpen ? (
                <CustomerAppointmentModal
                    customer={customer}
                    canCreateCustomer={canCreateCustomer}
                    timeZone={timeZone}
                    onClose={() => setAppointmentOpen(false)}
                    onCreated={(appointment) => {
                        setAppointmentOpen(false);
                        setCreatedAppointment(appointment);
                    }}
                />
            ) : null}
        </section>
    );
}

/**
 * Monta el formulario de turno solo al abrir (hooks de Turnos + invalidación
 * acotada a la ficha). La agenda ya se invalida en `useCreateAppointment`.
 */
function CustomerAppointmentModal({
    customer,
    canCreateCustomer,
    timeZone,
    onClose,
    onCreated,
}: {
    customer: { id: string; name: string; phone: string | null; email: string | null };
    canCreateCustomer: boolean;
    timeZone: string;
    onClose: () => void;
    onCreated: (appointment: Appointment) => void;
}) {
    const refreshCustomerViews = useRefreshCustomerAppointmentViews(customer.id);
    return (
        <AppointmentFormModal
            editing={null}
            initialCustomer={{ id: customer.id, name: customer.name, phone: customer.phone, email: customer.email }}
            canPickCustomer
            canCreateCustomer={canCreateCustomer}
            timeZone={timeZone}
            onClose={onClose}
            onSaved={(appointment) => {
                void refreshCustomerViews();
                onCreated(appointment);
            }}
        />
    );
}

// ── Resumen Turnos (CUSTOMER 02) ─────────────────────────────────────────────

function formatDay(iso: string, timeZone: string) {
    const [year, month, day] = dateInTimeZone(iso, timeZone).split('-');
    return `${day}/${month}/${year}`;
}

function AppointmentsSummarySection({ summary, timeZone }: { summary: CustomerAppointmentsSummary; timeZone: string }) {
    const stats: Array<{ label: string; value: number }> = [
        { label: 'Turnos', value: summary.total },
        { label: 'Próximos', value: summary.upcoming },
        { label: 'Completados', value: summary.completed },
        { label: 'Cancelados', value: summary.cancelled },
        { label: 'No asistió', value: summary.no_show },
    ];
    return (
        <section aria-label="Resumen de Turnos" className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Turnos</h3>
            <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
                {stats.map((stat) => (
                    <div key={stat.label} className="rounded-2xl bg-slate-50 px-3 py-2">
                        <dt className="text-xs text-slate-500">{stat.label}</dt>
                        <dd className="text-lg font-semibold text-slate-900">{stat.value}</dd>
                    </div>
                ))}
            </dl>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
                <AppointmentRefCard title="Próximo turno" appointment={summary.next_appointment} timeZone={timeZone} empty="Sin turnos próximos." />
                <AppointmentRefCard title="Último turno" appointment={summary.last_appointment} timeZone={timeZone} empty="Todavía no tuvo turnos." />
            </div>
        </section>
    );
}

function AppointmentRefCard({
    title,
    appointment,
    timeZone,
    empty,
}: {
    title: string;
    appointment: CustomerAppointmentRef | null;
    timeZone: string;
    empty: string;
}) {
    return (
        <div className="rounded-2xl border border-slate-100 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</p>
            {appointment ? (
                <div className="mt-1 space-y-0.5 text-sm">
                    <p className="font-semibold text-slate-900">{dateTimeInTimeZone(appointment.start_at, timeZone)}</p>
                    <p className="text-slate-600">
                        {appointment.service_name}
                        {appointment.professional_name ? ` · ${appointment.professional_name}` : ''}
                    </p>
                    <p className="text-xs text-slate-500">{APPOINTMENT_STATUS_LABELS[appointment.status] ?? appointment.status}</p>
                    <Link
                        href={agendaHref(appointment, timeZone) as any}
                        className="inline-block pt-1 text-xs font-semibold text-slate-500 hover:text-slate-900"
                    >
                        Ver en agenda
                    </Link>
                </div>
            ) : (
                <p className="mt-1 text-sm text-slate-500">{empty}</p>
            )}
        </div>
    );
}

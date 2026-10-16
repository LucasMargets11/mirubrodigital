"use client";

import { useState } from 'react';

import { Modal } from '@/components/ui/modal';
import { useAppointments } from '@/features/appointments/hooks';
import { APPOINTMENT_STATUS_LABELS, type AppointmentStatus } from '@/features/appointments/types';
import { useCustomerAppointments } from '@/features/customers/hooks';
import { timeInTimeZone, todayInTimeZone } from '@/lib/business-time';
import { cn } from '@/lib/utils';

import { formatAppointmentWhen } from '../../../clientes/[id]/customer-upcoming-appointments';

const CUSTOMER_APPOINTMENTS_LIMIT = 10;

/** Fila común a los dos orígenes (agenda del día / historial del cliente). */
type PickableAppointment = {
    id: string;
    start_at: string;
    service_name: string;
    customer_name: string;
    status: AppointmentStatus;
};

type LeadAppointmentPickerProps = {
    /** Customer vinculado al Lead: si se puede ver, se ofrecen primero sus turnos. */
    customer: { id: string; display_name: string } | null;
    currentAppointmentId: string | null;
    canViewCustomers: boolean;
    canViewAppointments: boolean;
    timeZone: string;
    pending: boolean;
    error: string | null;
    onSelect: (appointmentId: string) => void;
    onClose: () => void;
};

/**
 * Elegir un turno EXISTENTE para vincular (LEADS 05B). Sin endpoint propio:
 * reutiliza `GET /customers/{id}/appointments/?scope=all` (`view_customers`)
 * y la agenda del día `GET /appointments/appointments/?date=` (`view_appointments`).
 * Se listan todos los estados (cancelado/completado/vencido también): el
 * backend permite vincularlos.
 */
export function LeadAppointmentPicker({
    customer,
    currentAppointmentId,
    canViewCustomers,
    canViewAppointments,
    timeZone,
    pending,
    error,
    onSelect,
    onClose,
}: LeadAppointmentPickerProps) {
    const [date, setDate] = useState(() => todayInTimeZone(timeZone));
    const showCustomer = Boolean(customer) && canViewCustomers;

    const customerQuery = useCustomerAppointments(
        customer?.id ?? '',
        { scope: 'all', limit: CUSTOMER_APPOINTMENTS_LIMIT },
        { enabled: showCustomer },
    );
    const dayQuery = useAppointments({ date }, { enabled: canViewAppointments && Boolean(date) });

    const customerRows: PickableAppointment[] = (customerQuery.data?.results ?? []).map((item) => ({
        id: item.id,
        start_at: item.start_at,
        service_name: item.service_name,
        customer_name: item.customer_name,
        status: item.status,
    }));
    const dayRows: PickableAppointment[] = (dayQuery.data ?? []).map((item) => ({
        id: item.id,
        start_at: item.start_at,
        service_name: item.service_name,
        customer_name: item.customer_name,
        status: item.effective_status,
    }));

    const footer = (
        <div className="space-y-3">
            {error ? (
                <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                    {error}
                </p>
            ) : null}
            <div className="flex justify-end">
                <button
                    type="button"
                    onClick={onClose}
                    className="rounded-full border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 sm:py-2"
                >
                    Cancelar
                </button>
            </div>
        </div>
    );

    return (
        <Modal open eyebrow={null} title="Vincular turno" onClose={onClose} footer={footer}>
            <div className="space-y-5">
                {showCustomer && customer ? (
                    <section aria-label="Turnos del cliente" className="space-y-2">
                        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Turnos de {customer.display_name}
                        </h4>
                        <AppointmentOptions
                            loading={customerQuery.isLoading}
                            isError={customerQuery.isError}
                            onRetry={() => void customerQuery.refetch()}
                            rows={customerRows}
                            empty="Este cliente no tiene turnos."
                            label={(row) => formatAppointmentWhen(row.start_at, timeZone)}
                            currentAppointmentId={currentAppointmentId}
                            pending={pending}
                            onSelect={onSelect}
                        />
                    </section>
                ) : null}

                {canViewAppointments ? (
                    <section aria-label="Turnos por día" className="space-y-2">
                        <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Buscar en la agenda del día
                            <input
                                type="date"
                                value={date}
                                onChange={(event) => setDate(event.target.value)}
                                className="rounded-2xl border border-slate-200 px-3 py-2 text-sm font-normal normal-case tracking-normal text-slate-700 focus:border-slate-900 focus:outline-none"
                            />
                        </label>
                        <AppointmentOptions
                            loading={dayQuery.isLoading}
                            isError={dayQuery.isError}
                            onRetry={() => void dayQuery.refetch()}
                            rows={dayRows}
                            empty="No hay turnos ese día."
                            label={(row) => timeInTimeZone(row.start_at, timeZone)}
                            currentAppointmentId={currentAppointmentId}
                            pending={pending}
                            onSelect={onSelect}
                        />
                    </section>
                ) : null}

                {!showCustomer && !canViewAppointments ? (
                    <p className="text-sm text-slate-500">Tu rol no puede ver turnos para elegir uno.</p>
                ) : null}
            </div>
        </Modal>
    );
}

type AppointmentOptionsProps = {
    loading: boolean;
    isError: boolean;
    onRetry: () => void;
    rows: PickableAppointment[];
    empty: string;
    label: (row: PickableAppointment) => string;
    currentAppointmentId: string | null;
    pending: boolean;
    onSelect: (appointmentId: string) => void;
};

function AppointmentOptions({ loading, isError, onRetry, rows, empty, label, currentAppointmentId, pending, onSelect }: AppointmentOptionsProps) {
    if (loading) return <p className="text-sm text-slate-500">Cargando turnos...</p>;
    if (isError) {
        return (
            <p role="alert" className="text-sm text-rose-600">
                No pudimos cargar los turnos.{' '}
                <button type="button" onClick={onRetry} className="font-semibold underline">
                    Reintentar
                </button>
            </p>
        );
    }
    if (rows.length === 0) return <p className="text-sm text-slate-500">{empty}</p>;
    return (
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200">
            {rows.map((row) => {
                const current = row.id === currentAppointmentId;
                return (
                    <li key={row.id}>
                        <button
                            type="button"
                            disabled={pending || current}
                            onClick={() => onSelect(row.id)}
                            data-testid="lead-appointment-option"
                            className={cn(
                                'flex w-full items-start justify-between gap-3 px-3 py-2 text-left hover:bg-slate-50 disabled:cursor-not-allowed',
                                current && 'bg-slate-50',
                            )}
                        >
                            <span className="min-w-0">
                                <span className="block text-sm font-semibold text-slate-900">{label(row)}</span>
                                <span className="block truncate text-xs text-slate-500">
                                    {row.service_name} · {row.customer_name}
                                </span>
                            </span>
                            <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                                {current ? 'Vinculado' : APPOINTMENT_STATUS_LABELS[row.status] ?? row.status}
                            </span>
                        </button>
                    </li>
                );
            })}
        </ul>
    );
}

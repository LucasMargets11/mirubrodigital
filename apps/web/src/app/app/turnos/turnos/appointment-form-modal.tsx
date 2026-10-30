"use client";

import { useEffect, useMemo, useRef, useState } from 'react';
import { z } from 'zod';

import { DatePicker, formatLongDate } from '@/components/ui/date-picker';
import { Modal } from '@/components/ui/modal';
import {
    useAppointmentAvailability,
    useAppointmentProfessionals,
    useAppointmentServices,
    useCreateAppointment,
    useUpdateAppointment,
} from '@/features/appointments/hooks';
import type { Appointment, AppointmentPayload } from '@/features/appointments/types';
import { CustomerPicker, type PickedCustomer } from '@/features/customers/components/customer-picker';
import type { Customer } from '@/features/customers/types';
import { appointmentProposalErrorCode, PROPOSAL_SLOT_UNAVAILABLE, resolveLeadApiError } from '@/features/leads/errors';
import type { AppointmentProposalPayload } from '@/features/leads/types';
import { ApiError } from '@/lib/api/client';
import { dateInTimeZone, timeInTimeZone, todayInTimeZone } from '@/lib/business-time';

import { AppointmentPaymentSection } from './appointment-status';

const appointmentFormSchema = z.object({
    service_id: z.string().min(1, 'Elegí un servicio'),
    professional_id: z.string(),
    date: z.string().min(1, 'Elegí una fecha'),
    start_at: z.string().min(1, 'Elegí un horario disponible'),
    customer_name: z.string().min(2, 'El nombre debe tener al menos 2 caracteres').max(150, 'El nombre es muy largo'),
    customer_phone: z.string().min(6, 'El teléfono no es válido').max(30, 'El teléfono es muy largo'),
    customer_email: z.string().max(254).optional(),
    notes: z.string().max(1000).optional(),
});

type FormState = z.infer<typeof appointmentFormSchema>;

/** Customer canónico con el que arranca el alta (CUSTOMER 06: desde la ficha). */
export type InitialAppointmentCustomer = {
    id: string;
    name: string;
    phone: string | null;
    email: string | null;
};

function snapshotsFrom(customer: { name: string; phone?: string | null; email?: string | null }) {
    return {
        customer_name: customer.name.slice(0, 150),
        customer_phone: customer.phone ?? '',
        customer_email: customer.email ?? '',
    };
}

function initialForm(
    editing: Appointment | null,
    date: string,
    initialCustomer: InitialAppointmentCustomer | null,
    timeZone: string,
): FormState {
    if (editing) {
        return {
            service_id: editing.service.id,
            professional_id: editing.professional?.id ?? '',
            // Día del turno en la zona del Business (la misma con la que el
            // backend interpreta `date` en availability); `start_at` viaja intacto.
            date: dateInTimeZone(editing.start_at, timeZone),
            start_at: editing.start_at,
            customer_name: editing.customer_name,
            customer_phone: editing.customer_phone,
            customer_email: editing.customer_email ?? '',
            notes: editing.notes ?? '',
        };
    }
    return {
        service_id: '',
        professional_id: '',
        date,
        start_at: '',
        ...(initialCustomer ? snapshotsFrom(initialCustomer) : { customer_name: '', customer_phone: '', customer_email: '' }),
        notes: '',
    };
}

function initialPicked(editing: Appointment | null, initialCustomer: InitialAppointmentCustomer | null): PickedCustomer | null {
    if (editing) {
        // Vinculado → el picker muestra ese Customer (la tarjeta trae la ficha).
        // Legacy `customer_id=null` → picker vacío: abrir el modal no vincula nada.
        return editing.customer_id ? { id: editing.customer_id } : null;
    }
    // Desde la ficha: ya trae nombre/teléfono/email, el picker no lo vuelve a buscar.
    return initialCustomer ? { ...initialCustomer, is_active: true } : null;
}

type AppointmentFormModalProps = {
    /** Turno a editar; `null` = alta. */
    editing: Appointment | null;
    /** Fecha inicial del alta (YYYY-MM-DD, zona del Business). */
    defaultDate?: string;
    /** Alta con un Customer ya elegido (ficha del cliente, CUSTOMER 06). */
    initialCustomer?: InitialAppointmentCustomer | null;
    /** CUSTOMER 05: ver `TurnosClient`. */
    canPickCustomer: boolean;
    canCreateCustomer: boolean;
    /** Timezone IANA ya resuelta del Business. */
    timeZone: string;
    onClose: () => void;
    onSaved: (appointment: Appointment, mode: 'create' | 'edit') => void;
    /** 403 del backend (p.ej. la sesión perdió `manage_appointments`). */
    onPermissionDenied?: () => void;
    initialPatient?: Pick<AppointmentPayload, 'customer_name' | 'customer_phone' | 'notes'>;
    /** Alta orquestada desde Lead; no ejecuta el create independiente. */
    onCreate?: (payload: AppointmentPayload) => Promise<void>;
    createPending?: boolean;
    coordination?: {
        context: string;
        onPropose: (payload: AppointmentProposalPayload) => Promise<void>;
        onAppointmentConflict: () => Promise<void>;
    };
};

/**
 * Formulario de alta/edición de turno (Slice 7B → CUSTOMER 05), extraído de
 * `TurnosClient` en CUSTOMER 06 para reutilizarlo desde la ficha del cliente.
 * Única fuente de availability, validaciones y mutations del turno manual.
 * Se monta al abrir: el estado inicial sale de las props.
 */
export function AppointmentFormModal({
    editing,
    defaultDate,
    initialCustomer = null,
    canPickCustomer,
    canCreateCustomer,
    timeZone,
    onClose,
    onSaved,
    onPermissionDenied,
    initialPatient,
    onCreate,
    createPending = false,
    coordination,
}: AppointmentFormModalProps) {
    const today = todayInTimeZone(timeZone);
    const [form, setForm] = useState<FormState>(() => ({
        ...initialForm(editing, defaultDate ?? (onCreate ? '' : today), initialCustomer, timeZone),
        ...(!editing ? initialPatient : {}),
    }));
    // Customer canónico elegido (identidad). Los `customer_*` del form son
    // los snapshots del turno: editarlos nunca modifica el Customer.
    const [pickedCustomer, setPickedCustomer] = useState<PickedCustomer | null>(() => initialPicked(editing, initialCustomer));
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [saveError, setSaveError] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const submitLock = useRef(false);
    const proposalKey = useRef<string | null>(null);
    const fieldsetRef = useRef<HTMLFieldSetElement>(null);
    const closeRef = useRef(onClose);
    closeRef.current = onClose;
    const coordinating = Boolean(coordination);

    useEffect(() => {
        if (!coordinating) return;
        const opener = document.activeElement;
        const dialog = fieldsetRef.current?.closest('[role="dialog"]');
        const focusable = () => dialog ? Array.from(dialog.querySelectorAll<HTMLElement>(
            'button:not(:disabled), select:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href]',
        )).filter((element) => element.tabIndex >= 0
            && (element.getAttribute('aria-label') !== 'Cerrar' || element.textContent?.trim())) : [];
        fieldsetRef.current?.querySelector('select')?.focus();
        const onKeyDown = (event: Event) => {
            if (!(event instanceof KeyboardEvent)) return;
            if (event.key === 'Escape' && !submitLock.current) {
                event.preventDefault();
                closeRef.current();
            }
            if (event.key !== 'Tab') return;
            const elements = focusable();
            const first = elements[0];
            const last = elements[elements.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last?.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first?.focus();
            }
        };
        dialog?.addEventListener('keydown', onKeyDown);
        return () => {
            dialog?.removeEventListener('keydown', onKeyDown);
            if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
        };
    }, [coordinating]);

    const servicesQuery = useAppointmentServices('', false);
    const professionalsQuery = useAppointmentProfessionals('', false);
    const availabilityQuery = useAppointmentAvailability(
        {
            service: form.service_id,
            date: form.date,
            professional: form.professional_id || null,
            excludeAppointmentId: editing?.id ?? null,
        },
        { enabled: Boolean(form.service_id) && Boolean(form.date) },
    );

    const createMutation = useCreateAppointment();
    const updateMutation = useUpdateAppointment();
    const isSaving = submitting || createPending || createMutation.isPending || updateMutation.isPending;

    const services = useMemo(() => servicesQuery.data ?? [], [servicesQuery.data]);
    const professionals = useMemo(() => professionalsQuery.data ?? [], [professionalsQuery.data]);

    const eligibleProfessionals = useMemo(() => {
        if (!form.service_id) return professionals;
        return professionals.filter((professional) => professional.services.some((service) => service.id === form.service_id));
    }, [professionals, form.service_id]);

    const availableSlots = useMemo(() => availabilityQuery.data?.slots ?? [], [availabilityQuery.data]);

    function handleCustomerSelect(customer: Customer) {
        setPickedCustomer(customer);
        // Copia inicial de la ficha a los snapshots; el resto del turno no se toca.
        setForm((prev) => ({ ...prev, ...snapshotsFrom(customer) }));
        setErrors((prev) => {
            const next = { ...prev };
            for (const field of ['customer_id', 'customer_name', 'customer_phone', 'customer_email']) delete next[field];
            return next;
        });
    }

    function handleServiceChange(serviceId: string) {
        if (serviceId !== form.service_id) proposalKey.current = null;
        setForm((prev) => ({ ...prev, service_id: serviceId, professional_id: '', start_at: '' }));
    }

    function handleProfessionalChange(professionalId: string) {
        if (professionalId !== form.professional_id) proposalKey.current = null;
        setForm((prev) => ({ ...prev, professional_id: professionalId, start_at: '' }));
    }

    function handleDateChange(nextDate: string) {
        if (nextDate !== form.date) proposalKey.current = null;
        setForm((prev) => ({ ...prev, date: nextDate, start_at: '' }));
    }

    async function handleSubmit(propose = false) {
        if (submitLock.current || isSaving) return;
        if (onCreate && eligibleProfessionals.length > 0 && !form.professional_id) {
            setErrors({ professional_id: 'Elegí un profesional' });
            return;
        }
        const schema = propose
            ? appointmentFormSchema.pick({ service_id: true, professional_id: true, date: true, start_at: true })
            : appointmentFormSchema;
        const parsed = schema.safeParse(form);
        if (!parsed.success) {
            const fieldErrors: Record<string, string> = {};
            parsed.error.errors.forEach((err) => {
                if (err.path[0]) {
                    fieldErrors[err.path[0] as string] = err.message;
                }
            });
            setErrors(fieldErrors);
            return;
        }
        setErrors({});
        setSaveError('');

        const payload: AppointmentPayload = {
            service_id: form.service_id,
            professional_id: form.professional_id || null,
            start_at: form.start_at,
            // Con Customer elegido el backend lo usa tal cual (sin resolver por teléfono).
            customer_id: canPickCustomer && pickedCustomer ? pickedCustomer.id : undefined,
            customer_name: form.customer_name.trim(),
            customer_phone: form.customer_phone.trim(),
            customer_email: form.customer_email?.trim() || undefined,
            notes: form.notes?.trim() || undefined,
        };

        submitLock.current = true;
        setSubmitting(true);
        try {
            if (propose && coordination) {
                proposalKey.current ??= crypto.randomUUID();
                await coordination.onPropose({
                    service_id: form.service_id,
                    professional_id: form.professional_id || null,
                    start_at: form.start_at,
                    idempotency_key: proposalKey.current,
                });
                return;
            }
            if (!editing && onCreate) {
                await onCreate(payload);
                return;
            }
            const saved = editing
                ? await updateMutation.mutateAsync({ id: editing.id, payload })
                : await createMutation.mutateAsync(payload);
            onSaved(saved, editing ? 'edit' : 'create');
        } catch (error) {
            const code = appointmentProposalErrorCode(error);
            if (coordination && code === 'lead_has_appointment') {
                try {
                    await coordination.onAppointmentConflict();
                } catch (refreshError) {
                    setSaveError(resolveLeadApiError(refreshError, 'El Lead ya tiene un turno. No pudimos actualizar el detalle; cerrá y volvé a cargarlo.'));
                }
                return;
            }
            if (propose && code === 'idempotency_key_reused') {
                setSaveError('Esta clave de envío ya se usó para otra propuesta. Cambiá la selección o iniciá una propuesta nueva.');
            } else if (error instanceof ApiError && error.status === 403) {
                setSaveError('Tu rol no tiene permiso para esta acción.');
                onPermissionDenied?.();
            } else if (error instanceof ApiError && error.status === 400 && error.payload && typeof error.payload === 'object') {
                const payloadErrors = error.payload as Record<string, unknown>;
                const fieldErrors: Record<string, string> = {};
                for (const [field, value] of Object.entries(payloadErrors)) {
                    if (Array.isArray(value) && value.length > 0) {
                        fieldErrors[field] = String(value[0]);
                    }
                }
                if (Object.keys(fieldErrors).length > 0) {
                    setErrors(fieldErrors);
                    setSaveError(Object.entries(fieldErrors)
                        .filter(([field]) => !['service_id', 'professional_id', 'date', 'start_at', 'customer_id', 'customer_name', 'customer_phone', 'customer_email', 'notes'].includes(field))
                        .map(([, message]) => message).join(' '));
                    if (fieldErrors.start_at) {
                        if (propose) {
                            setErrors((prev) => ({ ...prev, start_at: PROPOSAL_SLOT_UNAVAILABLE }));
                        }
                        setForm((prev) => ({ ...prev, start_at: '' }));
                        proposalKey.current = null;
                        void availabilityQuery.refetch();
                    }
                } else {
                    setSaveError(resolveLeadApiError(error, propose ? 'No pudimos enviar la propuesta.' : 'No pudimos guardar el turno.'));
                }
            } else {
                setSaveError(resolveLeadApiError(error, propose
                    ? 'No pudimos verificar el envío de la propuesta. Reintentá sin cambiar la selección para evitar duplicados.'
                    : 'No pudimos guardar el turno.'));
            }
        } finally {
            submitLock.current = false;
            setSubmitting(false);
        }
    }

    return (
        <Modal open onClose={() => { if (!submitLock.current && !isSaving) onClose(); }} title={coordination ? 'Coordinar turno' : editing ? 'Editar turno' : 'Nuevo turno'}>
            <fieldset ref={fieldsetRef} disabled={isSaving} className="space-y-4">
                <legend className="sr-only">{editing ? 'Formulario para editar turno' : 'Formulario para crear turno'}</legend>

                {coordination ? (
                    <div className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
                        <p>{coordination.context}</p>
                        <p className="mt-1 text-xs text-slate-500">La preferencia reportada es orientativa.</p>
                    </div>
                ) : null}
                {editing ? <AppointmentPaymentSection appointment={editing} timeZone={timeZone} /> : null}
                {servicesQuery.isError || professionalsQuery.isError ? (
                    <div role="alert">
                        <p>No pudimos cargar los servicios o profesionales.</p>
                        <button type="button" onClick={() => { void servicesQuery.refetch(); void professionalsQuery.refetch(); }}>Reintentar carga</button>
                    </div>
                ) : null}

                <div className="grid gap-4 md:grid-cols-2">
                    <label className="block text-sm font-medium text-slate-700">
                        Servicio <span className="text-rose-600" aria-hidden="true">*</span>
                        <select
                            value={form.service_id}
                            onChange={(event) => handleServiceChange(event.target.value)}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                        >
                            <option value="">Elegí un servicio</option>
                            {services.map((service) => (
                                <option key={service.id} value={service.id}>
                                    {service.name} ({service.duration_minutes} min)
                                </option>
                            ))}
                        </select>
                        {errors.service_id && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.service_id}</span>}
                    </label>

                    <label className="block text-sm font-medium text-slate-700">
                        Profesional
                        <select
                            value={form.professional_id}
                            onChange={(event) => handleProfessionalChange(event.target.value)}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                        >
                            <option value="">Sin profesional asignado</option>
                            {eligibleProfessionals.map((professional) => (
                                <option key={professional.id} value={professional.id}>
                                    {professional.name}
                                </option>
                            ))}
                        </select>
                        {errors.professional_id && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.professional_id}</span>}
                    </label>
                </div>

                <div className="block text-sm font-medium text-slate-700">
                    <span aria-hidden="true">
                        Fecha <span className="text-rose-600">*</span>
                    </span>
                    <DatePicker
                        label="Fecha"
                        value={form.date}
                        onChange={handleDateChange}
                        today={today}
                        formatValue={formatLongDate}
                        triggerClassName="mt-1 py-2 font-normal"
                    />
                    {errors.date && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.date}</span>}
                </div>

                <div role="group" aria-label="Horario disponible">
                    <p className="text-sm font-medium text-slate-700">
                        Horario <span className="text-rose-600" aria-hidden="true">*</span>
                    </p>
                    {!form.service_id ? (
                        <p className="mt-1 text-xs text-slate-500">Elegí un servicio para ver los horarios disponibles.</p>
                    ) : !form.date ? (
                        <p className="mt-1 text-xs text-slate-500">Elegí una fecha para ver los horarios disponibles.</p>
                    ) : availabilityQuery.isError ? (
                        <div role="alert">
                            <p>No pudimos cargar la disponibilidad.</p>
                            <button type="button" onClick={() => void availabilityQuery.refetch()}>Reintentar disponibilidad</button>
                        </div>
                    ) : availabilityQuery.isLoading || availabilityQuery.isFetching ? (
                        <p className="mt-1 text-xs text-slate-500">Buscando horarios disponibles...</p>
                    ) : availableSlots.length === 0 ? (
                        <p className="mt-1 text-xs text-slate-500">No hay horarios disponibles para esta fecha.</p>
                    ) : (
                        <div className="mt-2 flex flex-wrap gap-2">
                            {availableSlots.map((slot) => (
                                <button
                                    key={slot.start}
                                    type="button"
                                    onClick={() => {
                                        if (slot.start !== form.start_at) proposalKey.current = null;
                                        setForm((prev) => ({ ...prev, start_at: slot.start }));
                                    }}
                                    aria-pressed={form.start_at === slot.start}
                                    className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                                        form.start_at === slot.start
                                            ? 'border-slate-900 bg-slate-900 text-white'
                                            : 'border-slate-200 text-slate-600 hover:border-slate-900 hover:text-slate-900'
                                    }`}
                                >
                                    {timeInTimeZone(slot.start, timeZone)}
                                </button>
                            ))}
                        </div>
                    )}
                    {errors.start_at && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.start_at}</span>}
                </div>

                {canPickCustomer ? (
                    <CustomerPicker
                        value={pickedCustomer}
                        onSelect={handleCustomerSelect}
                        canCreate={canCreateCustomer}
                        error={errors.customer_id}
                    />
                ) : null}

                {!coordination || !initialPatient?.customer_name || !initialPatient?.customer_phone || errors.customer_name || errors.customer_phone ? (
                <div className="grid gap-4 md:grid-cols-2">
                    <label className="block text-sm font-medium text-slate-700">
                        {canPickCustomer ? 'Nombre en el turno' : 'Cliente'} <span className="text-rose-600" aria-hidden="true">*</span>
                        <input
                            type="text"
                            value={form.customer_name}
                            onChange={(event) => setForm((prev) => ({ ...prev, customer_name: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                        />
                        {errors.customer_name && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.customer_name}</span>}
                    </label>

                    <label className="block text-sm font-medium text-slate-700">
                        Teléfono <span className="text-rose-600" aria-hidden="true">*</span>
                        <input
                            type="text"
                            value={form.customer_phone}
                            onChange={(event) => setForm((prev) => ({ ...prev, customer_phone: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                        />
                        {errors.customer_phone && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.customer_phone}</span>}
                    </label>
                </div>
                ) : null}

                {!coordination ? (
                <label className="block text-sm font-medium text-slate-700">
                    Email
                    <input
                        type="email"
                        value={form.customer_email}
                        onChange={(event) => setForm((prev) => ({ ...prev, customer_email: event.target.value }))}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                    />
                    {errors.customer_email && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.customer_email}</span>}
                </label>
                ) : null}

                {!coordination ? (
                <label className="block text-sm font-medium text-slate-700">
                    Notas
                    <textarea
                        value={form.notes}
                        onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                        rows={2}
                    />
                </label>
                ) : null}

                {saveError ? (
                    <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                        {saveError}
                    </p>
                ) : null}

                {coordination ? (
                    <div className="space-y-3 border-t border-slate-100 pt-4">
                        <div>
                            <button type="button" onClick={() => void handleSubmit(true)} disabled={isSaving} aria-busy={isSaving}
                                className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:opacity-60">
                                Enviar propuesta
                            </button>
                            <p className="mt-1 text-xs text-slate-500">El paciente recibe una opción por WhatsApp. El horario todavía no está reservado. Se volverá a validar al confirmar.</p>
                        </div>
                        <div>
                            <button type="button" onClick={() => void handleSubmit()} disabled={isSaving} aria-busy={isSaving}
                                className="rounded-full border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-700 disabled:opacity-60">
                                Crear turno directamente
                            </button>
                            <p className="mt-1 text-xs text-slate-500">Crea el turno real inmediatamente.</p>
                        </div>
                        <button type="button" onClick={onClose} disabled={isSaving} className="text-sm text-slate-600 underline">Cancelar</button>
                    </div>
                ) : <div className="flex justify-end gap-3 pt-2">
                    <button
                        type="button"
                        onClick={onClose}
                        className="rounded-full border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900 disabled:opacity-50 disabled:cursor-not-allowed"
                        disabled={isSaving}
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        onClick={() => void handleSubmit()}
                        disabled={isSaving}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                        aria-busy={isSaving}
                    >
                        {isSaving ? 'Guardando...' : 'Guardar'}
                    </button>
                </div>}
            </fieldset>
        </Modal>
    );
}

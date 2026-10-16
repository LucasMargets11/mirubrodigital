"use client";

import { useMemo, useState } from 'react';
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
import type { Appointment } from '@/features/appointments/types';
import { CustomerPicker, type PickedCustomer } from '@/features/customers/components/customer-picker';
import type { Customer } from '@/features/customers/types';
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
}: AppointmentFormModalProps) {
    const today = todayInTimeZone(timeZone);
    const [form, setForm] = useState<FormState>(() => initialForm(editing, defaultDate ?? today, initialCustomer, timeZone));
    // Customer canónico elegido (identidad). Los `customer_*` del form son
    // los snapshots del turno: editarlos nunca modifica el Customer.
    const [pickedCustomer, setPickedCustomer] = useState<PickedCustomer | null>(() => initialPicked(editing, initialCustomer));
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [saveError, setSaveError] = useState('');

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
    const isSaving = createMutation.isPending || updateMutation.isPending;

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
        setForm((prev) => ({ ...prev, service_id: serviceId, professional_id: '', start_at: '' }));
    }

    function handleProfessionalChange(professionalId: string) {
        setForm((prev) => ({ ...prev, professional_id: professionalId, start_at: '' }));
    }

    function handleDateChange(nextDate: string) {
        setForm((prev) => ({ ...prev, date: nextDate, start_at: '' }));
    }

    async function handleSubmit() {
        const parsed = appointmentFormSchema.safeParse(form);
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

        const payload = {
            service_id: parsed.data.service_id,
            professional_id: parsed.data.professional_id || null,
            start_at: parsed.data.start_at,
            // Con Customer elegido el backend lo usa tal cual (sin resolver por teléfono).
            customer_id: canPickCustomer && pickedCustomer ? pickedCustomer.id : undefined,
            customer_name: parsed.data.customer_name.trim(),
            customer_phone: parsed.data.customer_phone.trim(),
            customer_email: parsed.data.customer_email?.trim() || undefined,
            notes: parsed.data.notes?.trim() || undefined,
        };

        try {
            const saved = editing
                ? await updateMutation.mutateAsync({ id: editing.id, payload })
                : await createMutation.mutateAsync(payload);
            onSaved(saved, editing ? 'edit' : 'create');
        } catch (error) {
            if (error instanceof ApiError && error.status === 403) {
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
                } else {
                    setSaveError('No pudimos guardar el turno.');
                }
            } else {
                setSaveError('No pudimos guardar el turno.');
            }
        }
    }

    return (
        <Modal open onClose={onClose} title={editing ? 'Editar turno' : 'Nuevo turno'}>
            <fieldset disabled={isSaving} className="space-y-4">
                <legend className="sr-only">{editing ? 'Formulario para editar turno' : 'Formulario para crear turno'}</legend>

                {editing ? <AppointmentPaymentSection appointment={editing} timeZone={timeZone} /> : null}

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

                <div>
                    <p className="text-sm font-medium text-slate-700">
                        Horario <span className="text-rose-600" aria-hidden="true">*</span>
                    </p>
                    {!form.service_id ? (
                        <p className="mt-1 text-xs text-slate-500">Elegí un servicio para ver los horarios disponibles.</p>
                    ) : availabilityQuery.isLoading ? (
                        <p className="mt-1 text-xs text-slate-500">Buscando horarios disponibles...</p>
                    ) : availableSlots.length === 0 ? (
                        <p className="mt-1 text-xs text-slate-500">No hay horarios disponibles para esta fecha.</p>
                    ) : (
                        <div className="mt-2 flex flex-wrap gap-2">
                            {availableSlots.map((slot) => (
                                <button
                                    key={slot.start}
                                    type="button"
                                    onClick={() => setForm((prev) => ({ ...prev, start_at: slot.start }))}
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

                <label className="block text-sm font-medium text-slate-700">
                    Notas
                    <textarea
                        value={form.notes}
                        onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                        rows={2}
                    />
                </label>

                {saveError ? (
                    <p role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                        {saveError}
                    </p>
                ) : null}

                <div className="flex justify-end gap-3 pt-2">
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
    );
}

"use client";

import { useMemo, useState } from 'react';
import { z } from 'zod';

import { Modal } from '@/components/ui/modal';
import { SortableHeader } from '@/components/ui/sortable-header';
import {
    useAppointmentProfessionals,
    useAppointmentServices,
    useCreateAppointmentProfessional,
    useUpdateAppointmentProfessional,
} from '@/features/appointments/hooks';
import type { AppointmentProfessional } from '@/features/appointments/types';
import { ApiError } from '@/lib/api/client';
import { useTableSort, sortArray, type ColumnConfig } from '@/lib/table/useTableSort';

const professionalFormSchema = z.object({
    name: z.string().min(2, 'El nombre debe tener al menos 2 caracteres').max(150, 'El nombre es muy largo'),
    description: z.string().max(500, 'La descripción es muy larga').optional(),
    phone: z.string().max(30, 'El teléfono es muy largo').optional(),
    email: z.string().max(254, 'El email es muy largo').optional(),
    service_ids: z.array(z.string()),
});

type FormState = z.infer<typeof professionalFormSchema>;

const emptyForm: FormState = {
    name: '',
    description: '',
    phone: '',
    email: '',
    service_ids: [],
};

type ProfessionalsClientProps = {
    canManage: boolean;
};

export function ProfessionalsClient({ canManage }: ProfessionalsClientProps) {
    const [search, setSearch] = useState('');
    const [includeInactive, setIncludeInactive] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [form, setForm] = useState<FormState>(emptyForm);
    const [editing, setEditing] = useState<AppointmentProfessional | null>(null);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [feedback, setFeedback] = useState<string>('');
    const [permissionNotice, setPermissionNotice] = useState<string>('');
    const [confirmAction, setConfirmAction] = useState<{ professional: AppointmentProfessional; action: 'activate' | 'deactivate' } | null>(null);

    const professionalsQuery = useAppointmentProfessionals(search, includeInactive);
    const servicesQuery = useAppointmentServices('', false);
    const createMutation = useCreateAppointmentProfessional();
    const updateMutation = useUpdateAppointmentProfessional();

    const isSaving = createMutation.isPending || updateMutation.isPending;

    const professionals = useMemo(() => professionalsQuery.data ?? [], [professionalsQuery.data]);
    const services = useMemo(() => servicesQuery.data ?? [], [servicesQuery.data]);

    const columnConfigs: Record<string, ColumnConfig<AppointmentProfessional>> = useMemo(() => ({
        name: {
            accessor: 'name',
            sortType: 'string',
        },
        services_count: {
            accessor: (professional) => professional.services.length,
            sortType: 'number',
        },
        is_active: {
            accessor: 'is_active',
            sortType: 'boolean',
        },
    }), []);

    const { sortKey, sortDir, onToggleSort } = useTableSort({
        defaultSortKey: 'name',
        defaultSortDir: 'asc',
        persistInUrl: true,
    });

    const sortedProfessionals = useMemo(() => {
        return sortArray(professionals, sortKey, sortDir, columnConfigs);
    }, [professionals, sortKey, sortDir, columnConfigs]);

    const handleOpenCreate = () => {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para crear profesionales.');
            return;
        }
        setEditing(null);
        setForm({ ...emptyForm });
        setErrors({});
        setFeedback('');
        setModalOpen(true);
    };

    const handleOpenEdit = (professional: AppointmentProfessional) => {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para editar profesionales.');
            return;
        }
        setEditing(professional);
        setForm({
            name: professional.name,
            description: professional.description ?? '',
            phone: professional.phone ?? '',
            email: professional.email ?? '',
            service_ids: professional.services.map((service) => service.id),
        });
        setErrors({});
        setFeedback('');
        setModalOpen(true);
    };

    const handleCloseModal = () => {
        setModalOpen(false);
    };

    const toggleServiceSelection = (serviceId: string) => {
        setForm((prev) => ({
            ...prev,
            service_ids: prev.service_ids.includes(serviceId)
                ? prev.service_ids.filter((id) => id !== serviceId)
                : [...prev.service_ids, serviceId],
        }));
    };

    async function handleSubmit() {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para modificar profesionales.');
            return;
        }
        const parsed = professionalFormSchema.safeParse(form);
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

        const payload = {
            name: parsed.data.name.trim(),
            description: parsed.data.description?.trim() ?? '',
            phone: parsed.data.phone?.trim() ?? '',
            email: parsed.data.email?.trim() ?? '',
            service_ids: parsed.data.service_ids,
        };

        try {
            if (editing) {
                await updateMutation.mutateAsync({ id: editing.id, payload });
                setFeedback('Profesional actualizado.');
            } else {
                await createMutation.mutateAsync(payload);
                setFeedback('Profesional creado.');
            }
            setModalOpen(false);
        } catch (error) {
            if (error instanceof ApiError) {
                if (error.status === 403) {
                    setPermissionNotice('Tu rol no tiene permiso para esta acción.');
                } else if (error.status === 400 && error.payload && typeof error.payload === 'object') {
                    const payload = error.payload as Record<string, unknown>;
                    const fieldErrors: Record<string, string> = {};
                    for (const [field, value] of Object.entries(payload)) {
                        if (Array.isArray(value) && value.length > 0) {
                            fieldErrors[field] = String(value[0]);
                        }
                    }
                    if (Object.keys(fieldErrors).length > 0) {
                        setErrors(fieldErrors);
                    } else {
                        setFeedback('No pudimos guardar los cambios.');
                    }
                } else {
                    setFeedback('No pudimos guardar los cambios.');
                }
            } else {
                setFeedback('No pudimos guardar los cambios.');
            }
        }
    }

    const handleToggleActive = (professional: AppointmentProfessional) => {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para esta acción.');
            return;
        }
        const action = professional.is_active ? 'deactivate' : 'activate';
        setConfirmAction({ professional, action });
    };

    const handleConfirmToggle = async () => {
        if (!confirmAction || !canManage) {
            return;
        }
        const { professional, action } = confirmAction;
        try {
            await updateMutation.mutateAsync({
                id: professional.id,
                payload: { is_active: action === 'activate' },
            });
            setFeedback(`Profesional ${action === 'activate' ? 'activado' : 'desactivado'}.`);
        } catch (error) {
            if (error instanceof ApiError && error.status === 403) {
                setPermissionNotice('Tu rol no tiene permiso para esta acción.');
            } else {
                setFeedback('No pudimos actualizar el estado.');
            }
        } finally {
            setConfirmAction(null);
        }
    };

    const handleCancelConfirm = () => {
        setConfirmAction(null);
    };

    const isLoading = professionalsQuery.isLoading;
    const hasProfessionals = sortedProfessionals.length > 0;
    const hasSearch = search.length > 0;

    return (
        <>
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-4">
                <div className="flex items-center gap-3">
                    <label className="flex items-center gap-2 text-sm text-slate-500">
                        <input
                            type="checkbox"
                            checked={includeInactive}
                            onChange={(event) => setIncludeInactive(event.target.checked)}
                            className="size-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
                        />
                        Mostrar inactivos
                    </label>
                </div>
                {canManage && (
                    <button
                        type="button"
                        onClick={handleOpenCreate}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                        aria-label="Crear nuevo profesional"
                    >
                        Nuevo profesional
                    </button>
                )}
            </div>

            {!canManage && (
                <p className="mb-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                    Tu rol puede consultar los profesionales pero no crear ni editar.
                </p>
            )}

            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-3 mb-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center">
                        <label className="flex-1">
                            <span className="sr-only">Buscar por nombre</span>
                            <input
                                type="search"
                                value={search}
                                onChange={(event) => setSearch(event.target.value)}
                                placeholder="Buscar por nombre"
                                className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                aria-label="Buscar profesionales"
                            />
                        </label>
                        {hasSearch && (
                            <button
                                type="button"
                                onClick={() => setSearch('')}
                                className="text-sm text-slate-600 hover:text-slate-900"
                                aria-label="Limpiar búsqueda"
                            >
                                Limpiar
                            </button>
                        )}
                    </div>
                    <div className="text-right text-sm">
                        {professionalsQuery.isError && <p className="text-rose-600">No pudimos cargar los profesionales.</p>}
                        {feedback && <p className="text-slate-500">{feedback}</p>}
                        {permissionNotice && <p className="text-rose-600">{permissionNotice}</p>}
                    </div>
                </div>

                {isLoading ? (
                    <div className="py-8 text-center text-sm text-slate-500">
                        Cargando profesionales...
                    </div>
                ) : !hasProfessionals && !hasSearch ? (
                    <div className="py-12 text-center">
                        <p className="text-slate-600 mb-2">No tenés profesionales creados todavía.</p>
                        <p className="text-sm text-slate-500 mb-4">
                            Es opcional: sin profesionales, la reserva se hace directamente contra el negocio.
                        </p>
                        {canManage && (
                            <button
                                type="button"
                                onClick={handleOpenCreate}
                                className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                            >
                                Crear primer profesional
                            </button>
                        )}
                    </div>
                ) : !hasProfessionals && hasSearch ? (
                    <div className="py-8 text-center">
                        <p className="text-slate-600 mb-2">No hay resultados para &quot;{search}&quot;.</p>
                        <button
                            type="button"
                            onClick={() => setSearch('')}
                            className="text-sm text-slate-600 hover:text-slate-900 underline"
                        >
                            Limpiar búsqueda
                        </button>
                    </div>
                ) : (
                    <div className="mt-4 overflow-x-auto">
                        <table className="min-w-full divide-y divide-slate-100 text-sm">
                            <thead>
                                <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                    <SortableHeader
                                        label="Profesional"
                                        sortKey="name"
                                        activeSortKey={sortKey}
                                        sortDir={sortDir}
                                        onToggleSort={onToggleSort}
                                    />
                                    <th scope="col" className="px-3 py-2">Contacto</th>
                                    <SortableHeader
                                        label="Servicios"
                                        sortKey="services_count"
                                        activeSortKey={sortKey}
                                        sortDir={sortDir}
                                        onToggleSort={onToggleSort}
                                    />
                                    <SortableHeader
                                        label="Estado"
                                        sortKey="is_active"
                                        activeSortKey={sortKey}
                                        sortDir={sortDir}
                                        onToggleSort={onToggleSort}
                                    />
                                    {canManage ? <th className="px-3 py-2" /> : null}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {sortedProfessionals.map((professional) => (
                                    <tr key={professional.id} className={professional.is_active ? 'text-slate-700' : 'text-slate-700 opacity-50'}>
                                        <td className="px-3 py-3">
                                            <p className="font-medium">{professional.name}</p>
                                            {professional.description && (
                                                <p className="text-xs text-slate-500">{professional.description}</p>
                                            )}
                                        </td>
                                        <td className="px-3 py-3 text-slate-500">
                                            {professional.phone || professional.email ? (
                                                <div className="space-y-0.5">
                                                    {professional.phone && <p>{professional.phone}</p>}
                                                    {professional.email && <p>{professional.email}</p>}
                                                </div>
                                            ) : (
                                                <span className="text-slate-400">Sin datos de contacto</span>
                                            )}
                                        </td>
                                        <td className="px-3 py-3 text-slate-500">
                                            {professional.services.length > 0 ? (
                                                <div className="flex flex-wrap gap-1">
                                                    {professional.services.map((service) => (
                                                        <span
                                                            key={service.id}
                                                            className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-800"
                                                        >
                                                            {service.name}
                                                        </span>
                                                    ))}
                                                </div>
                                            ) : (
                                                <span className="text-slate-400">Sin servicios asignados</span>
                                            )}
                                        </td>
                                        <td className="px-3 py-3">
                                            <span
                                                className={`rounded-full px-3 py-1 text-xs font-semibold ${professional.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'
                                                    }`}
                                            >
                                                {professional.is_active ? 'Activo' : 'Inactivo'}
                                            </span>
                                        </td>
                                        {canManage ? (
                                            <td className="px-3 py-3">
                                                <div className="flex gap-2 text-xs font-semibold">
                                                    <button
                                                        type="button"
                                                        onClick={() => handleOpenEdit(professional)}
                                                        className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 hover:border-slate-900 hover:text-slate-900"
                                                        aria-label={`Editar profesional ${professional.name}`}
                                                    >
                                                        Editar
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={() => handleToggleActive(professional)}
                                                        className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 hover:border-slate-900 hover:text-slate-900"
                                                        aria-label={`${professional.is_active ? 'Desactivar' : 'Activar'} profesional ${professional.name}`}
                                                    >
                                                        {professional.is_active ? 'Desactivar' : 'Activar'}
                                                    </button>
                                                </div>
                                            </td>
                                        ) : null}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            <Modal open={modalOpen} onClose={handleCloseModal} title={editing ? 'Editar profesional' : 'Nuevo profesional'}>
                <fieldset disabled={isSaving} className="space-y-4">
                    <legend className="sr-only">
                        {editing ? 'Formulario para editar profesional' : 'Formulario para crear profesional'}
                    </legend>
                    <label className="block text-sm font-medium text-slate-700">
                        Nombre <span className="text-rose-600" aria-hidden="true">*</span>
                        <span className="sr-only">Campo obligatorio</span>
                        <input
                            type="text"
                            value={form.name}
                            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                            required
                            aria-required="true"
                        />
                        {errors.name && <span className="mt-1 block text-xs text-rose-600" role="alert">{errors.name}</span>}
                    </label>

                    <label className="block text-sm font-medium text-slate-700">
                        Descripción
                        <textarea
                            value={form.description}
                            onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                            rows={2}
                        />
                        {errors.description && <span className="text-xs text-rose-600">{errors.description}</span>}
                    </label>

                    <div className="grid gap-4 md:grid-cols-2">
                        <label className="text-sm font-medium text-slate-700">
                            Teléfono
                            <input
                                type="text"
                                value={form.phone}
                                onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                            />
                            {errors.phone && <span className="text-xs text-rose-600">{errors.phone}</span>}
                        </label>
                        <label className="text-sm font-medium text-slate-700">
                            Email
                            <input
                                type="email"
                                value={form.email}
                                onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                            />
                            {errors.email && <span className="text-xs text-rose-600">{errors.email}</span>}
                        </label>
                    </div>

                    <div>
                        <p className="text-sm font-medium text-slate-700">Servicios que realiza</p>
                        {services.length === 0 ? (
                            <p className="mt-1 text-xs text-slate-500">Todavía no tenés servicios cargados en Turnos.</p>
                        ) : (
                            <div className="mt-2 max-h-48 space-y-1 overflow-y-auto rounded-xl border border-slate-200 p-2">
                                {services.map((service) => (
                                    <label key={service.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-50">
                                        <input
                                            type="checkbox"
                                            checked={form.service_ids.includes(service.id)}
                                            onChange={() => toggleServiceSelection(service.id)}
                                            className="size-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
                                        />
                                        {service.name}
                                    </label>
                                ))}
                            </div>
                        )}
                        {errors.service_ids && <span className="text-xs text-rose-600">{errors.service_ids}</span>}
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={handleCloseModal}
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

            <Modal
                open={!!confirmAction}
                onClose={handleCancelConfirm}
                title={confirmAction?.action === 'deactivate' ? 'Desactivar profesional' : 'Activar profesional'}
            >
                <p className="text-sm text-slate-600 mb-4">
                    {confirmAction?.action === 'deactivate' ? (
                        <>¿Estás seguro de desactivar a &quot;{confirmAction.professional.name}&quot;?</>
                    ) : (
                        <>¿Querés activar a &quot;{confirmAction?.professional.name}&quot;?</>
                    )}
                </p>
                <div className="flex justify-end gap-3">
                    <button
                        type="button"
                        onClick={handleCancelConfirm}
                        className="rounded-full border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        onClick={handleConfirmToggle}
                        disabled={updateMutation.isPending}
                        className={`rounded-full px-5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60 ${
                            confirmAction?.action === 'deactivate'
                                ? 'bg-rose-600 hover:bg-rose-700'
                                : 'bg-emerald-600 hover:bg-emerald-700'
                        }`}
                    >
                        {updateMutation.isPending ? 'Procesando...' : confirmAction?.action === 'deactivate' ? 'Desactivar' : 'Activar'}
                    </button>
                </div>
            </Modal>
        </>
    );
}

"use client";

import Link from 'next/link';
import { useDeferredValue, useMemo, useState } from 'react';
import { z } from 'zod';

import { Modal } from '@/components/ui/modal';
import { SortableHeader } from '@/components/ui/sortable-header';
import { useAppointmentCategories } from '@/features/appointments/hooks';
import { useCreateAppointmentService, useAppointmentServices, useUpdateAppointmentService } from '@/features/appointments/hooks';
import type { AppointmentService, DepositType } from '@/features/appointments/types';
import { ApiError } from '@/lib/api/client';
import { useTableSort, sortArray, type ColumnConfig } from '@/lib/table/useTableSort';

const serviceFormSchema = z.object({
    category_id: z.string().optional().nullable(),
    name: z.string().min(2, 'El nombre es obligatorio'),
    description: z.string().optional(),
    duration_minutes: z.string().min(1, 'Ingresá una duración'),
    price: z.string().min(1, 'Ingresá un precio'),
    deposit_type: z.enum(['none', 'fixed', 'percentage']),
    deposit_value: z.string().optional(),
});

type FormState = z.infer<typeof serviceFormSchema>;

const emptyForm: FormState = {
    category_id: null,
    name: '',
    description: '',
    duration_minutes: '',
    price: '',
    deposit_type: 'none',
    deposit_value: '',
};

function formatCurrency(value: string) {
    const numeric = Number(value);
    if (Number.isNaN(numeric)) {
        return '$0';
    }
    return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(numeric);
}

function formatDuration(minutes: number) {
    if (minutes < 60) {
        return `${minutes} min`;
    }
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

function formatDeposit(service: AppointmentService) {
    if (service.deposit_type === 'none') {
        return 'Sin seña';
    }
    if (service.deposit_type === 'fixed') {
        return `${formatCurrency(service.deposit_value)} fijo`;
    }
    return `${Number(service.deposit_value)}%`;
}

type ServicesClientProps = {
    canManage: boolean;
};

export function ServicesClient({ canManage }: ServicesClientProps) {
    const [search, setSearch] = useState('');
    const deferredSearch = useDeferredValue(search);
    const [includeInactive, setIncludeInactive] = useState(false);
    const [categoryFilter, setCategoryFilter] = useState<string | null | undefined>(undefined);
    const [modalOpen, setModalOpen] = useState(false);
    const [form, setForm] = useState<FormState>(emptyForm);
    const [editing, setEditing] = useState<AppointmentService | null>(null);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [feedback, setFeedback] = useState<string>('');
    const [permissionNotice, setPermissionNotice] = useState<string>('');

    const servicesQuery = useAppointmentServices(deferredSearch, includeInactive, categoryFilter);
    const categoriesQuery = useAppointmentCategories('');
    const createMutation = useCreateAppointmentService();
    const updateMutation = useUpdateAppointmentService();

    const isSaving = createMutation.isPending || updateMutation.isPending;

    const services = useMemo(() => servicesQuery.data ?? [], [servicesQuery.data]);
    const categories = useMemo(() => categoriesQuery.data ?? [], [categoriesQuery.data]);

    const columnConfigs: Record<string, ColumnConfig<AppointmentService>> = useMemo(() => ({
        name: {
            accessor: 'name',
            sortType: 'string',
        },
        category: {
            accessor: (service) => service.category?.name ?? '',
            sortType: 'string',
        },
        duration_minutes: {
            accessor: 'duration_minutes',
            sortType: 'number',
        },
        price: {
            accessor: 'price',
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

    const sortedServices = useMemo(() => {
        return sortArray(services, sortKey, sortDir, columnConfigs);
    }, [services, sortKey, sortDir, columnConfigs]);

    const handleOpenCreate = () => {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para crear servicios.');
            return;
        }
        setEditing(null);
        setForm({ ...emptyForm });
        setErrors({});
        setFeedback('');
        setModalOpen(true);
    };

    const handleOpenEdit = (service: AppointmentService) => {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para editar servicios.');
            return;
        }
        setEditing(service);
        setForm({
            category_id: service.category?.id ?? null,
            name: service.name,
            description: service.description ?? '',
            duration_minutes: String(service.duration_minutes),
            price: service.price,
            deposit_type: service.deposit_type,
            deposit_value: service.deposit_value,
        });
        setErrors({});
        setFeedback('');
        setModalOpen(true);
    };

    const handleCloseModal = () => {
        setModalOpen(false);
    };

    async function handleSubmit() {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para modificar servicios.');
            return;
        }
        const parsed = serviceFormSchema.safeParse(form);
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
            category_id: parsed.data.category_id || null,
            name: parsed.data.name,
            description: parsed.data.description || undefined,
            duration_minutes: Number(parsed.data.duration_minutes),
            price: Number(parsed.data.price),
            deposit_type: parsed.data.deposit_type,
            deposit_value: parsed.data.deposit_type === 'none' ? 0 : Number(parsed.data.deposit_value || 0),
        };

        try {
            if (editing) {
                await updateMutation.mutateAsync({ id: editing.id, payload });
                setFeedback('Servicio actualizado.');
            } else {
                await createMutation.mutateAsync(payload);
                setFeedback('Servicio creado.');
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

    async function handleToggleActive(service: AppointmentService) {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para esta acción.');
            return;
        }
        try {
            await updateMutation.mutateAsync({ id: service.id, payload: { is_active: !service.is_active } });
        } catch (error) {
            if (error instanceof ApiError && error.status === 403) {
                setPermissionNotice('Tu rol no tiene permiso para esta acción.');
            } else {
                setFeedback('No pudimos actualizar el estado.');
            }
        }
    }

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
                    >
                        Nuevo servicio
                    </button>
                )}
            </div>
            {!canManage && (
                <p className="mb-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                    Tu rol puede consultar los servicios pero no crear ni editar.
                </p>
            )}
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-3 mb-4">
                    <div className="flex flex-col gap-3 md:flex-row md:items-center">
                        <input
                            type="search"
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder="Buscar por nombre"
                            className="flex-1 rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                        <div className="flex gap-2">
                            <select
                                value={categoryFilter ?? ''}
                                onChange={(e) => {
                                    const val = e.target.value;
                                    setCategoryFilter(val === '' ? undefined : val === 'null' ? null : val);
                                }}
                                className="rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                aria-label="Filtrar por categoría"
                            >
                                <option value="">Todas las categorías</option>
                                <option value="null">Sin categoría</option>
                                {categories.map((cat) => (
                                    <option key={cat.id} value={cat.id}>
                                        {cat.name}
                                    </option>
                                ))}
                            </select>
                            <Link
                                href="/app/turnos/servicios/categorias"
                                className="rounded-xl border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:border-slate-900 hover:text-slate-900 flex items-center whitespace-nowrap"
                                title="Administrar categorías"
                            >
                                Administrar
                            </Link>
                        </div>
                    </div>
                    <div className="text-right text-sm">
                        {servicesQuery.isError && <p className="text-rose-600">No pudimos cargar los servicios.</p>}
                        {feedback && <p className="text-slate-500">{feedback}</p>}
                        {permissionNotice && <p className="text-rose-600">{permissionNotice}</p>}
                    </div>
                </div>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <SortableHeader
                                    label="Servicio"
                                    sortKey="name"
                                    activeSortKey={sortKey}
                                    sortDir={sortDir}
                                    onToggleSort={onToggleSort}
                                />
                                <SortableHeader
                                    label="Categoría"
                                    sortKey="category"
                                    activeSortKey={sortKey}
                                    sortDir={sortDir}
                                    onToggleSort={onToggleSort}
                                />
                                <SortableHeader
                                    label="Duración"
                                    sortKey="duration_minutes"
                                    activeSortKey={sortKey}
                                    sortDir={sortDir}
                                    onToggleSort={onToggleSort}
                                />
                                <SortableHeader
                                    label="Precio"
                                    sortKey="price"
                                    activeSortKey={sortKey}
                                    sortDir={sortDir}
                                    onToggleSort={onToggleSort}
                                />
                                <th scope="col" className="px-3 py-2">Seña</th>
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
                            {servicesQuery.isLoading && (
                                <tr>
                                    <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                        Cargando servicios...
                                    </td>
                                </tr>
                            )}
                            {!servicesQuery.isLoading && sortedServices.length === 0 && (
                                <tr>
                                    <td colSpan={7} className="px-3 py-6 text-center text-slate-500">
                                        {categoryFilter !== undefined
                                            ? 'No hay servicios en esta categoría.'
                                            : 'No encontramos servicios.'}
                                    </td>
                                </tr>
                            )}
                            {sortedServices.map((service) => (
                                <tr key={service.id} className="text-slate-700">
                                    <td className="px-3 py-3">
                                        <p className="font-medium">{service.name}</p>
                                    </td>
                                    <td className="px-3 py-3 text-slate-500">
                                        {service.category ? (
                                            <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-800">
                                                {service.category.name}
                                            </span>
                                        ) : (
                                            <span className="text-slate-400">Sin categoría</span>
                                        )}
                                    </td>
                                    <td className="px-3 py-3">{formatDuration(service.duration_minutes)}</td>
                                    <td className="px-3 py-3">{formatCurrency(service.price)}</td>
                                    <td className="px-3 py-3 text-slate-500">{formatDeposit(service)}</td>
                                    <td className="px-3 py-3">
                                        <span
                                            className={`rounded-full px-3 py-1 text-xs font-semibold ${service.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'
                                                }`}
                                        >
                                            {service.is_active ? 'Activo' : 'Inactivo'}
                                        </span>
                                    </td>
                                    {canManage ? (
                                        <td className="px-3 py-3">
                                            <div className="flex gap-2 text-xs font-semibold">
                                                <button
                                                    type="button"
                                                    onClick={() => handleOpenEdit(service)}
                                                    className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 hover:border-slate-900 hover:text-slate-900"
                                                >
                                                    Editar
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => handleToggleActive(service)}
                                                    className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 hover:border-slate-900 hover:text-slate-900"
                                                >
                                                    {service.is_active ? 'Desactivar' : 'Activar'}
                                                </button>
                                            </div>
                                        </td>
                                    ) : null}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
            <Modal open={modalOpen} onClose={handleCloseModal} title={editing ? 'Editar servicio' : 'Nuevo servicio'}>
                <div className="mb-4">
                    <label className="text-sm font-medium text-slate-700">
                        Categoría
                        <select
                            value={form.category_id ?? ''}
                            onChange={(event) => setForm((prev) => ({ ...prev, category_id: event.target.value || null }))}
                            disabled={isSaving}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50"
                        >
                            <option value="">Sin categoría</option>
                            {categories.map((cat) => (
                                <option key={cat.id} value={cat.id}>
                                    {cat.name}
                                </option>
                            ))}
                        </select>
                        {errors.category_id && <span className="text-xs text-rose-600">{errors.category_id}</span>}
                    </label>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                    <label className="text-sm font-medium text-slate-700">
                        Nombre <span className="text-rose-600" aria-hidden="true">*</span>
                        <span className="sr-only">Campo obligatorio</span>
                        <input
                            type="text"
                            value={form.name}
                            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            required
                            aria-required="true"
                        />
                        {errors.name && <span className="text-xs text-rose-600">{errors.name}</span>}
                    </label>
                    <label className="text-sm font-medium text-slate-700">
                        Duración (minutos) <span className="text-rose-600" aria-hidden="true">*</span>
                        <span className="sr-only">Campo obligatorio</span>
                        <input
                            type="number"
                            min="1"
                            step="1"
                            value={form.duration_minutes}
                            onChange={(event) => setForm((prev) => ({ ...prev, duration_minutes: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            required
                            aria-required="true"
                        />
                        {errors.duration_minutes && <span className="text-xs text-rose-600">{errors.duration_minutes}</span>}
                    </label>
                </div>
                <div className="mt-4">
                    <label className="text-sm font-medium text-slate-700">
                        Descripción
                        <textarea
                            value={form.description}
                            onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            rows={2}
                        />
                    </label>
                </div>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                    <label className="text-sm font-medium text-slate-700">
                        Precio <span className="text-rose-600" aria-hidden="true">*</span>
                        <span className="sr-only">Campo obligatorio</span>
                        <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={form.price}
                            onChange={(event) => setForm((prev) => ({ ...prev, price: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            required
                            aria-required="true"
                        />
                        {errors.price && <span className="text-xs text-rose-600">{errors.price}</span>}
                    </label>
                    <label className="text-sm font-medium text-slate-700">
                        Tipo de seña
                        <select
                            value={form.deposit_type}
                            onChange={(event) => setForm((prev) => ({ ...prev, deposit_type: event.target.value as DepositType }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        >
                            <option value="none">Sin seña</option>
                            <option value="fixed">Monto fijo</option>
                            <option value="percentage">Porcentaje</option>
                        </select>
                    </label>
                </div>
                {form.deposit_type !== 'none' && (
                    <div className="mt-4">
                        <label className="text-sm font-medium text-slate-700">
                            {form.deposit_type === 'fixed' ? 'Monto de la seña' : 'Porcentaje de seña'}
                            <span className="text-rose-600" aria-hidden="true"> *</span>
                            <span className="sr-only">Campo obligatorio</span>
                            <input
                                type="number"
                                min="0"
                                max={form.deposit_type === 'percentage' ? 100 : undefined}
                                step="0.01"
                                value={form.deposit_value}
                                onChange={(event) => setForm((prev) => ({ ...prev, deposit_value: event.target.value }))}
                                className="mt-1 w-full max-w-xs rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                required
                                aria-required="true"
                            />
                            {errors.deposit_value && <span className="block text-xs text-rose-600">{errors.deposit_value}</span>}
                        </label>
                    </div>
                )}
                <div className="flex justify-end gap-3 pt-4">
                    <button
                        type="button"
                        onClick={handleCloseModal}
                        className="rounded-full border border-slate-300 px-5 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        onClick={handleSubmit}
                        disabled={isSaving}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {isSaving ? 'Guardando...' : 'Guardar'}
                    </button>
                </div>
            </Modal>
        </>
    );
}

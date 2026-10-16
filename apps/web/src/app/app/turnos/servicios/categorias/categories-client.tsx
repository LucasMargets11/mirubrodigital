"use client";

import { useMemo, useState } from 'react';
import { z } from 'zod';

import { Modal } from '@/components/ui/modal';
import { SortableHeader } from '@/components/ui/sortable-header';
import {
    useAppointmentCategories,
    useCreateAppointmentCategory,
    useUpdateAppointmentCategory,
} from '@/features/appointments/hooks';
import type { AppointmentCategory } from '@/features/appointments/types';
import { ApiError } from '@/lib/api/client';
import { useTableSort, sortArray, type ColumnConfig } from '@/lib/table/useTableSort';

const categoryFormSchema = z.object({
    name: z.string().min(2, 'El nombre debe tener al menos 2 caracteres').max(100, 'El nombre es muy largo'),
    description: z.string().max(255, 'La descripción es muy larga').optional(),
});

type FormState = z.infer<typeof categoryFormSchema>;

const emptyForm: FormState = {
    name: '',
    description: '',
};

type AppointmentCategoriesClientProps = {
    canManage: boolean;
};

export function AppointmentCategoriesClient({ canManage }: AppointmentCategoriesClientProps) {
    const [search, setSearch] = useState('');
    const [includeInactive, setIncludeInactive] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [form, setForm] = useState<FormState>(emptyForm);
    const [editing, setEditing] = useState<AppointmentCategory | null>(null);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [feedback, setFeedback] = useState<string>('');
    const [permissionNotice, setPermissionNotice] = useState<string>('');
    const [confirmAction, setConfirmAction] = useState<{ category: AppointmentCategory; action: 'activate' | 'deactivate' } | null>(null);

    const categoriesQuery = useAppointmentCategories(search, includeInactive);
    const createMutation = useCreateAppointmentCategory();
    const updateMutation = useUpdateAppointmentCategory();

    const isSaving = createMutation.isPending || updateMutation.isPending;

    const categories = useMemo(() => categoriesQuery.data ?? [], [categoriesQuery.data]);

    const columnConfigs: Record<string, ColumnConfig<AppointmentCategory>> = useMemo(() => ({
        name: {
            accessor: 'name',
            sortType: 'string',
        },
        services_count: {
            accessor: 'services_count',
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

    const sortedCategories = useMemo(() => {
        return sortArray(categories, sortKey, sortDir, columnConfigs);
    }, [categories, sortKey, sortDir, columnConfigs]);

    const handleOpenCreate = () => {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para crear categorías.');
            return;
        }
        setEditing(null);
        setForm({ ...emptyForm });
        setErrors({});
        setFeedback('');
        setModalOpen(true);
    };

    const handleOpenEdit = (category: AppointmentCategory) => {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para editar categorías.');
            return;
        }
        setEditing(category);
        setForm({
            name: category.name,
            description: category.description ?? '',
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
            setPermissionNotice('Tu rol no tiene permiso para modificar categorías.');
            return;
        }
        const parsed = categoryFormSchema.safeParse(form);
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
        };

        try {
            if (editing) {
                await updateMutation.mutateAsync({ id: editing.id, payload });
                setFeedback('Categoría actualizada.');
            } else {
                await createMutation.mutateAsync(payload);
                setFeedback('Categoría creada.');
            }
            setModalOpen(false);
        } catch (error) {
            if (error instanceof ApiError) {
                if (error.status === 403) {
                    setPermissionNotice('Tu rol no tiene permiso para esta acción.');
                } else if (error.status === 400 && error.payload && typeof error.payload === 'object' && 'name' in error.payload) {
                    const nameError = (error.payload as Record<string, unknown>).name;
                    if (Array.isArray(nameError) && nameError.length > 0) {
                        setErrors({ name: String(nameError[0]) });
                    } else {
                        setErrors({ name: 'Ya existe una categoría con este nombre.' });
                    }
                } else {
                    setFeedback('No pudimos guardar los cambios.');
                }
            } else {
                setFeedback('No pudimos guardar los cambios.');
            }
        }
    }

    const handleToggleActive = (category: AppointmentCategory) => {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para esta acción.');
            return;
        }
        const action = category.is_active ? 'deactivate' : 'activate';
        setConfirmAction({ category, action });
    };

    const handleConfirmToggle = async () => {
        if (!confirmAction || !canManage) {
            return;
        }
        const { category, action } = confirmAction;
        try {
            await updateMutation.mutateAsync({
                id: category.id,
                payload: { is_active: action === 'activate' },
            });
            setFeedback(`Categoría ${action === 'activate' ? 'activada' : 'desactivada'}.`);
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

    const isLoading = categoriesQuery.isLoading;
    const hasCategories = sortedCategories.length > 0;
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
                        Mostrar inactivas
                    </label>
                </div>
                {canManage && (
                    <button
                        type="button"
                        onClick={handleOpenCreate}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                        aria-label="Crear nueva categoría"
                    >
                        Nueva categoría
                    </button>
                )}
            </div>

            {!canManage && (
                <p className="mb-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                    Tu rol puede consultar las categorías pero no crear ni editar.
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
                                aria-label="Buscar categorías"
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
                        {categoriesQuery.isError && <p className="text-rose-600">No pudimos cargar las categorías.</p>}
                        {feedback && <p className="text-slate-500">{feedback}</p>}
                        {permissionNotice && <p className="text-rose-600">{permissionNotice}</p>}
                    </div>
                </div>

                {isLoading ? (
                    <div className="py-8 text-center text-sm text-slate-500">
                        Cargando categorías...
                    </div>
                ) : !hasCategories && !hasSearch ? (
                    <div className="py-12 text-center">
                        <p className="text-slate-600 mb-4">No tenés categorías creadas todavía.</p>
                        {canManage && (
                            <button
                                type="button"
                                onClick={handleOpenCreate}
                                className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                            >
                                Crear primera categoría
                            </button>
                        )}
                    </div>
                ) : !hasCategories && hasSearch ? (
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
                                        label="Categoría"
                                        sortKey="name"
                                        activeSortKey={sortKey}
                                        sortDir={sortDir}
                                        onToggleSort={onToggleSort}
                                    />
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
                                    <th scope="col" className="px-4 py-3">
                                        Acciones
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {sortedCategories.map((category) => (
                                    <tr key={category.id} className={category.is_active ? '' : 'opacity-50'}>
                                        <td className="px-4 py-3 font-medium text-slate-900">
                                            {category.name}
                                        </td>
                                        <td className="px-4 py-3 text-slate-600">
                                            {category.services_count}
                                        </td>
                                        <td className="px-4 py-3">
                                            <span
                                                className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${
                                                    category.is_active
                                                        ? 'bg-emerald-100 text-emerald-700'
                                                        : 'bg-slate-100 text-slate-600'
                                                }`}
                                            >
                                                {category.is_active ? 'Activa' : 'Inactiva'}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-2">
                                                <button
                                                    type="button"
                                                    onClick={() => handleOpenEdit(category)}
                                                    className="text-slate-600 hover:text-slate-900 text-sm font-medium"
                                                    aria-label={`Editar categoría ${category.name}`}
                                                >
                                                    Editar
                                                </button>
                                                <span className="text-slate-300">|</span>
                                                <button
                                                    type="button"
                                                    onClick={() => handleToggleActive(category)}
                                                    className={`text-sm font-medium ${
                                                        category.is_active
                                                            ? 'text-rose-600 hover:text-rose-700'
                                                            : 'text-emerald-600 hover:text-emerald-700'
                                                    }`}
                                                    aria-label={`${category.is_active ? 'Desactivar' : 'Activar'} categoría ${category.name}`}
                                                >
                                                    {category.is_active ? 'Desactivar' : 'Activar'}
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            <Modal
                open={modalOpen}
                onClose={handleCloseModal}
                title={editing ? 'Editar categoría' : 'Nueva categoría'}
            >
                <fieldset disabled={isSaving}>
                    <legend className="sr-only">
                        {editing ? 'Formulario para editar categoría' : 'Formulario para crear categoría'}
                    </legend>
                    <p className="text-sm text-slate-500 mb-4">
                        Se usa para agrupar servicios reservables en Turnos.
                    </p>
                    <label className="block text-sm font-medium text-slate-700">
                        Nombre de categoría{' '}
                        <span className="text-rose-600" aria-hidden="true">
                            *
                        </span>
                        <span className="sr-only">Campo obligatorio</span>
                        <input
                            type="text"
                            value={form.name}
                            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50 disabled:cursor-not-allowed"
                            required
                            aria-required="true"
                            aria-invalid={!!errors.name}
                            aria-describedby={errors.name ? 'name-error' : undefined}
                            maxLength={100}
                        />
                        {errors.name && (
                            <span id="name-error" className="mt-1 block text-xs text-rose-600" role="alert">
                                {errors.name}
                            </span>
                        )}
                    </label>
                    <label className="mt-4 block text-sm font-medium text-slate-700">
                        Descripción
                        <textarea
                            value={form.description}
                            onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none disabled:bg-slate-50 disabled:cursor-not-allowed"
                            rows={2}
                            maxLength={255}
                        />
                        {errors.description && <span className="text-xs text-rose-600">{errors.description}</span>}
                    </label>
                    <div className="flex justify-end gap-3 pt-4">
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
                title={confirmAction?.action === 'deactivate' ? 'Desactivar categoría' : 'Activar categoría'}
            >
                <p className="text-sm text-slate-600 mb-4">
                    {confirmAction?.action === 'deactivate' ? (
                        <>
                            ¿Estás seguro de desactivar &quot;{confirmAction.category.name}&quot;?
                            <br />
                            <br />
                            La categoría no aparecerá en los filtros pero los servicios mantendrán la asignación.
                        </>
                    ) : (
                        <>
                            ¿Querés activar &quot;{confirmAction?.category.name}&quot;?
                            <br />
                            <br />
                            La categoría volverá a aparecer en los filtros.
                        </>
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

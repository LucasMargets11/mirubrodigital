"use client";

import { ChangeEvent, useMemo, useRef, useState } from 'react';

import { Modal } from '@/components/ui/modal';
import {
    useCreateMenuCategory,
    useCreateMenuItem,
    useDeleteMenuCategory,
    useDeleteMenuItem,
    useExportMenu,
    useImportMenu,
    useMenuCategories,
    useMenuItems,
    useMenuStructure,
    useUpdateMenuCategory,
    useUpdateMenuItem,
} from '@/features/menu/hooks';
import type { MenuCategory, MenuImportResult, MenuItem } from '@/features/menu/types';

const pesosFormatter = new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'ARS',
    maximumFractionDigits: 2,
});

const availabilityFilters = [
    { id: 'all', label: 'Todo' },
    { id: 'available', label: 'Solo disponibles' },
    { id: 'unavailable', label: 'Pausados' },
] as const;

type AvailabilityFilter = (typeof availabilityFilters)[number]['id'];

type CategoryFormState = {
    id: string | null;
    name: string;
    description: string;
    position: string;
    is_active: boolean;
};

type ItemFormState = {
    id: string | null;
    category_id: string | null;
    name: string;
    description: string;
    price: string;
    sku: string;
    tags: string;
    is_available: boolean;
    is_featured: boolean;
    position: string;
    estimated_time_minutes: string;
};

type MenuClientProps = {
    canManage: boolean;
    canImport: boolean;
    canExport: boolean;
};

const emptyCategoryForm: CategoryFormState = {
    id: null,
    name: '',
    description: '',
    position: '',
    is_active: true,
};

const emptyItemForm: ItemFormState = {
    id: null,
    category_id: null,
    name: '',
    description: '',
    price: '',
    sku: '',
    tags: '',
    is_available: true,
    is_featured: false,
    position: '',
    estimated_time_minutes: '',
};

function formatCurrency(value: string | number | undefined) {
    if (value === undefined || value === null) {
        return '—';
    }
    const numeric = typeof value === 'string' ? Number(value) : value;
    if (Number.isNaN(numeric)) {
        return '—';
    }
    return pesosFormatter.format(numeric);
}

export function MenuClient({ canManage, canImport, canExport }: MenuClientProps) {
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
    const [search, setSearch] = useState('');
    const [availability, setAvailability] = useState<AvailabilityFilter>('all');
    const [categoryModalOpen, setCategoryModalOpen] = useState(false);
    const [itemModalOpen, setItemModalOpen] = useState(false);
    const [categoryForm, setCategoryForm] = useState<CategoryFormState>(emptyCategoryForm);
    const [itemForm, setItemForm] = useState<ItemFormState>(emptyItemForm);
    const [categoryFormError, setCategoryFormError] = useState<string | null>(null);
    const [itemFormError, setItemFormError] = useState<string | null>(null);
    const [importResult, setImportResult] = useState<MenuImportResult | null>(null);
    const [importError, setImportError] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement | null>(null);

    const categoryQuery = useMenuCategories();
    const categories = categoryQuery.data ?? [];

    const itemFilters = useMemo(() => {
        return {
            category: selectedCategory,
            available: availability === 'available' ? 'true' : availability === 'unavailable' ? 'false' : undefined,
            search: search.trim() || undefined,
        };
    }, [selectedCategory, availability, search]);

    const itemsQuery = useMenuItems(itemFilters);
    const items = itemsQuery.data ?? [];

    const structureQuery = useMenuStructure();

    const createCategory = useCreateMenuCategory();
    const updateCategory = useUpdateMenuCategory();
    const deleteCategory = useDeleteMenuCategory();
    const createItem = useCreateMenuItem();
    const updateItem = useUpdateMenuItem();
    const deleteItem = useDeleteMenuItem();
    const importMenu = useImportMenu();
    const exportMenu = useExportMenu();

    const hasCategories = categories.length > 0;

    const handleSelectCategory = (categoryId: string | null) => {
        setSelectedCategory((current) => (current === categoryId ? null : categoryId));
    };

    const handleOpenCategoryModal = (category?: MenuCategory) => {
        if (!canManage) {
            return;
        }
        if (category) {
            setCategoryForm({
                id: category.id,
                name: category.name,
                description: category.description ?? '',
                position: category.position ? String(category.position) : '',
                is_active: category.is_active,
            });
        } else {
            setCategoryForm({
                ...emptyCategoryForm,
                position: String(categories.length + 1),
            });
        }
        setCategoryFormError(null);
        setCategoryModalOpen(true);
    };

    const handleCloseCategoryModal = () => {
        setCategoryModalOpen(false);
        setCategoryForm(emptyCategoryForm);
    };

    const handleCategorySubmit = async () => {
        if (!canManage) {
            return;
        }
        const name = categoryForm.name.trim();
        if (!name) {
            setCategoryFormError('El nombre es obligatorio.');
            return;
        }

        const payload = {
            name,
            description: categoryForm.description.trim() || undefined,
            position: categoryForm.position ? Number(categoryForm.position) : undefined,
            is_active: categoryForm.is_active,
        };

        try {
            if (categoryForm.id) {
                await updateCategory.mutateAsync({ id: categoryForm.id, payload });
            } else {
                await createCategory.mutateAsync(payload);
            }
            setCategoryFormError(null);
            handleCloseCategoryModal();
        } catch (error) {
            setCategoryFormError('No pudimos guardar la categoría. Intentalo nuevamente.');
        }
    };

    const handleDeleteCategory = async (category: MenuCategory) => {
        if (!canManage) {
            return;
        }
        const message = `Vas a eliminar "${category.name}" y sus productos quedarán sin categoría. ¿Continuar?`;
        if (!window.confirm(message)) {
            return;
        }
        try {
            await deleteCategory.mutateAsync(category.id);
            if (selectedCategory === category.id) {
                setSelectedCategory(null);
            }
        } catch (error) {
            window.alert('No pudimos eliminar la categoría.');
        }
    };

    const handleOpenItemModal = (item?: MenuItem) => {
        if (!canManage) {
            return;
        }
        if (item) {
            setItemForm({
                id: item.id,
                category_id: item.category_id,
                name: item.name,
                description: item.description ?? '',
                price: item.price ?? '',
                sku: item.sku ?? '',
                tags: (item.tags ?? []).join(', '),
                is_available: item.is_available,
                is_featured: item.is_featured,
                position: item.position ? String(item.position) : '',
                estimated_time_minutes: item.estimated_time_minutes ? String(item.estimated_time_minutes) : '',
            });
        } else {
            setItemForm({
                ...emptyItemForm,
                category_id: selectedCategory,
                position: String(items.length + 1),
            });
        }
        setItemFormError(null);
        setItemModalOpen(true);
    };

    const handleCloseItemModal = () => {
        setItemModalOpen(false);
        setItemForm(emptyItemForm);
    };

    const resolveItemPayload = () => {
        const name = itemForm.name.trim();
        if (!name) {
            setItemFormError('El nombre es obligatorio.');
            return null;
        }
        const priceValue = itemForm.price.trim();
        if (priceValue && Number.isNaN(Number(priceValue))) {
            setItemFormError('El precio debe ser un número.');
            return null;
        }
        const tags = itemForm.tags
            .split(',')
            .map((tag) => tag.trim())
            .filter((tag, index, array) => tag && array.indexOf(tag) === index);

        return {
            category_id: itemForm.category_id || null,
            name,
            description: itemForm.description.trim() || undefined,
            price: priceValue ? Number(priceValue) : undefined,
            sku: itemForm.sku.trim() || undefined,
            tags,
            is_available: itemForm.is_available,
            is_featured: itemForm.is_featured,
            position: itemForm.position ? Number(itemForm.position) : undefined,
            estimated_time_minutes: itemForm.estimated_time_minutes ? Number(itemForm.estimated_time_minutes) : undefined,
        };
    };

    const handleItemSubmit = async () => {
        if (!canManage) {
            return;
        }
        const payload = resolveItemPayload();
        if (!payload) {
            return;
        }
        try {
            if (itemForm.id) {
                await updateItem.mutateAsync({ id: itemForm.id, payload });
            } else {
                await createItem.mutateAsync(payload);
            }
            setItemFormError(null);
            handleCloseItemModal();
        } catch (error) {
            setItemFormError('No pudimos guardar el producto.');
        }
    };

    const handleDeleteItem = async (item: MenuItem) => {
        if (!canManage) {
            return;
        }
        if (!window.confirm(`¿Eliminar "${item.name}" de la carta?`)) {
            return;
        }
        try {
            await deleteItem.mutateAsync(item.id);
        } catch (error) {
            window.alert('No pudimos eliminar el producto.');
        }
    };

    const handleToggleAvailability = async (item: MenuItem, nextValue: boolean) => {
        if (!canManage) {
            return;
        }
        try {
            await updateItem.mutateAsync({ id: item.id, payload: { is_available: nextValue } });
        } catch (error) {
            window.alert('No pudimos actualizar la disponibilidad.');
        }
    };

    const handleImportClick = () => {
        if (!canImport) {
            return;
        }
        fileInputRef.current?.click();
    };

    const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) {
            return;
        }
        setImportError(null);
        try {
            const result = await importMenu.mutateAsync(file);
            setImportResult(result);
        } catch (error) {
            setImportError('El archivo no se pudo procesar. Confirmá que sea la última plantilla.');
        } finally {
            event.target.value = '';
        }
    };

    const handleExport = async () => {
        if (!canExport) {
            return;
        }
        try {
            const blob = await exportMenu.mutateAsync();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `carta-${new Date().toISOString().slice(0, 10)}.xlsx`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            window.alert('No pudimos generar la descarga.');
        }
    };

    const totalAvailable = items.filter((item) => item.is_available).length;

    return (
        <section className="space-y-8">
            <header className="rounded-3xl border border-amber-100 bg-gradient-to-br from-amber-50 via-rose-50 to-white p-6 shadow-sm">
                <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                    <div className="space-y-2">
                        <p className="text-xs uppercase tracking-widest text-amber-500">Carta inteligente</p>
                        <h1 className="text-3xl font-semibold text-slate-900">Diseñá tu menú centralizado</h1>
                        <p className="max-w-2xl text-sm text-slate-500">
                            Las categorías y productos que cargues acá alimentan las órdenes, tableros de cocina y el importador de
                            ventas. Activá o pausá platos en segundos para mantener sincronizado al equipo completo.
                        </p>
                    </div>
                    {canManage ? (
                        <div className="flex flex-wrap gap-3">
                            <button
                                type="button"
                                onClick={() => handleOpenCategoryModal()}
                                className="rounded-full border border-slate-900 px-5 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-900 hover:text-white"
                            >
                                Nueva categoría
                            </button>
                            <button
                                type="button"
                                onClick={() => handleOpenItemModal()}
                                className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
                            >
                                Nuevo plato
                            </button>
                        </div>
                    ) : null}
                </div>
                <div className="mt-6 rounded-2xl border border-white/60 bg-white/80 p-4 text-sm text-slate-600 shadow-inner">
                    <p className="font-semibold text-slate-900">Integrada a pedidos</p>
                    <p className="mt-1 text-slate-500">
                        Cada cambio impacta en <a href="/app/orders" className="font-semibold text-amber-600">Órdenes</a> y en el tablero de cocina.
                    </p>
                </div>
            </header>

            <div className="grid gap-6 lg:grid-cols-[320px,1fr]">
                <aside className="space-y-4">
                    <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-xs uppercase tracking-wide text-slate-400">Categorías</p>
                                <p className="text-lg font-semibold text-slate-900">{categories.length}</p>
                            </div>
                            {canManage ? (
                                <button
                                    type="button"
                                    onClick={() => handleOpenCategoryModal()}
                                    className="text-sm font-semibold text-amber-600"
                                >
                                    Añadir
                                </button>
                            ) : null}
                        </div>
                        <div className="mt-4 space-y-2">
                            <button
                                type="button"
                                onClick={() => handleSelectCategory(null)}
                                className={`w-full rounded-2xl px-4 py-3 text-left text-sm font-semibold transition ${selectedCategory === null
                                        ? 'bg-amber-100 text-amber-800'
                                        : 'bg-slate-50 text-slate-600 hover:bg-slate-100'
                                    }`}
                            >
                                Todas las categorías
                            </button>
                            {categoryQuery.isLoading ? <p className="text-xs text-slate-400">Cargando...</p> : null}
                            {categoryQuery.isError ? (
                                <p className="text-xs text-rose-500">No pudimos cargar las categorías.</p>
                            ) : null}
                            {!categoryQuery.isLoading && categories.length === 0 ? (
                                <p className="text-xs text-slate-500">Creá tu primera categoría para comenzar.</p>
                            ) : null}
                            {categories.map((category) => (
                                <div
                                    key={category.id}
                                    className={`rounded-2xl border px-4 py-3 text-sm transition ${selectedCategory === category.id
                                            ? 'border-amber-400 bg-amber-50'
                                            : 'border-slate-100 bg-white hover:border-amber-200'
                                        }`}
                                >
                                    <button
                                        type="button"
                                        onClick={() => handleSelectCategory(category.id)}
                                        className="flex w-full items-center justify-between text-left"
                                    >
                                        <div>
                                            <p className="font-semibold text-slate-900">{category.name}</p>
                                            <p className="text-xs text-slate-500">{category.item_count} productos</p>
                                        </div>
                                        <span
                                            className={`h-2 w-2 rounded-full ${category.is_active ? 'bg-emerald-400' : 'bg-slate-300'
                                                }`}
                                        />
                                    </button>
                                    {canManage ? (
                                        <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
                                            <button type="button" onClick={() => handleOpenCategoryModal(category)}>
                                                Editar
                                            </button>
                                            <span>·</span>
                                            <button type="button" onClick={() => handleDeleteCategory(category)}>
                                                Eliminar
                                            </button>
                                        </div>
                                    ) : null}
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                        <p className="text-sm font-semibold text-slate-900">Sincronización masiva</p>
                        <p className="mt-1 text-xs text-slate-500">Usá la plantilla de Excel para cargar tu carta desde sistemas externos.</p>
                        <div className="mt-4 space-y-2">
                            <button
                                type="button"
                                disabled={!canImport || importMenu.isPending}
                                onClick={handleImportClick}
                                className="w-full rounded-xl border border-dashed border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-amber-300 disabled:opacity-60"
                            >
                                {importMenu.isPending ? 'Procesando archivo...' : 'Importar plantilla'}
                            </button>
                            <button
                                type="button"
                                disabled={!canExport || exportMenu.isPending}
                                onClick={handleExport}
                                className="w-full rounded-xl border border-slate-900 px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-900 hover:text-white disabled:opacity-60"
                            >
                                {exportMenu.isPending ? 'Generando archivo...' : 'Descargar catálogo'}
                            </button>
                            {importError ? <p className="text-xs text-rose-500">{importError}</p> : null}
                            {importResult ? (
                                <div className="rounded-2xl bg-slate-50 p-3 text-xs text-slate-600">
                                    <p className="font-semibold text-slate-900">Último importado</p>
                                    <dl className="mt-2 grid grid-cols-2 gap-2">
                                        <div>
                                            <dt className="text-[11px] uppercase tracking-wide text-slate-400">Filas</dt>
                                            <dd className="text-sm font-semibold text-slate-900">{importResult.summary.total_rows}</dd>
                                        </div>
                                        <div>
                                            <dt className="text-[11px] uppercase tracking-wide text-slate-400">Nuevos items</dt>
                                            <dd className="text-sm font-semibold text-slate-900">{importResult.summary.created_items}</dd>
                                        </div>
                                        <div>
                                            <dt className="text-[11px] uppercase tracking-wide text-slate-400">Actualizados</dt>
                                            <dd className="text-sm font-semibold text-slate-900">{importResult.summary.updated_items}</dd>
                                        </div>
                                        <div>
                                            <dt className="text-[11px] uppercase tracking-wide text-slate-400">Saltados</dt>
                                            <dd className="text-sm font-semibold text-slate-900">{importResult.summary.skipped_rows}</dd>
                                        </div>
                                    </dl>
                                    {importResult.preview.length ? (
                                        <div className="mt-3 max-h-40 space-y-1 overflow-y-auto rounded-xl border border-slate-200 bg-white p-2">
                                            {importResult.preview.slice(0, 4).map((row) => (
                                                <p key={row.line_number} className="text-[11px] text-slate-500">
                                                    #{row.line_number} · {row.name} ({row.action})
                                                </p>
                                            ))}
                                            {importResult.preview.length > 4 ? (
                                                <p className="text-[11px] font-semibold text-slate-400">
                                                    +{importResult.preview.length - 4} filas más
                                                </p>
                                            ) : null}
                                        </div>
                                    ) : null}
                                </div>
                            ) : null}
                        </div>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".xlsx"
                            className="hidden"
                            onChange={handleFileChange}
                        />
                    </div>
                </aside>

                <div className="space-y-4">
                    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                            <div>
                                <p className="text-xs uppercase tracking-wide text-slate-400">Productos activos</p>
                                <h2 className="text-2xl font-semibold text-slate-900">{totalAvailable} disponibles</h2>
                                <p className="text-sm text-slate-500">{items.length} en total en esta vista</p>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                                <input
                                    type="search"
                                    placeholder="Buscar por nombre, SKU o tag"
                                    value={search}
                                    onChange={(event) => setSearch(event.target.value)}
                                    className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none lg:w-64"
                                />
                                {availabilityFilters.map((filter) => (
                                    <button
                                        key={filter.id}
                                        type="button"
                                        onClick={() => setAvailability(filter.id)}
                                        className={`rounded-full px-4 py-2 text-xs font-semibold transition ${availability === filter.id
                                                ? 'bg-slate-900 text-white'
                                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                            }`}
                                    >
                                        {filter.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>

                    <div className="space-y-3">
                        {itemsQuery.isLoading ? <p className="text-sm text-slate-500">Cargando productos...</p> : null}
                        {itemsQuery.isError ? (
                            <p className="text-sm text-rose-500">No pudimos cargar los productos de la carta.</p>
                        ) : null}
                        {!itemsQuery.isLoading && items.length === 0 ? (
                            <div className="rounded-3xl border border-dashed border-slate-300 bg-white p-8 text-center">
                                <p className="text-base font-semibold text-slate-900">Todavía no hay platos para esta vista</p>
                                <p className="mt-1 text-sm text-slate-500">
                                    Agregá una nueva receta o cambiá los filtros para ver más resultados.
                                </p>
                                {canManage ? (
                                    <button
                                        type="button"
                                        onClick={() => handleOpenItemModal()}
                                        className="mt-4 rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white"
                                    >
                                        Crear plato
                                    </button>
                                ) : null}
                            </div>
                        ) : null}
                        <div className="grid gap-4 xl:grid-cols-2">
                            {items.map((item) => (
                                <article
                                    key={item.id}
                                    className="flex flex-col gap-3 rounded-3xl border border-slate-100 bg-white p-5 shadow-sm"
                                >
                                    <div className="flex flex-wrap items-start justify-between gap-2">
                                        <div>
                                            <p className="text-sm uppercase tracking-wide text-slate-400">
                                                {item.category_name || 'Sin categoría'}
                                            </p>
                                            <h3 className="text-xl font-semibold text-slate-900">{item.name}</h3>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-2xl font-semibold text-slate-900">{formatCurrency(item.price)}</p>
                                            {item.sku ? <p className="text-xs text-slate-400">SKU {item.sku}</p> : null}
                                        </div>
                                    </div>
                                    {item.description ? (
                                        <p className="text-sm text-slate-600">{item.description}</p>
                                    ) : null}
                                    {item.tags?.length ? (
                                        <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                                            {item.tags.map((tag) => (
                                                <span key={tag} className="rounded-full bg-slate-100 px-3 py-1">
                                                    #{tag}
                                                </span>
                                            ))}
                                        </div>
                                    ) : null}
                                    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
                                        <div className="flex items-center gap-2">
                                            <span className={`flex h-2 w-2 items-center justify-center rounded-full ${item.is_available ? 'bg-emerald-400' : 'bg-slate-300'
                                                }`}
                                            />
                                            <span>{item.is_available ? 'Disponible' : 'Pausado'}</span>
                                            {item.is_featured ? (
                                                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-700">Destacado</span>
                                            ) : null}
                                        </div>
                                        {item.estimated_time_minutes ? (
                                            <span>~{item.estimated_time_minutes} min</span>
                                        ) : null}
                                    </div>
                                    {canManage ? (
                                        <div className="flex flex-wrap items-center gap-2 text-sm">
                                            <button
                                                type="button"
                                                onClick={() => handleToggleAvailability(item, !item.is_available)}
                                                className={`rounded-full px-4 py-1 text-xs font-semibold transition ${item.is_available
                                                        ? 'border border-slate-300 text-slate-600 hover:border-rose-400 hover:text-rose-600'
                                                        : 'bg-emerald-600 text-white hover:bg-emerald-500'
                                                    }`}
                                                disabled={updateItem.isPending}
                                            >
                                                {item.is_available ? 'Pausar' : 'Publicar'}
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => handleOpenItemModal(item)}
                                                className="rounded-full border border-slate-200 px-4 py-1 text-xs font-semibold text-slate-600"
                                            >
                                                Editar
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => handleDeleteItem(item)}
                                                className="rounded-full border border-slate-200 px-4 py-1 text-xs font-semibold text-slate-600"
                                            >
                                                Eliminar
                                            </button>
                                        </div>
                                    ) : null}
                                </article>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                        <p className="text-xs uppercase tracking-wide text-slate-400">Vista previa</p>
                        <h2 className="text-2xl font-semibold text-slate-900">Así ve la cocina tu carta</h2>
                    </div>
                    <button
                        type="button"
                        onClick={() => structureQuery.refetch()}
                        className="rounded-full border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600"
                    >
                        Actualizar
                    </button>
                </div>
                {structureQuery.isLoading ? <p className="mt-4 text-sm text-slate-500">Cargando vista previa...</p> : null}
                {structureQuery.isError ? (
                    <p className="mt-4 text-sm text-rose-500">No pudimos armar la vista previa.</p>
                ) : null}
                {structureQuery.data ? (
                    <div className="mt-6 grid gap-4 lg:grid-cols-2">
                        {structureQuery.data.map((category) => (
                            <div key={category.id} className="rounded-2xl border border-slate-100 bg-slate-50 p-4">
                                <p className="text-xs uppercase tracking-wide text-slate-400">{category.name}</p>
                                <ul className="mt-2 space-y-2">
                                    {category.items.map((item) => (
                                        <li key={item.id} className="flex items-center justify-between text-sm">
                                            <div>
                                                <p className="font-semibold text-slate-900">{item.name}</p>
                                                {item.tags?.length ? (
                                                    <p className="text-xs text-slate-400">{item.tags.join(', ')}</p>
                                                ) : null}
                                            </div>
                                            <span className="font-semibold text-slate-900">{formatCurrency(item.price)}</span>
                                        </li>
                                    ))}
                                    {category.items.length === 0 ? (
                                        <p className="text-xs text-slate-400">Sin productos activos.</p>
                                    ) : null}
                                </ul>
                            </div>
                        ))}
                    </div>
                ) : null}
            </div>

            <Modal open={categoryModalOpen} onClose={handleCloseCategoryModal} title={categoryForm.id ? 'Editar categoría' : 'Nueva categoría'}>
                <label className="text-sm font-semibold text-slate-700">
                    Nombre
                    <input
                        type="text"
                        value={categoryForm.name}
                        onChange={(event) => setCategoryForm((prev) => ({ ...prev, name: event.target.value }))}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    />
                </label>
                <label className="text-sm font-semibold text-slate-700">
                    Descripción interna
                    <textarea
                        value={categoryForm.description}
                        onChange={(event) => setCategoryForm((prev) => ({ ...prev, description: event.target.value }))}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        rows={3}
                    />
                </label>
                <div className="grid gap-4 md:grid-cols-2">
                    <label className="text-sm font-semibold text-slate-700">
                        Orden
                        <input
                            type="number"
                            min="0"
                            value={categoryForm.position}
                            onChange={(event) => setCategoryForm((prev) => ({ ...prev, position: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                    <label className="flex items-center gap-3 text-sm font-semibold text-slate-700">
                        <input
                            type="checkbox"
                            checked={categoryForm.is_active}
                            onChange={(event) => setCategoryForm((prev) => ({ ...prev, is_active: event.target.checked }))}
                            className="h-4 w-4 rounded border-slate-300"
                        />
                        Visible para órdenes y cocina
                    </label>
                </div>
                {categoryFormError ? <p className="text-sm text-rose-600">{categoryFormError}</p> : null}
                <div className="flex justify-end gap-3">
                    <button
                        type="button"
                        onClick={handleCloseCategoryModal}
                        className="rounded-full border border-slate-200 px-5 py-2 text-sm font-semibold text-slate-600"
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        disabled={createCategory.isPending || updateCategory.isPending}
                        onClick={handleCategorySubmit}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
                    >
                        Guardar categoría
                    </button>
                </div>
            </Modal>

            <Modal open={itemModalOpen} onClose={handleCloseItemModal} title={itemForm.id ? 'Editar plato' : 'Nuevo plato'}>
                <label className="text-sm font-semibold text-slate-700">
                    Nombre
                    <input
                        type="text"
                        value={itemForm.name}
                        onChange={(event) => setItemForm((prev) => ({ ...prev, name: event.target.value }))}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    />
                </label>
                <label className="text-sm font-semibold text-slate-700">
                    Categoría
                    <select
                        value={itemForm.category_id ?? ''}
                        onChange={(event) =>
                            setItemForm((prev) => ({ ...prev, category_id: event.target.value || null }))
                        }
                        className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    >
                        <option value="">Sin categoría</option>
                        {categories.map((category) => (
                            <option key={category.id} value={category.id}>
                                {category.name}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="text-sm font-semibold text-slate-700">
                    Descripción
                    <textarea
                        value={itemForm.description}
                        onChange={(event) => setItemForm((prev) => ({ ...prev, description: event.target.value }))}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        rows={3}
                    />
                </label>
                <div className="grid gap-4 md:grid-cols-2">
                    <label className="text-sm font-semibold text-slate-700">
                        Precio sugerido (ARS)
                        <input
                            type="number"
                            min="0"
                            step="0.5"
                            value={itemForm.price}
                            onChange={(event) => setItemForm((prev) => ({ ...prev, price: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                    <label className="text-sm font-semibold text-slate-700">
                        SKU / Código interno
                        <input
                            type="text"
                            value={itemForm.sku}
                            onChange={(event) => setItemForm((prev) => ({ ...prev, sku: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                </div>
                <label className="text-sm font-semibold text-slate-700">
                    Tags (separados por coma)
                    <input
                        type="text"
                        value={itemForm.tags}
                        onChange={(event) => setItemForm((prev) => ({ ...prev, tags: event.target.value }))}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    />
                </label>
                <div className="grid gap-4 md:grid-cols-2">
                    <label className="text-sm font-semibold text-slate-700">
                        Orden
                        <input
                            type="number"
                            min="0"
                            value={itemForm.position}
                            onChange={(event) => setItemForm((prev) => ({ ...prev, position: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                    <label className="text-sm font-semibold text-slate-700">
                        Tiempo estimado (minutos)
                        <input
                            type="number"
                            min="0"
                            value={itemForm.estimated_time_minutes}
                            onChange={(event) =>
                                setItemForm((prev) => ({ ...prev, estimated_time_minutes: event.target.value }))
                            }
                            className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                </div>
                <div className="flex flex-wrap gap-4 text-sm font-semibold text-slate-700">
                    <label className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            checked={itemForm.is_available}
                            onChange={(event) => setItemForm((prev) => ({ ...prev, is_available: event.target.checked }))}
                            className="h-4 w-4 rounded border-slate-300"
                        />
                        Disponible para tomar órdenes
                    </label>
                    <label className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            checked={itemForm.is_featured}
                            onChange={(event) => setItemForm((prev) => ({ ...prev, is_featured: event.target.checked }))}
                            className="h-4 w-4 rounded border-slate-300"
                        />
                        Destacado en la carta
                    </label>
                </div>
                {itemFormError ? <p className="text-sm text-rose-600">{itemFormError}</p> : null}
                <div className="flex justify-end gap-3">
                    <button
                        type="button"
                        onClick={handleCloseItemModal}
                        className="rounded-full border border-slate-200 px-5 py-2 text-sm font-semibold text-slate-600"
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        disabled={createItem.isPending || updateItem.isPending}
                        onClick={handleItemSubmit}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
                    >
                        Guardar plato
                    </button>
                </div>
            </Modal>
        </section>
    );
}

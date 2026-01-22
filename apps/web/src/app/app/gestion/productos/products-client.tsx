"use client";

import { useDeferredValue, useMemo, useState } from 'react';
import { z } from 'zod';

import { Modal } from '@/components/ui/modal';
import { useCreateProduct, useProducts, useUpdateProduct } from '@/features/gestion/hooks';
import type { Product } from '@/features/gestion/types';
import { ApiError } from '@/lib/api/client';

const productFormSchema = z.object({
    name: z.string().min(2, 'El nombre es obligatorio'),
    sku: z.string().optional(),
    barcode: z.string().optional(),
    cost: z.string().min(1, 'Ingresá un costo'),
    price: z.string().min(1, 'Ingresá un precio'),
    stock_min: z.string().min(1, 'Definí un stock mínimo'),
});

type FormState = z.infer<typeof productFormSchema>;

const emptyForm: FormState = {
    name: '',
    sku: '',
    barcode: '',
    cost: '',
    price: '',
    stock_min: '',
};

function formatCurrency(value: string) {
    const numeric = Number(value);
    if (Number.isNaN(numeric)) {
        return '$0';
    }
    return new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 2 }).format(numeric);
}

function formatQuantity(value: string) {
    const numeric = Number(value);
    if (Number.isNaN(numeric)) {
        return '0';
    }
    return numeric.toLocaleString('es-AR', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

type ProductsClientProps = {
    canManage: boolean;
    canViewCost: boolean;
};

export function ProductsClient({ canManage, canViewCost }: ProductsClientProps) {
    const [search, setSearch] = useState('');
    const deferredSearch = useDeferredValue(search);
    const [includeInactive, setIncludeInactive] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [form, setForm] = useState<FormState>(emptyForm);
    const [editing, setEditing] = useState<Product | null>(null);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [feedback, setFeedback] = useState<string>('');
    const [permissionNotice, setPermissionNotice] = useState<string>('');

    const productsQuery = useProducts(deferredSearch, includeInactive);
    const createMutation = useCreateProduct();
    const updateMutation = useUpdateProduct();

    const isSaving = createMutation.isPending || updateMutation.isPending;

    const products = useMemo(() => productsQuery.data ?? [], [productsQuery.data]);

    const handleOpenCreate = () => {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para crear productos.');
            return;
        }
        setEditing(null);
        setForm({ ...emptyForm });
        setErrors({});
        setFeedback('');
        setModalOpen(true);
    };

    const handleOpenEdit = (product: Product) => {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para editar productos.');
            return;
        }
        setEditing(product);
        setForm({
            name: product.name,
            sku: product.sku ?? '',
            barcode: product.barcode ?? '',
            cost: product.cost ?? '',
            price: product.price ?? '',
            stock_min: product.stock_min ?? '',
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
            setPermissionNotice('Tu rol no tiene permiso para modificar productos.');
            return;
        }
        const parsed = productFormSchema.safeParse(form);
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
            name: parsed.data.name,
            sku: parsed.data.sku || undefined,
            barcode: parsed.data.barcode || undefined,
            cost: Number(parsed.data.cost),
            price: Number(parsed.data.price),
            stock_min: Number(parsed.data.stock_min),
        };

        try {
            if (editing) {
                await updateMutation.mutateAsync({ id: editing.id, payload });
                setFeedback('Producto actualizado.');
            } else {
                await createMutation.mutateAsync(payload);
                setFeedback('Producto creado.');
            }
            setModalOpen(false);
        } catch (error) {
            if (error instanceof ApiError && error.status === 403) {
                setPermissionNotice('Tu rol no tiene permiso para esta acción.');
            } else {
                setFeedback('No pudimos guardar los cambios.');
            }
        }
    }

    async function handleToggleActive(product: Product) {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para esta acción.');
            return;
        }
        try {
            await updateMutation.mutateAsync({ id: product.id, payload: { is_active: !product.is_active } });
        } catch (error) {
            if (error instanceof ApiError && error.status === 403) {
                setPermissionNotice('Tu rol no tiene permiso para esta acción.');
            } else {
                setFeedback('No pudimos actualizar el estado.');
            }
        }
    }

    return (
        <section className="space-y-4">
            <header className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                    <h2 className="text-2xl font-semibold text-slate-900">Productos</h2>
                    <p className="text-sm text-slate-500">Catálogo multi-tenant sincronizado con inventario.</p>
                </div>
                <div className="flex flex-col gap-3 md:flex-row md:items-center">
                    <label className="flex items-center gap-2 text-sm text-slate-500">
                        <input
                            type="checkbox"
                            checked={includeInactive}
                            onChange={(event) => setIncludeInactive(event.target.checked)}
                            className="size-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
                        />
                        Mostrar inactivos
                    </label>
                    {canManage ? (
                        <button
                            type="button"
                            onClick={handleOpenCreate}
                            className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                        >
                            Nuevo producto
                        </button>
                    ) : null}
                </div>
            </header>
            {!canManage && (
                <p className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                    Tu rol puede consultar el catálogo pero no crear ni editar productos.
                </p>
            )}
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <input
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Buscar por nombre o SKU"
                        className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    />
                    <div className="text-right text-sm">
                        {productsQuery.isError && <p className="text-rose-600">No pudimos cargar los productos.</p>}
                        {feedback && <p className="text-slate-500">{feedback}</p>}
                        {permissionNotice && <p className="text-rose-600">{permissionNotice}</p>}
                    </div>
                </div>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Producto</th>
                                <th className="px-3 py-2">SKU</th>
                                <th className="px-3 py-2">Precio</th>
                                <th className="px-3 py-2">Stock min.</th>
                                <th className="px-3 py-2">Estado</th>
                                {canManage ? <th className="px-3 py-2" /> : null}
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {productsQuery.isLoading && (
                                <tr>
                                    <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                                        Cargando productos...
                                    </td>
                                </tr>
                            )}
                            {!productsQuery.isLoading && products.length === 0 && (
                                <tr>
                                    <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                                        No encontramos productos.
                                    </td>
                                </tr>
                            )}
                            {products.map((product) => (
                                <tr key={product.id} className="text-slate-700">
                                    <td className="px-3 py-3">
                                        <p className="font-medium">{product.name}</p>
                                        {product.barcode && <p className="text-xs text-slate-400">EAN {product.barcode}</p>}
                                    </td>
                                    <td className="px-3 py-3 text-slate-500">{product.sku || '—'}</td>
                                    <td className="px-3 py-3">{formatCurrency(product.price)}</td>
                                    <td className="px-3 py-3">{formatQuantity(product.stock_min)}</td>
                                    <td className="px-3 py-3">
                                        <span
                                            className={`rounded-full px-3 py-1 text-xs font-semibold ${product.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'
                                                }`}
                                        >
                                            {product.is_active ? 'Activo' : 'Inactivo'}
                                        </span>
                                    </td>
                                    {canManage ? (
                                        <td className="px-3 py-3">
                                            <div className="flex gap-2 text-xs font-semibold">
                                                <button
                                                    type="button"
                                                    onClick={() => handleOpenEdit(product)}
                                                    className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 hover:border-slate-900 hover:text-slate-900"
                                                >
                                                    Editar
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => handleToggleActive(product)}
                                                    className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 hover:border-slate-900 hover:text-slate-900"
                                                >
                                                    {product.is_active ? 'Desactivar' : 'Activar'}
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
            <Modal open={modalOpen} onClose={handleCloseModal} title={editing ? 'Editar producto' : 'Nuevo producto'}>
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
                        SKU
                        <input
                            type="text"
                            value={form.sku}
                            onChange={(event) => setForm((prev) => ({ ...prev, sku: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                    <label className="text-sm font-medium text-slate-700">
                        Código de barras
                        <input
                            type="text"
                            value={form.barcode}
                            onChange={(event) => setForm((prev) => ({ ...prev, barcode: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                    </label>
                    <label className="text-sm font-medium text-slate-700">
                        Stock mínimo <span className="text-rose-600" aria-hidden="true">*</span>
                        <span className="sr-only">Campo obligatorio</span>
                        <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={form.stock_min}
                            onChange={(event) => setForm((prev) => ({ ...prev, stock_min: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            required
                            aria-required="true"
                        />
                        {errors.stock_min && <span className="text-xs text-rose-600">{errors.stock_min}</span>}
                    </label>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                    {canViewCost ? (
                        <label className="text-sm font-medium text-slate-700">
                            Costo <span className="text-rose-600" aria-hidden="true">*</span>
                            <span className="sr-only">Campo obligatorio</span>
                            <input
                                type="number"
                                min="0"
                                step="0.01"
                                value={form.cost}
                                onChange={(event) => setForm((prev) => ({ ...prev, cost: event.target.value }))}
                                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                                required
                                aria-required="true"
                            />
                            {errors.cost && <span className="text-xs text-rose-600">{errors.cost}</span>}
                        </label>
                    ) : null}
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
                </div>
                <div className="flex justify-end gap-3 pt-2">
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
        </section>
    );
}

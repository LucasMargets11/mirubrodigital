"use client";

import { useCallback, useDeferredValue, useEffect, useId, useMemo, useState } from 'react';
import { z } from 'zod';

import { StockStatusSelect } from '@/components/app/stock-status-select';
import { Modal } from '@/components/ui/modal';
import {
    useCreateMovement,
    useProducts,
    useStockLevels,
    useStockMovements,
} from '@/features/gestion/hooks';
import type { ProductStock, StockMovement } from '@/features/gestion/types';
import { ApiError } from '@/lib/api/client';

const movementSchema = z.object({
    product_id: z.string().uuid('Seleccioná un producto'),
    movement_type: z.enum(['IN', 'OUT', 'ADJUST', 'WASTE']),
    quantity: z.string().min(1, 'Ingresa una cantidad'),
    note: z.string().optional(),
});

type MovementForm = z.infer<typeof movementSchema>;

const movementLabels: Record<MovementForm['movement_type'], string> = {
    IN: 'Entrada',
    OUT: 'Salida',
    ADJUST: 'Ajuste',
    WASTE: 'Merma',
};

type StockClientProps = {
    canManage: boolean;
    initialStatus?: string;
    initialAction?: 'movement';
    initialProductId?: string;
};

export function StockClient({ canManage, initialStatus = '', initialAction, initialProductId }: StockClientProps) {
    const [search, setSearch] = useState('');
    const deferredSearch = useDeferredValue(search);
    const [statusFilter, setStatusFilter] = useState(initialStatus ?? '');
    const [selectedProductForMovements, setSelectedProductForMovements] = useState<string | undefined>();
    const [pendingAction, setPendingAction] = useState<'movement' | undefined>(initialAction);
    const [productSearch, setProductSearch] = useState('');
    const deferredModalSearch = useDeferredValue(productSearch.trim());
    const modalSearchEnabled = deferredModalSearch.length >= 2;

    const [form, setForm] = useState<MovementForm>({ product_id: '', movement_type: 'IN', quantity: '', note: '' });
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [modalOpen, setModalOpen] = useState(false);
    const [feedback, setFeedback] = useState('');
    const [permissionNotice, setPermissionNotice] = useState('');

    const stockQuery = useStockLevels(deferredSearch, statusFilter);
    const productsQuery = useProducts('', true);
    const modalProductsQuery = useProducts(deferredModalSearch, true, { enabled: modalSearchEnabled });
    const movementsQuery = useStockMovements(selectedProductForMovements);
    const createMovement = useCreateMovement();

    const products = useMemo(() => productsQuery.data ?? [], [productsQuery.data]);
    const stockRows = useMemo(() => stockQuery.data ?? [], [stockQuery.data]);
    const movements = useMemo(() => movementsQuery.data ?? [], [movementsQuery.data]);
    const productSelectId = useId();
    const productSearchId = `${productSelectId}-search`;
    const modalSearchResults = modalProductsQuery.data ?? [];
    const modalSearchLoading = modalSearchEnabled && modalProductsQuery.isFetching;
    const modalSearchErrored = modalSearchEnabled && modalProductsQuery.isError;
    const localProductMatches = useMemo(() => {
        const term = productSearch.trim().toLowerCase();
        if (!term) {
            return products;
        }
        return products.filter((product) => {
            const name = product.name?.toLowerCase() ?? '';
            const sku = product.sku?.toLowerCase() ?? '';
            return name.includes(term) || sku.includes(term);
        });
    }, [productSearch, products]);
    const modalProductMatches = modalSearchEnabled
        ? modalSearchResults.length > 0
            ? modalSearchResults
            : localProductMatches
        : localProductMatches;
    const knownProducts = useMemo(() => {
        const map = new Map<string, (typeof products)[number]>();
        products.forEach((product) => map.set(product.id, product));
        modalSearchResults.forEach((product) => {
            if (!map.has(product.id)) {
                map.set(product.id, product);
            }
        });
        return map;
    }, [modalSearchResults, products]);
    const selectedProductOption = useMemo(() => {
        if (!form.product_id) {
            return null;
        }
        return knownProducts.get(form.product_id) ?? null;
    }, [form.product_id, knownProducts]);
    const modalProductOptions = useMemo(() => {
        if (!selectedProductOption) {
            return modalProductMatches;
        }
        const exists = modalProductMatches.some((product) => product.id === selectedProductOption.id);
        return exists ? modalProductMatches : [selectedProductOption, ...modalProductMatches];
    }, [modalProductMatches, selectedProductOption]);

    const isSaving = createMovement.isPending;

    const handleOpenModal = useCallback(
        (product?: ProductStock) => {
            if (!canManage) {
                setPermissionNotice('Tu rol no tiene permiso para registrar movimientos.');
                return;
            }
            setPermissionNotice('');
            setProductSearch('');
            setForm((prev) => ({
                product_id: product?.product.id ?? prev.product_id ?? '',
                movement_type: 'IN',
                quantity: '',
                note: '',
            }));
            setErrors({});
            setFeedback('');
            setModalOpen(true);
        },
        [canManage]
    );

    useEffect(() => {
        if (pendingAction !== 'movement' || !canManage) {
            return;
        }
        const targetProduct = initialProductId ? stockRows.find((row) => row.product.id === initialProductId) : undefined;
        handleOpenModal(targetProduct);
        setPendingAction(undefined);
    }, [pendingAction, canManage, handleOpenModal, initialProductId, stockRows]);

    async function handleSubmit() {
        if (!canManage) {
            setPermissionNotice('Tu rol no tiene permiso para registrar movimientos.');
            return;
        }
        const parsed = movementSchema.safeParse(form);
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

        try {
            await createMovement.mutateAsync({
                product_id: parsed.data.product_id,
                movement_type: parsed.data.movement_type,
                quantity: Number(parsed.data.quantity),
                note: parsed.data.note,
            });
            setPermissionNotice('');
            setModalOpen(false);
        } catch (error) {
            if (error instanceof ApiError && error.status === 403) {
                setPermissionNotice('Tu rol no tiene permiso para registrar movimientos.');
            } else {
                setFeedback('No pudimos registrar el movimiento.');
            }
        }
    }

    const statusBadges: Record<ProductStock['status'], string> = {
        ok: 'bg-emerald-100 text-emerald-700',
        low: 'bg-amber-100 text-amber-700',
        out: 'bg-rose-100 text-rose-700',
    };

    return (
        <section className="space-y-6">
            <header className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                    <h2 className="text-2xl font-semibold text-slate-900">Stock</h2>
                    <p className="text-sm text-slate-500">Disponibilidad por producto y alertas preventivas.</p>
                </div>
                {canManage ? (
                    <button
                        type="button"
                        onClick={() => handleOpenModal()}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
                    >
                        Registrar movimiento
                    </button>
                ) : null}
            </header>
            {!canManage && (
                <p className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                    Tu rol puede monitorear el inventario pero no registrar movimientos.
                </p>
            )}
            {permissionNotice && (
                <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">{permissionNotice}</p>
            )}
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <input
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Buscar producto"
                        className="w-full rounded-xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                    />
                    <StockStatusSelect value={statusFilter} onValueChange={setStatusFilter} className="w-full md:w-60" />
                </div>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Producto</th>
                                <th className="px-3 py-2">Cantidad</th>
                                <th className="px-3 py-2">Stock mínimo</th>
                                <th className="px-3 py-2">Estado</th>
                                <th className="px-3 py-2" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {stockQuery.isLoading && (
                                <tr>
                                    <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                                        Cargando inventario...
                                    </td>
                                </tr>
                            )}
                            {!stockQuery.isLoading && stockRows.length === 0 && (
                                <tr>
                                    <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                                        No hay registros para mostrar.
                                    </td>
                                </tr>
                            )}
                            {stockRows.map((row) => (
                                <tr key={row.id}>
                                    <td className="px-3 py-3">
                                        <p className="font-medium text-slate-900">{row.product.name}</p>
                                        <p className="text-xs text-slate-400">SKU {row.product.sku || '—'}</p>
                                    </td>
                                    <td className="px-3 py-3 font-semibold text-slate-900">{Number(row.quantity).toLocaleString('es-AR')}</td>
                                    <td className="px-3 py-3 text-slate-500">{Number(row.product.stock_min).toLocaleString('es-AR')}</td>
                                    <td className="px-3 py-3">
                                        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadges[row.status]}`}>
                                            {row.status === 'ok' && 'En orden'}
                                            {row.status === 'low' && 'Stock bajo'}
                                            {row.status === 'out' && 'Sin stock'}
                                        </span>
                                    </td>
                                    <td className="px-3 py-3">
                                        {canManage ? (
                                            <button
                                                type="button"
                                                onClick={() => handleOpenModal(row)}
                                                className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                                            >
                                                Ajustar
                                            </button>
                                        ) : null}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
            <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div>
                        <h3 className="text-lg font-semibold text-slate-900">Movimientos recientes</h3>
                        <p className="text-sm text-slate-500">Ultimas operaciones registradas.</p>
                    </div>
                    <select
                        value={selectedProductForMovements ?? ''}
                        onChange={(event) => setSelectedProductForMovements(event.target.value || undefined)}
                        className="rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                    >
                        <option value="">Todos los productos</option>
                        {products.map((product) => (
                            <option key={product.id} value={product.id}>
                                {product.name}
                            </option>
                        ))}
                    </select>
                </div>
                <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                        <thead>
                            <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-3 py-2">Fecha</th>
                                <th className="px-3 py-2">Producto</th>
                                <th className="px-3 py-2">Tipo</th>
                                <th className="px-3 py-2">Cantidad</th>
                                <th className="px-3 py-2">Nota</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {movementsQuery.isLoading && (
                                <tr>
                                    <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                                        Cargando movimientos...
                                    </td>
                                </tr>
                            )}
                            {!movementsQuery.isLoading && movements.length === 0 && (
                                <tr>
                                    <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                                        Aún no registraste movimientos.
                                    </td>
                                </tr>
                            )}
                            {movements.map((movement) => (
                                <tr key={movement.id}>
                                    <td className="px-3 py-3 text-slate-500">
                                        {new Date(movement.created_at).toLocaleString('es-AR', {
                                            dateStyle: 'medium',
                                            timeStyle: 'short',
                                        })}
                                    </td>
                                    <td className="px-3 py-3 font-medium text-slate-900">{movement.product.name}</td>
                                    <td className="px-3 py-3 text-slate-600">{movementLabels[movement.movement_type]}</td>
                                    <td className="px-3 py-3 font-semibold text-slate-900">{Number(movement.quantity).toLocaleString('es-AR')}</td>
                                    <td className="px-3 py-3 text-slate-500">{movement.note || '—'}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>
            <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Movimiento de inventario">
                <div className="text-sm font-medium text-slate-700">
                    <label htmlFor={productSelectId} className="text-sm font-medium text-slate-700">
                        Producto <span className="text-rose-600" aria-hidden="true">*</span>
                        <span className="sr-only">Campo obligatorio</span>
                    </label>
                    <div className="mt-1 space-y-2">
                        <label htmlFor={productSearchId} className="sr-only">
                            Buscar producto
                        </label>
                        <input
                            id={productSearchId}
                            type="search"
                            value={productSearch}
                            onChange={(event) => setProductSearch(event.target.value)}
                            placeholder="Buscar por nombre o SKU"
                            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        />
                        <div className="min-h-[1.5rem] space-y-1 text-xs font-normal">
                            {productSearch.trim().length > 0 && productSearch.trim().length < 2 ? (
                                <p className="text-slate-500">Escribí al menos 2 letras para buscar en todo el catálogo.</p>
                            ) : null}
                            {modalSearchLoading ? <p className="text-slate-500">Buscando productos...</p> : null}
                            {modalSearchErrored ? <p className="text-rose-600">No pudimos buscar productos. Intentá nuevamente.</p> : null}
                        </div>
                        <select
                            id={productSelectId}
                            value={form.product_id}
                            onChange={(event) => setForm((prev) => ({ ...prev, product_id: event.target.value }))}
                            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none disabled:cursor-not-allowed disabled:bg-slate-50"
                            required
                            aria-required="true"
                            disabled={modalProductOptions.length === 0}
                        >
                            <option value="">{modalProductOptions.length === 0 ? 'Sin coincidencias' : 'Seleccioná un producto'}</option>
                            {modalProductOptions.map((product) => (
                                <option key={product.id} value={product.id}>
                                    {product.name}
                                    {product.sku ? ` · SKU ${product.sku}` : ''}
                                </option>
                            ))}
                        </select>
                        {modalProductOptions.length === 0 && !modalSearchLoading ? (
                            <p className="text-xs font-normal text-slate-500">No encontramos productos para esa búsqueda.</p>
                        ) : null}
                        {errors.product_id && <span className="text-xs text-rose-600">{errors.product_id}</span>}
                    </div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                    <label className="text-sm font-medium text-slate-700">
                        Tipo <span className="text-rose-600" aria-hidden="true">*</span>
                        <span className="sr-only">Campo obligatorio</span>
                        <select
                            value={form.movement_type}
                            onChange={(event) => setForm((prev) => ({ ...prev, movement_type: event.target.value as MovementForm['movement_type'] }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
                            required
                            aria-required="true"
                        >
                            {Object.entries(movementLabels).map(([value, label]) => (
                                <option key={value} value={value}>
                                    {label}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className="text-sm font-medium text-slate-700">
                        Cantidad <span className="text-rose-600" aria-hidden="true">*</span>
                        <span className="sr-only">Campo obligatorio</span>
                        <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={form.quantity}
                            onChange={(event) => setForm((prev) => ({ ...prev, quantity: event.target.value }))}
                            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            required
                            aria-required="true"
                        />
                        {errors.quantity && <span className="text-xs text-rose-600">{errors.quantity}</span>}
                    </label>
                </div>
                <label className="text-sm font-medium text-slate-700">
                    Nota
                    <textarea
                        value={form.note}
                        onChange={(event) => setForm((prev) => ({ ...prev, note: event.target.value }))}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none"
                        rows={3}
                    />
                </label>
                {feedback && <p className="text-sm text-rose-600">{feedback}</p>}
                <div className="flex justify-end gap-3">
                    <button
                        type="button"
                        onClick={() => setModalOpen(false)}
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
                        {isSaving ? 'Guardando...' : 'Registrar'}
                    </button>
                </div>
            </Modal>
        </section>
    );
}

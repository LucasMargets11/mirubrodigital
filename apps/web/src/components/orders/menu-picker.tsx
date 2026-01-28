"use client";

import { RefObject, useEffect, useMemo, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';

import { useMenuStructure } from '@/features/menu/hooks';
import type { MenuStructureCategory, MenuStructureItem } from '@/features/menu/types';
import { formatCurrency } from '@/lib/format';
import { cn } from '@/lib/utils';

export type MenuStockStatus = 'in' | 'low' | 'critical' | 'out';

export type MenuProductSelection = {
    id: string;
    name: string;
    price: number;
    sku: string | null;
    categoryId: string | null;
    categoryName: string | null;
    description: string;
    stockStatus: MenuStockStatus;
    isAvailable: boolean;
};

type MenuPickerProps = {
    onProductSelect: (product: MenuProductSelection) => void;
    allowSellWithoutStock: boolean;
    onBlockedSelection?: (message: string) => void;
    searchInputRef?: RefObject<HTMLInputElement>;
};

const STATUS_META: Record<MenuStockStatus, { label: string; dot: string; background: string; text: string }> = {
    in: { label: 'Stock OK', dot: 'bg-emerald-400', background: 'bg-emerald-50', text: 'text-emerald-700' },
    low: { label: 'Stock bajo', dot: 'bg-amber-400', background: 'bg-amber-50', text: 'text-amber-800' },
    critical: { label: 'Crítico', dot: 'bg-rose-400', background: 'bg-rose-50', text: 'text-rose-800' },
    out: { label: 'Sin stock', dot: 'bg-rose-500', background: 'bg-rose-100', text: 'text-rose-800' },
};

const OUT_OF_STOCK_TAGS = ['sin stock', 'out-of-stock', 'out_stock', 'agotado'];
const LOW_STOCK_TAGS = ['bajo stock', 'low-stock', 'low_stock'];
const CRITICAL_TAGS = ['critico', 'crítico', 'critical'];

export function MenuPicker({ onProductSelect, allowSellWithoutStock, onBlockedSelection, searchInputRef }: MenuPickerProps) {
    const [search, setSearch] = useState('');
    const [categoryFilter, setCategoryFilter] = useState<string | null>(null);

    const structureQuery = useMenuStructure();
    const categories = structureQuery.data ?? [];

    const flattenedItems = useMemo(() => flattenStructure(categories), [categories]);

    const filteredItems = useMemo(() => {
        const normalizedSearch = search.trim().toLowerCase();
        return flattenedItems.filter((item) => {
            const matchesCategory = !categoryFilter || item.categoryId === categoryFilter;
            if (!matchesCategory) {
                return false;
            }
            if (!normalizedSearch) {
                return true;
            }
            const skuMatch = item.sku?.toLowerCase().includes(normalizedSearch) ?? false;
            const descriptionMatch = item.description?.toLowerCase().includes(normalizedSearch) ?? false;
            const categoryMatch = item.categoryName?.toLowerCase().includes(normalizedSearch) ?? false;
            return (
                item.name.toLowerCase().includes(normalizedSearch) ||
                skuMatch ||
                descriptionMatch ||
                categoryMatch
            );
        });
    }, [flattenedItems, categoryFilter, search]);

    useEffect(() => {
        if (searchInputRef?.current) {
            searchInputRef.current.focus();
        }
    }, [searchInputRef]);

    const handleSelect = (selection: MenuProductSelection) => {
        if (selection.stockStatus === 'out' && !allowSellWithoutStock) {
            onBlockedSelection?.('Este producto está sin stock. Podés habilitar la venta sin stock desde Configuración.');
            return;
        }
        onProductSelect(selection);
    };

    const handleKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
        if (event.key === 'Enter' && filteredItems.length === 1) {
            event.preventDefault();
            handleSelect(filteredItems[0]);
        }
    };

    const showEnterHint = filteredItems.length === 1 && search.trim().length >= 2;

    return (
        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Carta</p>
                        <h3 className="text-lg font-semibold text-slate-900">Agregar productos</h3>
                    </div>
                    <p className="hidden text-xs text-slate-400 md:block">Usá / para enfocar</p>
                </div>
                <div className="flex flex-col gap-3 md:flex-row md:items-center">
                    <div className="relative flex-1">
                        <input
                            ref={searchInputRef}
                            type="search"
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Buscar por nombre, SKU o código"
                            className="w-full rounded-2xl border border-slate-200 px-4 py-2 text-sm focus:border-slate-900 focus:outline-none"
                            aria-label="Buscar en la carta"
                        />
                        {showEnterHint ? (
                            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-400">Enter para agregar</span>
                        ) : null}
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <button
                            type="button"
                            onClick={() => setCategoryFilter(null)}
                            className={cn(
                                'rounded-full border px-3 py-1 text-xs font-semibold transition',
                                categoryFilter === null
                                    ? 'border-slate-900 bg-slate-900 text-white'
                                    : 'border-slate-200 text-slate-600 hover:border-slate-900 hover:text-slate-900'
                            )}
                        >
                            Todas
                        </button>
                        {categories.map((category) => (
                            <button
                                key={category.id}
                                type="button"
                                onClick={() => setCategoryFilter(category.id)}
                                className={cn(
                                    'rounded-full border px-3 py-1 text-xs font-semibold transition',
                                    categoryFilter === category.id
                                        ? 'border-slate-900 bg-slate-900 text-white'
                                        : 'border-slate-200 text-slate-600 hover:border-slate-900 hover:text-slate-900'
                                )}
                            >
                                {category.name}
                            </button>
                        ))}
                    </div>
                </div>
            </div>
            {structureQuery.isLoading ? (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {Array.from({ length: 6 }).map((_, index) => (
                        <div key={`menu-skeleton-${index}`} className="h-32 animate-pulse rounded-2xl bg-slate-100" />
                    ))}
                </div>
            ) : structureQuery.isError ? (
                <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    No pudimos cargar la carta. Intentá nuevamente en unos segundos.
                </p>
            ) : filteredItems.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-500">
                    {search.trim().length > 0 ? 'No encontramos productos con ese criterio.' : 'Agregá categorías y productos para comenzar.'}
                </div>
            ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {filteredItems.map((item) => (
                        <button
                            key={item.id}
                            type="button"
                            onClick={() => handleSelect(item)}
                            className="flex h-36 flex-col justify-between rounded-2xl border border-slate-200 bg-white p-3 text-left transition hover:border-slate-900"
                        >
                            <div>
                                <div className="flex items-center justify-between text-xs text-slate-500">
                                    <span>{item.categoryName ?? 'Sin categoría'}</span>
                                    {item.sku ? <span>SKU {item.sku}</span> : null}
                                </div>
                                <p className="mt-1 text-base font-semibold text-slate-900">{item.name}</p>
                                <p className="text-xs text-slate-400 line-clamp-2">{item.description || 'Sin descripción'}</p>
                            </div>
                            <div className="flex items-center justify-between">
                                <StockStatusBadge status={item.stockStatus} />
                                <div className="text-right">
                                    <p className="text-sm font-semibold text-slate-900">{formatCurrency(item.price)}</p>
                                    {item.stockStatus === 'out' && !allowSellWithoutStock ? (
                                        <span className="text-xs font-semibold text-rose-600">Sin stock</span>
                                    ) : null}
                                </div>
                            </div>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

function flattenStructure(categories: MenuStructureCategory[]): MenuProductSelection[] {
    return categories.flatMap((category) =>
        category.items.map((item) => {
            const typedItem = item as MenuStructureItem & {
                sku?: string | null;
                barcode?: string | null;
            };
            const derivedSku = typedItem.sku ?? typedItem.barcode ?? extractSkuFromDescription(item.description);
            return {
                id: item.id,
                name: item.name,
                sku: derivedSku,
                price: Number(item.price) || 0,
                categoryId: category.id,
                categoryName: category.name,
                description: item.description,
                stockStatus: resolveStockStatus(item),
                isAvailable: item.is_available,
            } satisfies MenuProductSelection;
        })
    );
}

function extractSkuFromDescription(description: string | null) {
    if (!description) {
        return null;
    }
    const pattern = /SKU[:\s#-]*([A-Za-z0-9-]+)/i;
    const match = description.match(pattern);
    return match ? match[1] : null;
}

function resolveStockStatus(item: MenuStructureItem): MenuStockStatus {
    const normalizedTags = (item.tags ?? []).map((tag) => tag.toLowerCase());
    const hasOutTag = normalizedTags.some((tag) => OUT_OF_STOCK_TAGS.includes(tag));
    if (hasOutTag || !item.is_available) {
        return 'out';
    }
    if (normalizedTags.some((tag) => CRITICAL_TAGS.includes(tag))) {
        return 'critical';
    }
    if (normalizedTags.some((tag) => LOW_STOCK_TAGS.includes(tag))) {
        return 'low';
    }
    return 'in';
}

function StockStatusBadge({ status }: { status: MenuStockStatus }) {
    const meta = STATUS_META[status];
    return (
        <span className={cn('inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold', meta.background, meta.text)}>
            <span className={`h-2.5 w-2.5 rounded-full ${meta.dot}`} aria-hidden />
            {meta.label}
        </span>
    );
}

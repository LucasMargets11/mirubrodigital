'use client';

/**
 * OfflineProductCatalogPanel (PR-OFF-03)
 *
 * Offline counterpart of `ProductCatalogPanel`. It renders the POS catalog from
 * the locally-persisted snapshot — it never calls any online product/category
 * API. Used on the quick-sale screen while the device is offline.
 *
 * States (driven by `catalog.status`):
 *  · loading              → "Cargando datos offline…"
 *  · offline-no-snapshot  → no data downloaded message
 *  · offline-disabled     → offline not enabled for this business
 *  · offline-ready        → category chips + product grid (local filtering)
 *
 * Search/browse filtering is done in-memory against the snapshot products.
 */

import { useMemo, useState } from 'react';
import type { PosProduct } from '@/types/pos-cash';
import { CategoryProductBrowser } from './../components/CategoryProductBrowser';
import type { PosOfflineCatalog } from './offline-catalog';
import { formatSavedAtTime } from './offline-catalog';

interface OfflineProductCatalogPanelProps {
  catalog: PosOfflineCatalog;
  onAdd: (product: PosProduct) => void;
  disabled?: boolean;
  /** Query from the main search bar — drives search mode vs browse mode. */
  searchQuery: string;
  /** Controlled: which category is currently active (null = Todas). */
  selectedCategoryId: string | null;
  /** Called when the user picks a category chip. */
  onCategorySelect: (id: string | null) => void;
}

export function OfflineProductCatalogPanel({
  catalog,
  onAdd,
  disabled = false,
  searchQuery,
  selectedCategoryId,
  onCategorySelect,
}: OfflineProductCatalogPanelProps) {
  const [inStockOnly, setInStockOnly] = useState(false);

  const { status, products, categories } = catalog;
  const isSearchMode = searchQuery.trim().length >= 2;
  const normalizedQuery = searchQuery.trim().toLowerCase();

  // ── Non-ready states ────────────────────────────────────────────────────────

  const matchingProducts = useMemo(() => {
    let list = products;
    if (isSearchMode) {
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(normalizedQuery) ||
          p.sku.toLowerCase().includes(normalizedQuery),
      );
    } else if (selectedCategoryId !== null) {
      list = list.filter((p) => p.category_id === selectedCategoryId);
    }
    if (inStockOnly) {
      list = list.filter((p) => parseFloat(p.stock_quantity) > 0);
    }
    return list;
  }, [products, isSearchMode, normalizedQuery, selectedCategoryId, inStockOnly]);

  const matchingCategories = useMemo(() => {
    if (!isSearchMode) return [];
    return categories.filter((c) => c.name.toLowerCase().includes(normalizedQuery));
  }, [categories, isSearchMode, normalizedQuery]);

  const selectedLabel =
    selectedCategoryId === null
      ? 'Todas'
      : categories.find((c) => c.id === selectedCategoryId)?.name;

  if (status === 'loading') {
    return (
      <section aria-label="Catálogo offline" className="flex flex-col gap-3">
        <p className="animate-pulse text-sm text-slate-400">Cargando datos offline…</p>
      </section>
    );
  }

  if (status === 'offline-no-snapshot') {
    return (
      <section aria-label="Catálogo offline" className="flex flex-col gap-3">
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900">
          No hay datos offline descargados. Conectate a Internet y actualizá datos offline.
        </div>
      </section>
    );
  }

  if (status === 'offline-disabled') {
    return (
      <section aria-label="Catálogo offline" className="flex flex-col gap-3">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-700">
          Modo offline no habilitado para este negocio.
        </div>
      </section>
    );
  }

  // ── Ready state ─────────────────────────────────────────────────────────────

  return (
    <section aria-label="Catálogo offline" className="flex flex-col gap-3">
      {catalog.savedAt && (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-800">
          Usando datos offline guardados el {formatSavedAtTime(catalog.savedAt)}. Las ventas
          rápidas se guardarán localmente y se sincronizarán cuando vuelva la conexión.
        </div>
      )}

      {/* Header row: title + stock toggle */}
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {isSearchMode ? `Resultados para "${searchQuery.trim()}"` : 'Explorar catálogo'}
        </h2>
        <label className="flex cursor-pointer select-none items-center gap-1.5 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={inStockOnly}
            onChange={(e) => setInStockOnly(e.target.checked)}
            disabled={disabled}
            className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
          />
          Solo con stock
        </label>
      </div>

      {isSearchMode ? (
        <>
          {matchingProducts.length === 0 && matchingCategories.length === 0 && (
            <p className="text-sm text-slate-400">
              Sin resultados para &ldquo;{searchQuery.trim()}&rdquo;.
            </p>
          )}

          {matchingCategories.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium text-slate-400">Categorías</p>
              <div className="flex flex-wrap gap-2">
                {matchingCategories.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => onCategorySelect(c.id)}
                    disabled={disabled}
                    className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-800 transition-colors hover:bg-indigo-100 disabled:opacity-60"
                  >
                    <span className="font-medium">{c.name}</span>
                    <span className="text-xs text-indigo-500">{c.products_count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {matchingProducts.length > 0 && (
            <div>
              {matchingCategories.length > 0 && (
                <p className="mb-2 text-xs font-medium text-slate-400">Productos</p>
              )}
              <CategoryProductBrowser
                products={matchingProducts}
                loading={false}
                onAdd={onAdd}
                disabled={disabled}
              />
            </div>
          )}
        </>
      ) : (
        <>
          {/* Category chips */}
          {categories.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => onCategorySelect(null)}
                disabled={disabled}
                className={[
                  'rounded-full px-3 py-1 text-xs font-medium transition-colors disabled:opacity-60',
                  selectedCategoryId === null
                    ? 'bg-slate-800 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                ].join(' ')}
              >
                Todas
              </button>
              {categories.map((cat) => (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => onCategorySelect(cat.id)}
                  disabled={disabled}
                  className={[
                    'rounded-full px-3 py-1 text-xs font-medium transition-colors disabled:opacity-60',
                    selectedCategoryId === cat.id
                      ? 'bg-slate-800 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
                  ].join(' ')}
                >
                  {cat.name}
                  {cat.products_count > 0 && (
                    <span
                      className={[
                        'ml-1',
                        selectedCategoryId === cat.id ? 'opacity-70' : 'text-slate-400',
                      ].join(' ')}
                    >
                      {cat.products_count}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}

          <CategoryProductBrowser
            products={matchingProducts}
            loading={false}
            onAdd={onAdd}
            disabled={disabled}
            categoryLabel={selectedLabel}
          />
        </>
      )}
    </section>
  );
}

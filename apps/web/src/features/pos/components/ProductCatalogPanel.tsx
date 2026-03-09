'use client';

/**
 * ProductCatalogPanel
 *
 * Catalog area below the search bar.
 *
 * Two modes:
 *  · Browse  (searchQuery < 2 chars): category chips + product grid
 *  · Search  (searchQuery ≥ 2 chars): inline unified results
 *    – matching categories shown as clickable chips
 *    – matching products shown in the same product grid
 *
 * No inner search input. No sidebar. All driven by searchQuery from above.
 */

import { useState } from 'react';
import {
  usePosCategories,
  usePosBrowseProducts,
  useUnifiedProductSearch,
} from '@/features/pos/cash-hooks';
import type { PosProduct } from '@/types/pos-cash';
import type { UnifiedSearchResult } from '@/features/pos/search-ranking';
import { CategoryProductBrowser } from './CategoryProductBrowser';

interface ProductCatalogPanelProps {
  onAdd: (product: PosProduct) => void;
  disabled?: boolean;
  /** Query from the main search bar — drives search mode vs browse mode. */
  searchQuery: string;
  /** Controlled: which category is currently active (null = Todas). */
  selectedCategoryId: string | null;
  /** Called when the user picks a category (chip or search result). */
  onCategorySelect: (id: string | null) => void;
}

export function ProductCatalogPanel({
  onAdd,
  disabled = false,
  searchQuery,
  selectedCategoryId,
  onCategorySelect,
}: ProductCatalogPanelProps) {
  const [inStockOnly, setInStockOnly] = useState(false);

  const isSearchMode = searchQuery.trim().length >= 2;

  // ── Browse mode data ──────────────────────────────────────────────────────

  const categoriesQuery = usePosCategories();
  const categories = categoriesQuery.data?.results ?? [];

  const browseQuery = usePosBrowseProducts(
    isSearchMode ? null : selectedCategoryId,
    '',
    inStockOnly,
  );
  const browseProducts = browseQuery.data?.results ?? [];

  const selectedLabel =
    selectedCategoryId === null
      ? 'Todas'
      : categories.find((c) => c.id === selectedCategoryId)?.name;

  // ── Search mode data ──────────────────────────────────────────────────────

  const { results: rawResults, isLoading: searchLoading } = useUnifiedProductSearch(searchQuery);

  // Apply stock filter client-side for search results
  const searchResults = inStockOnly
    ? rawResults.filter(
        (r) => r.type === 'category' || parseFloat(r.data.stock_quantity) > 0,
      )
    : rawResults;

  const categoryResults = searchResults.filter(
    (r): r is Extract<UnifiedSearchResult, { type: 'category' }> => r.type === 'category',
  );
  const productResults = searchResults
    .filter((r): r is Extract<UnifiedSearchResult, { type: 'product' }> => r.type === 'product')
    .map((r) => r.data);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <section aria-label="Catálogo de productos" className="flex flex-col gap-3">
      {/* ── Header row: title + stock toggle ──────────────────────────── */}
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
        /* ── Search results view ──────────────────────────────────────── */
        <>
          {searchLoading && (
            <p className="animate-pulse text-xs text-slate-400">Buscando…</p>
          )}

          {!searchLoading && searchResults.length === 0 && (
            <p className="text-sm text-slate-400">
              Sin resultados para &ldquo;{searchQuery.trim()}&rdquo;.
            </p>
          )}

          {/* Category hits */}
          {categoryResults.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium text-slate-400">Categorías</p>
              <div className="flex flex-wrap gap-2">
                {categoryResults.map((r) => (
                  <button
                    key={r.data.id}
                    type="button"
                    onClick={() => onCategorySelect(r.data.id)}
                    disabled={disabled}
                    className="flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-800 transition-colors hover:bg-indigo-100 disabled:opacity-60"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      className="h-4 w-4 shrink-0 text-indigo-500"
                      aria-hidden="true"
                    >
                      <path
                        fillRule="evenodd"
                        d="M2 4.75C2 3.784 2.784 3 3.75 3h12.5c.966 0 1.75.784 1.75 1.75v2.5A1.75 1.75 0 0116.25 9H3.75A1.75 1.75 0 012 7.25v-2.5zm1.75-.25a.25.25 0 00-.25.25v2.5c0 .138.112.25.25.25h12.5a.25.25 0 00.25-.25v-2.5a.25.25 0 00-.25-.25H3.75zM2 12.75c0-.966.784-1.75 1.75-1.75h12.5c.966 0 1.75.784 1.75 1.75v2.5A1.75 1.75 0 0116.25 17H3.75A1.75 1.75 0 012 15.25v-2.5zm1.75-.25a.25.25 0 00-.25.25v2.5c0 .138.112.25.25.25h12.5a.25.25 0 00.25-.25v-2.5a.25.25 0 00-.25-.25H3.75z"
                        clipRule="evenodd"
                      />
                    </svg>
                    <span className="font-medium">{r.data.name}</span>
                    <span className="text-xs text-indigo-500">{r.data.products_count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Product hits */}
          {productResults.length > 0 && (
            <div>
              {categoryResults.length > 0 && (
                <p className="mb-2 text-xs font-medium text-slate-400">Productos</p>
              )}
              <CategoryProductBrowser
                products={productResults}
                loading={false}
                onAdd={onAdd}
                disabled={disabled}
              />
            </div>
          )}
        </>
      ) : (
        /* ── Browse view ──────────────────────────────────────────────── */
        <>
          {/* Category chips */}
          {categoriesQuery.isLoading ? (
            <div className="flex gap-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-7 w-20 animate-pulse rounded-full bg-slate-100" />
              ))}
            </div>
          ) : categories.length > 0 ? (
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
          ) : null}

          {/* Products in selected category */}
          <CategoryProductBrowser
            products={browseProducts}
            loading={browseQuery.isFetching && browseProducts.length === 0}
            onAdd={onAdd}
            disabled={disabled}
            categoryLabel={selectedLabel}
          />
        </>
      )}
    </section>
  );
}


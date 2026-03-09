'use client';

/**
 * ProductSearchPanel
 *
 * Controlled search input for the POS New Sale screen.
 * Results are displayed inline in the catalog panel below — no dropdown.
 */

import { useRef } from 'react';

interface ProductSearchPanelProps {
  query: string;
  onQueryChange: (q: string) => void;
  disabled?: boolean;
  /** Pass a ref to give the parent control over autofocus. */
  inputRef?: React.RefObject<HTMLInputElement>;
}

export function ProductSearchPanel({
  query,
  onQueryChange,
  disabled,
  inputRef,
}: ProductSearchPanelProps) {
  const localRef = useRef<HTMLInputElement>(null);
  const resolvedRef = inputRef ?? localRef;

  return (
    <div>
      <label htmlFor="product-search-input" className="sr-only">
        Buscar producto o categoría por nombre, SKU o código de barras
      </label>
      <input
        id="product-search-input"
        ref={resolvedRef}
        type="search"
        autoComplete="off"
        placeholder="Buscar producto o categoría…"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        disabled={disabled}
        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-base text-slate-900 placeholder-slate-400 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200 disabled:opacity-60"
        autoFocus
      />
    </div>
  );
}

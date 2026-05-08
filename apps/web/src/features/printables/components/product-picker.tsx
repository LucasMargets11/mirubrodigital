'use client';

import { useMemo, useState } from 'react';

import { useProducts } from '@/features/gestion/hooks';
import type { Product } from '@/features/gestion/types';
import { formatCurrency } from '@/lib/format';

type ProductPickerProps = {
  onSelect: (product: Product | null) => void;
  selected: Product | null;
};

export function ProductPicker({ onSelect, selected }: ProductPickerProps) {
  const [search, setSearch] = useState('');

  const productsQuery = useProducts(search, false);
  const products = useMemo(
    () => (productsQuery.data ?? []).filter((p) => p.is_active),
    [productsQuery.data],
  );

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-slate-700">
        Producto <span className="text-slate-400 font-normal">(opcional)</span>
      </label>

      {selected ? (
        <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-slate-900">{selected.name}</p>
            <p className="text-xs text-slate-500">
              {selected.sku ? <span className="mr-2">SKU: {selected.sku}</span> : null}
              {selected.price ? <span>{formatCurrency(selected.price)}</span> : null}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="ml-3 shrink-0 text-xs text-slate-500 underline hover:text-slate-900"
          >
            Cambiar
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar producto…"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/20"
          />

          {productsQuery.isLoading ? (
            <p className="text-xs text-slate-400">Cargando productos…</p>
          ) : products.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
              {search
                ? 'No se encontraron productos con ese nombre.'
                : 'No hay productos activos cargados todavía. Cargá productos para generar carteles.'}
            </p>
          ) : (
            <ul className="max-h-48 overflow-y-auto rounded-lg border border-slate-200 divide-y divide-slate-100">
              {products.map((product) => (
                <li key={product.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(product)}
                    className="w-full px-3 py-2 text-left hover:bg-slate-50 transition-colors"
                  >
                    <span className="block text-sm font-medium text-slate-900 truncate">
                      {product.name}
                    </span>
                    <span className="text-xs text-slate-500">
                      {product.sku ? <span className="mr-2">SKU: {product.sku}</span> : null}
                      {product.price ? formatCurrency(product.price) : null}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          <p className="text-xs text-slate-400">
            También podés generar un cartel manual sin seleccionar producto, siempre que completes el título.
          </p>
        </div>
      )}
    </div>
  );
}

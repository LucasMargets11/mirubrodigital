'use client';

/**
 * CategoryProductBrowser
 *
 * Scrollable grid of product cards for the selected category.
 * Each card shows name, SKU, price, stock badge, and an "Agregar" button.
 *
 * Keyboard:
 * - Tab moves between cards and buttons normally.
 * - Enter / Space on the "Agregar" button adds the item to the cart.
 *
 * The component is stateless — it receives all data and callbacks as props.
 */

import { formatCurrency } from '@/features/cash/utils';
import type { PosProduct } from '@/types/pos-cash';
import { getStockStatus, StockBadge } from './StockBadge';

interface CategoryProductBrowserProps {
  products: PosProduct[];
  loading?: boolean;
  onAdd: (product: PosProduct) => void;
  disabled?: boolean;
  /** Category name shown in the empty/loading state */
  categoryLabel?: string;
}

export function CategoryProductBrowser({
  products,
  loading = false,
  onAdd,
  disabled = false,
  categoryLabel,
}: CategoryProductBrowserProps) {
  if (loading) {
    return (
      <ul
        aria-label="Cargando productos"
        className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3"
      >
        {[...Array(6)].map((_, i) => (
          <li key={i} className="h-24 animate-pulse rounded-xl bg-slate-100" />
        ))}
      </ul>
    );
  }

  if (products.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-slate-400">
        {categoryLabel
          ? `No hay productos en "${categoryLabel}".`
          : 'No hay productos.'}
      </p>
    );
  }

  return (
    <ul
      aria-label={
        categoryLabel
          ? `Productos en ${categoryLabel}`
          : 'Todos los productos'
      }
      className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3"
    >
      {products.map((product) => (
        <ProductCard
          key={product.id}
          product={product}
          onAdd={onAdd}
          disabled={disabled}
        />
      ))}
    </ul>
  );
}

// ── ProductCard ───────────────────────────────────────────────────────────────

interface ProductCardProps {
  product: PosProduct;
  onAdd: (p: PosProduct) => void;
  disabled?: boolean;
}

function ProductCard({ product, onAdd, disabled = false }: ProductCardProps) {
  const stockStatus = getStockStatus(product.stock_quantity, product.stock_min);
  const isOutOfStock = stockStatus === 'out';
  const canAdd = !disabled && !isOutOfStock;

  return (
    <li>
      <button
        type="button"
        onClick={() => canAdd && onAdd(product)}
        disabled={!canAdd}
        aria-label={`Agregar ${product.name} al carrito`}
        className={[
          'flex w-full flex-col gap-1.5 rounded-xl border p-3 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1',
          isOutOfStock
            ? 'cursor-not-allowed border-slate-100 bg-slate-50 opacity-60'
            : 'border-slate-200 bg-white hover:border-indigo-300 hover:bg-indigo-50 hover:shadow-sm active:bg-indigo-100',
        ].join(' ')}
      >
        {/* Name */}
        <div className="flex items-start justify-between gap-1">
          <span
            className="line-clamp-2 flex-1 text-sm font-semibold leading-snug text-slate-800"
            title={product.name}
          >
            {product.name}
          </span>
          <StockBadge
            stockQuantity={product.stock_quantity}
            stockMin={product.stock_min}
            showQty
            className="mt-0.5 shrink-0"
          />
        </div>

        {/* SKU */}
        {product.sku && (
          <span className="text-xs text-slate-400">SKU: {product.sku}</span>
        )}

        {/* Price */}
        <div className="mt-auto pt-1">
          <span className="text-sm font-semibold text-slate-700">
            {formatCurrency(product.price)}
          </span>
        </div>
      </button>
    </li>
  );
}

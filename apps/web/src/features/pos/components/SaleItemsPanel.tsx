'use client';

/**
 * SaleItemsPanel
 *
 * Displays the current cart items with quantity controls and a footer summary.
 * Shows an empty state when the cart is empty.
 *
 * Accessibility:
 * - The items list is a <ul> with role exposed via SaleItemRow.
 * - Footer totals use <dl> for key/value semantics.
 */

import { formatCurrency } from '@/features/cash/utils';
import type { PosProduct } from '@/types/pos-cash';
import { SaleItemRow } from './SaleItemRow';

export interface CartItem {
  product: PosProduct;
  quantity: number;
  note?: string;
}

interface SaleItemsPanelProps {
  items: CartItem[];
  onChangeQty: (productId: string, delta: number) => void;
  onSetQty: (productId: string, qty: number) => void;
  onRemove: (productId: string) => void;
  subtotal: number;
  itemCount: number;
  disabled?: boolean;
}

export function SaleItemsPanel({
  items,
  onChangeQty,
  onSetQty,
  onRemove,
  subtotal,
  itemCount,
  disabled,
}: SaleItemsPanelProps) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 py-10 text-center">
        <p className="text-3xl" aria-hidden>
          🛒
        </p>
        <p className="mt-2 text-sm font-medium text-slate-500">Sin productos</p>
        <p className="mt-0.5 text-xs text-slate-400">
          Usá el buscador para agregar productos a la venta.
        </p>
      </div>
    );
  }

  return (
    <section aria-label="Productos en la venta">
      <ul
        className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white"
        aria-label={`${itemCount} producto${itemCount !== 1 ? 's' : ''} en la venta`}
      >
        {items.map((item) => (
          <SaleItemRow
            key={item.product.id}
            product={item.product}
            quantity={item.quantity}
            onChangeQty={(delta) => onChangeQty(item.product.id, delta)}
            onSetQty={(qty) => onSetQty(item.product.id, qty)}
            onRemove={() => onRemove(item.product.id)}
            disabled={disabled}
          />
        ))}
      </ul>

      {/* Footer totals */}
      <dl className="mt-3 flex items-center justify-between px-1 text-sm">
        <div className="flex gap-1">
          <dt className="text-slate-500">
            {itemCount} {itemCount === 1 ? 'ítem' : 'ítems'}
          </dt>
        </div>
        <div className="flex items-baseline gap-2">
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Subtotal
          </dt>
          <dd className="text-base font-bold text-slate-900 tabular-nums">
            {formatCurrency(String(subtotal))}
          </dd>
        </div>
      </dl>
    </section>
  );
}

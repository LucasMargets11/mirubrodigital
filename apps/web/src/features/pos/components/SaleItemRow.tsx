'use client';

/**
 * SaleItemRow
 *
 * One row in the cart / sell-items list.
 * Allows quantity increment/decrement, manual qty editing, and removal.
 *
 * Accessibility:
 * - Qty buttons have aria-label with product name.
 * - Manual qty input has an associated label.
 * - Remove button has an aria-label.
 */

import { useState } from 'react';
import { formatCurrency } from '@/features/cash/utils';
import type { PosProduct } from '@/types/pos-cash';

interface SaleItemRowProps {
  product: PosProduct;
  quantity: number;
  onChangeQty: (delta: number) => void;
  onSetQty: (qty: number) => void;
  onRemove: () => void;
  disabled?: boolean;
}

export function SaleItemRow({
  product,
  quantity,
  onChangeQty,
  onSetQty,
  onRemove,
  disabled,
}: SaleItemRowProps) {
  const [editing, setEditing] = useState(false);
  const [draftQty, setDraftQty] = useState(String(quantity));

  const lineTotal = parseFloat(product.price) * quantity;

  function commitEdit() {
    const parsed = parseInt(draftQty, 10);
    if (!isNaN(parsed) && parsed >= 1) {
      onSetQty(parsed);
    } else if (parsed === 0) {
      onRemove();
    } else {
      // Reset invalid input
      setDraftQty(String(quantity));
    }
    setEditing(false);
  }

  return (
    <li className="flex items-center gap-3 px-4 py-3">
      {/* Product info */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-900">{product.name}</p>
        {product.sku && (
          <p className="text-xs text-slate-400">SKU: {product.sku}</p>
        )}
      </div>

      {/* Unit price */}
      <span className="hidden w-20 shrink-0 text-right text-xs text-slate-500 tabular-nums sm:block">
        {formatCurrency(product.price)}
      </span>

      {/* Qty controls */}
      <div className="flex shrink-0 items-center gap-1.5" role="group" aria-label={`Cantidad de ${product.name}`}>
        <button
          type="button"
          onClick={() => onChangeQty(-1)}
          disabled={disabled}
          aria-label={`Reducir cantidad de ${product.name}`}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 text-sm font-bold text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-50"
        >
          −
        </button>

        {editing ? (
          <input
            type="number"
            min={1}
            value={draftQty}
            onChange={(e) => setDraftQty(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitEdit();
              if (e.key === 'Escape') {
                setDraftQty(String(quantity));
                setEditing(false);
              }
            }}
            aria-label={`Cantidad de ${product.name}`}
            className="h-7 w-12 rounded border border-slate-300 text-center text-sm tabular-nums focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-300"
            // eslint-disable-next-line jsx-a11y/no-autofocus
            autoFocus
          />
        ) : (
          <button
            type="button"
            onClick={() => {
              setDraftQty(String(quantity));
              setEditing(true);
            }}
            disabled={disabled}
            aria-label={`Cantidad: ${quantity}. Hacer clic para editar`}
            className="flex h-7 w-10 items-center justify-center rounded border border-transparent text-sm font-semibold tabular-nums text-slate-800 hover:border-slate-200 hover:bg-slate-50"
          >
            {quantity}
          </button>
        )}

        <button
          type="button"
          onClick={() => onChangeQty(+1)}
          disabled={disabled}
          aria-label={`Aumentar cantidad de ${product.name}`}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 text-sm font-bold text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-50"
        >
          +
        </button>
      </div>

      {/* Line total */}
      <span className="w-20 shrink-0 text-right text-sm font-semibold text-slate-800 tabular-nums">
        {formatCurrency(String(lineTotal))}
      </span>

      {/* Remove */}
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        aria-label={`Quitar ${product.name} del carrito`}
        className="ml-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-300 transition-colors hover:bg-rose-50 hover:text-rose-500 disabled:opacity-50"
      >
        <span aria-hidden>✕</span>
      </button>
    </li>
  );
}

'use client';

/**
 * StockBadge
 *
 * Displays a colour-coded label describing a product's stock level.
 *
 * Stock status logic:
 *  - out   stock_quantity <= 0
 *  - low   0 < stock_quantity <= stock_min  (or <= LOW_THRESHOLD when stock_min == 0)
 *  - ok    stock_quantity > stock_min      (or > LOW_THRESHOLD when stock_min == 0)
 */

const LOW_THRESHOLD = 5; // fallback when stock_min is zero

export type StockStatus = 'ok' | 'low' | 'out';

/**
 * Determine `StockStatus` from raw decimal strings coming from the API.
 * @param stockQuantity  product.stock_quantity (decimal string)
 * @param stockMin       product.stock_min      (decimal string, may be "0")
 */
export function getStockStatus(
  stockQuantity: string,
  stockMin: string = '0',
): StockStatus {
  const qty = parseFloat(stockQuantity);
  const min = parseFloat(stockMin);

  if (isNaN(qty) || qty <= 0) return 'out';

  const threshold = min > 0 ? min : LOW_THRESHOLD;
  return qty <= threshold ? 'low' : 'ok';
}

interface StockBadgeProps {
  stockQuantity: string;
  stockMin?: string;
  /** Show numeric quantity alongside the label. Default false. */
  showQty?: boolean;
  className?: string;
}

export function StockBadge({
  stockQuantity,
  stockMin = '0',
  showQty = false,
  className = '',
}: StockBadgeProps) {
  const status = getStockStatus(stockQuantity, stockMin);
  const qty = parseFloat(stockQuantity);
  const displayQty = isNaN(qty) ? 0 : Math.floor(qty);

  const config: Record<
    StockStatus,
    { label: string; classes: string; dot: string }
  > = {
    ok: {
      label: 'En stock',
      classes:
        'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
      dot: 'bg-emerald-500',
    },
    low: {
      label: 'Stock bajo',
      classes:
        'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
      dot: 'bg-amber-400',
    },
    out: {
      label: 'Sin stock',
      classes:
        'bg-red-50 text-red-600 ring-1 ring-red-200',
      dot: 'bg-red-400',
    },
  };

  const { label, classes, dot } = config[status];

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${classes} ${className}`}
      title={showQty ? `${displayQty} unidades` : label}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${dot}`}
        aria-hidden="true"
      />
      {label}
      {showQty && status !== 'out' && (
        <span className="ml-0.5 opacity-70">({displayQty})</span>
      )}
    </span>
  );
}

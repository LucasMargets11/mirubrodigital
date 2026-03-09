'use client';

/**
 * DiscountPanel
 *
 * Toggle + type selector + value input for applying a discount to the sale.
 *
 * Accessibility:
 * - Uses <fieldset>/<legend> for the whole panel.
 * - Switch/checkbox has an explicit <label>.
 * - Discount type and value inputs have labels.
 * - Validation errors are associated via aria-describedby and shown with role="alert".
 */

import { formatCurrency } from '@/features/cash/utils';

export type DiscountType = 'percent' | 'fixed';

interface DiscountPanelProps {
  enabled: boolean;
  onEnabledChange: (v: boolean) => void;
  type: DiscountType;
  onTypeChange: (v: DiscountType) => void;
  value: string;
  onValueChange: (v: string) => void;
  subtotal: number;
  discountAmount: number;
  disabled?: boolean;
  /** Validation error message */
  error?: string;
}

export function DiscountPanel({
  enabled,
  onEnabledChange,
  type,
  onTypeChange,
  value,
  onValueChange,
  subtotal,
  discountAmount,
  disabled,
  error,
}: DiscountPanelProps) {
  return (
    <fieldset>
      <legend className="sr-only">Descuento</legend>

      {/* Toggle */}
      <div className="flex items-center justify-between">
        <label htmlFor="discount-toggle" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Descuento
        </label>
        <button
          id="discount-toggle"
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => onEnabledChange(!enabled)}
          disabled={disabled}
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-1 disabled:opacity-60 ${
            enabled ? 'bg-slate-800' : 'bg-slate-200'
          }`}
          aria-label="Aplicar descuento"
        >
          <span
            aria-hidden
            className={`pointer-events-none block h-4 w-4 rounded-full bg-white shadow-sm ring-0 transition-transform ${
              enabled ? 'translate-x-5' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>

      {/* Discount controls (visible when enabled) */}
      {enabled && (
        <div className="mt-3 space-y-3">
          {/* Type selector */}
          <div className="flex gap-2" role="group" aria-label="Tipo de descuento">
            {[
              { value: 'percent' as DiscountType, label: 'Porcentaje (%)' },
              { value: 'fixed' as DiscountType, label: 'Monto fijo ($)' },
            ].map(({ value: v, label }) => (
              <label
                key={v}
                className={`flex flex-1 cursor-pointer items-center justify-center rounded-lg border px-2 py-2 text-xs font-medium transition-colors ${
                  type === v
                    ? 'border-slate-800 bg-slate-900 text-white'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                } ${disabled ? 'pointer-events-none opacity-60' : ''}`}
              >
                <input
                  type="radio"
                  name="discount-type"
                  value={v}
                  checked={type === v}
                  onChange={() => onTypeChange(v)}
                  disabled={disabled}
                  className="sr-only"
                />
                {label}
              </label>
            ))}
          </div>

          {/* Value input */}
          <div>
            <label htmlFor="discount-value" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
              {type === 'percent' ? 'Porcentaje de descuento' : 'Monto de descuento'}
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-medium text-slate-400" aria-hidden>
                {type === 'percent' ? '%' : '$'}
              </span>
              <input
                id="discount-value"
                type="number"
                min={0}
                max={type === 'percent' ? 100 : undefined}
                step="any"
                value={value}
                onChange={(e) => onValueChange(e.target.value)}
                disabled={disabled}
                aria-describedby={error ? 'discount-error' : undefined}
                className="w-full rounded-xl border border-slate-200 py-2 pl-8 pr-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60"
              />
            </div>

            {/* Inline preview */}
            {discountAmount > 0 && !error && (
              <p className="mt-1 text-xs text-emerald-600" aria-live="polite">
                Descuento: − {formatCurrency(String(discountAmount))}
              </p>
            )}

            {/* Validation error */}
            {error && (
              <p id="discount-error" role="alert" className="mt-1 text-xs text-rose-500">
                {error}
              </p>
            )}
          </div>
        </div>
      )}
    </fieldset>
  );
}

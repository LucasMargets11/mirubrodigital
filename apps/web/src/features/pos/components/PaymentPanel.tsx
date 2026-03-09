'use client';

/**
 * PaymentPanel
 *
 * Payment method selector + conditional extra fields (cash received / reference).
 *
 * UI payment options → API mapping:
 *   efectivo     → 'cash'
 *   mercadopago  → 'transfer'
 *   debito       → 'card'
 *   credito      → 'card'
 *   transferencia → 'transfer'
 *   otro         → 'other'
 *
 * The API only has 4 values: cash | card | transfer | other.
 * The UI shows more granularity for the operator; the mapping happens on submit.
 *
 * Accessibility:
 * - Payment options use a radio group with <fieldset>/<legend>.
 * - Cash received input has a label and shows live vuelto feedback.
 * - The vuelto alert uses aria-live="polite".
 */

import { formatCurrency } from '@/features/cash/utils';

/** UI-level payment method (more granular than the API enum) */
export type UiPaymentMethod = 'efectivo' | 'debito' | 'credito' | 'transferencia' | 'mercadopago' | 'otro';

/** Maps UI payment method to backend API enum */
export function toApiPaymentMethod(
  m: UiPaymentMethod,
): 'cash' | 'card' | 'transfer' | 'other' {
  switch (m) {
    case 'efectivo':
      return 'cash';
    case 'debito':
    case 'credito':
      return 'card';
    case 'transferencia':
    case 'mercadopago':
      return 'transfer';
    case 'otro':
      return 'other';
  }
}

const PAYMENT_OPTIONS: { value: UiPaymentMethod; label: string; icon: string }[] = [
  { value: 'efectivo',      label: 'Efectivo',        icon: '💵' },
  { value: 'debito',        label: 'Tarjeta débito',    icon: '💳' },
  { value: 'credito',       label: 'Tarjeta crédito',   icon: '💳' },
  { value: 'transferencia', label: 'Transferencia',    icon: '🏦' },
  { value: 'mercadopago',   label: 'Mercado Pago',     icon: '💙' },
  { value: 'otro',          label: 'Otro',             icon: '•' },
];

interface PaymentPanelProps {
  method: UiPaymentMethod;
  onMethodChange: (m: UiPaymentMethod) => void;
  cashReceived: string;
  onCashReceivedChange: (v: string) => void;
  cashChange: number;
  total: number;
  disabled?: boolean;
  cashError?: string;
}

export function PaymentPanel({
  method,
  onMethodChange,
  cashReceived,
  onCashReceivedChange,
  cashChange,
  total,
  disabled,
  cashError,
}: PaymentPanelProps) {
  const isCash = method === 'efectivo';
  const cashReceivedNum = parseFloat(cashReceived);
  const cashInsufficient = isCash && !isNaN(cashReceivedNum) && cashReceivedNum < total && cashReceivedNum > 0;

  return (
    <fieldset>
      <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Medio de pago
      </legend>

      {/* Options grid */}
      <div className="grid grid-cols-3 gap-2">
        {PAYMENT_OPTIONS.map(({ value, label, icon }) => (
          <label
            key={value}
            className={`flex cursor-pointer flex-col items-center gap-1 rounded-xl border px-2 py-2.5 text-center text-xs font-medium transition-colors ${
              method === value
                ? 'border-slate-800 bg-slate-900 text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            } ${disabled ? 'pointer-events-none opacity-60' : ''}`}
          >
            <input
              type="radio"
              name="pos-payment-method"
              value={value}
              checked={method === value}
              onChange={() => onMethodChange(value)}
              disabled={disabled}
              className="sr-only"
            />
            <span aria-hidden className="text-base leading-none">{icon}</span>
            <span>{label}</span>
          </label>
        ))}
      </div>

      {/* Cash received (only for efectivo) */}
      {isCash && (
        <div className="mt-4 space-y-3">
          <div>
            <label
              htmlFor="cash-received"
              className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500"
            >
              Monto recibido
            </label>
            <div className="relative">
              <span
                className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-medium text-slate-400"
                aria-hidden
              >
                $
              </span>
              <input
                id="cash-received"
                type="number"
                min={0}
                step="any"
                placeholder={String(total > 0 ? Math.ceil(total) : '')}
                value={cashReceived}
                onChange={(e) => onCashReceivedChange(e.target.value)}
                disabled={disabled}
                aria-describedby={cashError ? 'cash-received-error' : undefined}
                className={`w-full rounded-xl border py-2.5 pl-8 pr-3 text-sm text-slate-900 outline-none focus:ring-1 disabled:opacity-60 ${
                  cashError
                    ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-200'
                    : 'border-slate-200 focus:border-slate-400 focus:ring-slate-300'
                }`}
              />
            </div>

            {cashError && (
              <p id="cash-received-error" role="alert" className="mt-1 text-xs text-rose-500">
                {cashError}
              </p>
            )}
          </div>

          {/* Vuelto */}
          {!isNaN(cashReceivedNum) && cashReceivedNum > 0 && !cashInsufficient && (
            <div
              className="flex items-center justify-between rounded-xl bg-emerald-50 px-4 py-3"
              aria-live="polite"
              aria-atomic="true"
            >
              <span className="text-sm font-medium text-emerald-700">Vuelto</span>
              <span className="text-lg font-bold text-emerald-800 tabular-nums">
                {formatCurrency(String(cashChange))}
              </span>
            </div>
          )}

          {cashInsufficient && (
            <p className="text-xs text-amber-600" aria-live="polite">
              El monto recibido es menor al total.
            </p>
          )}
        </div>
      )}
    </fieldset>
  );
}

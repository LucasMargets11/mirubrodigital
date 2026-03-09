'use client';

/**
 * PosSaleModal
 *
 * Minimal POS sale creation modal for the terminal page.
 *
 * - Product search: live search against /api/v1/pos/catalog/products/ (X-Employee-Token).
 * - Cart: add/remove products, adjust quantity.
 * - Payment method selector.
 * - Submit → POST /api/v1/pos/sales/ (cash session auto-assigned server-side).
 * - On success: shows feedback for 1.5s then calls onSuccess().
 *
 * Admin cookie auth is never used here.
 */

import { useEffect, useRef, useState } from 'react';
import { Modal } from '@/components/ui/modal';
import {
  usePosCreateSale,
  usePosErrorHandler,
  usePosProducts,
} from '@/features/pos/cash-hooks';
import { formatCurrency } from '@/features/cash/utils';
import type { PosProduct, PosSaleItemPayload } from '@/types/pos-cash';

// ── Types ─────────────────────────────────────────────────────────────────────

type CartItem = {
  product: PosProduct;
  quantity: number;
};

type PaymentMethod = 'cash' | 'transfer' | 'card' | 'other';

const PAYMENT_OPTIONS: { value: PaymentMethod; label: string }[] = [
  { value: 'cash',     label: 'Efectivo' },
  { value: 'card',     label: 'Tarjeta' },
  { value: 'transfer', label: 'Transferencia' },
  { value: 'other',    label: 'Otro' },
];

// ── Props ─────────────────────────────────────────────────────────────────────

interface PosSaleModalProps {
  open: boolean;
  onClose: () => void;
  /** Called after a sale is successfully created. */
  onSuccess: () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function PosSaleModal({ open, onClose, onSuccess }: PosSaleModalProps) {
  const [search, setSearch] = useState('');
  const [cart, setCart] = useState<CartItem[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('cash');
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const searchInputRef = useRef<HTMLInputElement>(null);
  const handleError = usePosErrorHandler();
  const createSaleMutation = usePosCreateSale();
  const productsQuery = usePosProducts(search);

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setSearch('');
      setCart([]);
      setPaymentMethod('cash');
      setError('');
      setSuccessMsg('');
      setTimeout(() => searchInputRef.current?.focus(), 80);
    }
  }, [open]);

  // ── Cart helpers ─────────────────────────────────────────────────────────

  function addToCart(product: PosProduct) {
    setCart((prev) => {
      const existing = prev.find((i) => i.product.id === product.id);
      if (existing) {
        return prev.map((i) =>
          i.product.id === product.id ? { ...i, quantity: i.quantity + 1 } : i,
        );
      }
      return [...prev, { product, quantity: 1 }];
    });
  }

  function removeFromCart(productId: string) {
    setCart((prev) => prev.filter((i) => i.product.id !== productId));
  }

  function changeQty(productId: string, delta: number) {
    setCart((prev) =>
      prev
        .map((i) =>
          i.product.id === productId ? { ...i, quantity: Math.max(0, i.quantity + delta) } : i,
        )
        .filter((i) => i.quantity > 0),
    );
  }

  const total = cart.reduce((sum, item) => {
    return sum + parseFloat(item.product.price) * item.quantity;
  }, 0);

  // ── Submit ────────────────────────────────────────────────────────────────

  async function handleSubmit() {
    if (cart.length === 0) {
      setError('Agregá al menos un producto.');
      return;
    }
    setError('');

    const items: PosSaleItemPayload[] = cart.map((item) => ({
      product_id: item.product.id,
      quantity: item.quantity,
    }));

    try {
      const result = await createSaleMutation.mutateAsync({
        payment_method: paymentMethod,
        items,
      });

      setSuccessMsg(`Venta #${result.sale.number} registrada · ${formatCurrency(result.sale.total)}`);
      setTimeout(() => {
        setSuccessMsg('');
        onSuccess();
      }, 1500);
    } catch (err) {
      setError(handleError(err));
    }
  }

  const isPending = createSaleMutation.isPending;
  const products = productsQuery.data?.results ?? [];

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Modal open={open} onClose={onClose} title="Nueva venta">
      {/* Success feedback */}
      {successMsg && (
        <div className="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-center text-sm font-semibold text-emerald-700">
          ✓ {successMsg}
        </div>
      )}

      <div className="space-y-5">
        {/* Product search */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">
            Buscar producto
          </label>
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Nombre o código de producto…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300"
            disabled={isPending}
          />
          {search.length > 0 && search.length < 2 && (
            <p className="mt-1 text-xs text-slate-400">Escribí al menos 2 caracteres para buscar.</p>
          )}
          {productsQuery.isLoading && (
            <p className="mt-1 text-xs text-slate-400 animate-pulse">Buscando…</p>
          )}
          {products.length > 0 && (
            <ul className="mt-1 max-h-40 overflow-y-auto rounded-xl border border-slate-100 bg-white shadow-sm divide-y divide-slate-50">
              {products.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => addToCart(p)}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50"
                  >
                    <span className="font-medium text-slate-800">{p.name}</span>
                    <span className="ml-2 shrink-0 text-slate-500">
                      {formatCurrency(p.price)}
                      <span className="ml-2 text-xs text-slate-400">
                        stock: {p.stock_quantity}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {search.length >= 2 && !productsQuery.isLoading && products.length === 0 && (
            <p className="mt-2 text-xs text-slate-400 text-center">Sin resultados para "{search}"</p>
          )}
        </div>

        {/* Cart */}
        {cart.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">Carrito</p>
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-100 bg-slate-50">
              {cart.map((item) => (
                <li key={item.product.id} className="flex items-center justify-between px-3 py-2">
                  <span className="text-sm font-medium text-slate-800">{item.product.name}</span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => changeQty(item.product.id, -1)}
                      className="h-6 w-6 rounded-full border border-slate-200 text-slate-600 hover:bg-slate-100 text-xs font-bold"
                      disabled={isPending}
                    >
                      −
                    </button>
                    <span className="w-6 text-center text-sm tabular-nums">{item.quantity}</span>
                    <button
                      type="button"
                      onClick={() => changeQty(item.product.id, +1)}
                      className="h-6 w-6 rounded-full border border-slate-200 text-slate-600 hover:bg-slate-100 text-xs font-bold"
                      disabled={isPending}
                    >
                      +
                    </button>
                    <span className="w-20 text-right text-sm text-slate-600 tabular-nums">
                      {formatCurrency(String(parseFloat(item.product.price) * item.quantity))}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeFromCart(item.product.id)}
                      className="ml-1 text-rose-400 hover:text-rose-600 text-xs"
                      disabled={isPending}
                      aria-label={`Quitar ${item.product.name}`}
                    >
                      ✕
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Payment method */}
        {cart.length > 0 && (
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">
              Método de pago
            </label>
            <div className="flex flex-wrap gap-2">
              {PAYMENT_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setPaymentMethod(opt.value)}
                  className={`rounded-full border px-4 py-1.5 text-sm font-medium transition-colors ${
                    paymentMethod === opt.value
                      ? 'border-slate-800 bg-slate-900 text-white'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                  disabled={isPending}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Total + submit */}
        {cart.length > 0 && (
          <div className="flex items-center justify-between rounded-xl bg-slate-900 px-5 py-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Total</p>
              <p className="text-2xl font-bold text-white">{formatCurrency(String(total))}</p>
            </div>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={isPending || cart.length === 0}
              className="rounded-full bg-white px-6 py-2.5 text-sm font-bold text-slate-900 hover:bg-slate-100 disabled:opacity-50"
            >
              {isPending ? 'Registrando…' : 'Confirmar venta'}
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>
        )}
      </div>
    </Modal>
  );
}

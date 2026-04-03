'use client';

/**
 * PosNewSalePage
 *
 * Full-screen "Nueva venta" interface for the POS terminal.
 * Route: /pos/terminal/new-sale
 *
 * Layout:
 * ┌─────────────────────────────────────────────────────┐
 * │ Header: "Nueva venta"   [Cancelar]                   │
 * ├───────────────────────────┬─────────────────────────┤
 * │  Izquierda                │  Derecha (sticky)        │
 * │  · ProductSearchPanel     │  · CustomerPanel         │
 * │  · SaleItemsPanel         │  · DiscountPanel         │
 * │                           │  · SplitPaymentPanel     │
 * │                           │  · SaleSummaryCard       │
 * └───────────────────────────┴─────────────────────────┘
 *
 * State: all local — no external store.
 * Derived values: subtotal, discountAmount, total, itemCount, cashChange.
 *
 * Accessibility:
 * - Keyboard shortcuts: / or Ctrl+K → search focus, Ctrl+Enter → confirm.
 * - aria-live region for cart change announcements.
 * - Proper landmarks: <header>, <main>, <section>, <aside>.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useEmployeeSession } from '@/features/pos/context';
import {
  usePosCreateSale,
  usePosErrorHandler,
} from '@/features/pos/cash-hooks';
import { formatCurrency } from '@/features/cash/utils';
import type { PosCustomerSummary, PosProduct } from '@/types/pos-cash';

import { ProductSearchPanel } from './ProductSearchPanel';
import { SaleItemsPanel } from './SaleItemsPanel';
import type { CartItem } from './SaleItemsPanel';
import { CustomerPanel } from './CustomerPanel';
import type { CustomerType } from './CustomerPanel';
import { DiscountPanel } from './DiscountPanel';
import type { DiscountType } from './DiscountPanel';
import { SplitPaymentPanel, createPaymentLine, toApiPaymentLineMethod } from './SplitPaymentPanel';
import type { PaymentLine } from './SplitPaymentPanel';
import { SaleSummaryCard } from './SaleSummaryCard';
import { ProductCatalogPanel } from './ProductCatalogPanel';

// ── Component ─────────────────────────────────────────────────────────────────

export function PosNewSalePage() {
  const router = useRouter();
  const { session } = useEmployeeSession();
  const createSaleMutation = usePosCreateSale();
  const handleError = usePosErrorHandler();

  // ── Cart state ────────────────────────────────────────────────────────────

  const [cart, setCart] = useState<CartItem[]>([]);

  // ── Customer state ────────────────────────────────────────────────────────

  const [customerType, setCustomerType] = useState<CustomerType>('consumer');
  const [customer, setCustomer] = useState<PosCustomerSummary | null>(null);

  // ── Discount state ────────────────────────────────────────────────────────

  const [discountEnabled, setDiscountEnabled] = useState(false);
  const [discountType, setDiscountType] = useState<DiscountType>('percent');
  const [discountValue, setDiscountValue] = useState('');

  // ── Payment state ─────────────────────────────────────────────────────────

  const [paymentLines, setPaymentLines] = useState<PaymentLine[]>(() => [createPaymentLine()]);
  const [cashReceived, setCashReceived] = useState('');

  // ── UI state ──────────────────────────────────────────────────────────────

  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [announcement, setAnnouncement] = useState('');
  /** Query from the main search bar — shared with the catalog panel. */
  const [searchQuery, setSearchQuery] = useState('');
  /** Category currently active in the catalog browser. */
  const [activeCategoryId, setActiveCategoryId] = useState<string | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  /** Selecting a category clears the search so we switch to browse mode. */
  function handleCategorySelect(id: string | null) {
    setActiveCategoryId(id);
    setSearchQuery('');
  }

  // ── Derived values ────────────────────────────────────────────────────────

  const subtotal = useMemo(
    () => cart.reduce((sum, item) => sum + parseFloat(item.product.price) * item.quantity, 0),
    [cart],
  );

  const itemCount = useMemo(
    () => cart.reduce((sum, item) => sum + item.quantity, 0),
    [cart],
  );

  const discountAmount = useMemo(() => {
    if (!discountEnabled || !discountValue) return 0;
    const v = parseFloat(discountValue);
    if (isNaN(v) || v <= 0) return 0;
    if (discountType === 'percent') {
      return Math.min(subtotal * (v / 100), subtotal);
    }
    return Math.min(v, subtotal);
  }, [discountEnabled, discountType, discountValue, subtotal]);

  const total = useMemo(() => Math.max(0, subtotal - discountAmount), [subtotal, discountAmount]);

  const cashReceivedNum = parseFloat(cashReceived);
  const hasCashLine = paymentLines.some((l) => l.method === 'efectivo');
  const cashLineTotal = paymentLines
    .filter((l) => l.method === 'efectivo')
    .reduce((sum, l) => sum + (parseFloat(l.amount) || 0), 0);
  const cashChange = useMemo(() => {
    if (!hasCashLine) return 0;
    const received = cashReceivedNum;
    if (isNaN(received)) return 0;
    return Math.max(0, received - cashLineTotal);
  }, [hasCashLine, cashReceivedNum, cashLineTotal]);

  // ── Discount validation ───────────────────────────────────────────────────

  const discountError = useMemo(() => {
    if (!discountEnabled || !discountValue) return '';
    const v = parseFloat(discountValue);
    if (isNaN(v) || v < 0) return 'El descuento no puede ser negativo.';
    if (discountType === 'percent' && v > 100) return 'El porcentaje no puede superar 100.';
    if (discountType === 'fixed' && v > subtotal) return 'El descuento no puede superar el subtotal.';
    return '';
  }, [discountEnabled, discountValue, discountType, subtotal]);

  // ── Cash validation ───────────────────────────────────────────────────────

  const cashError = useMemo(() => {
    if (!hasCashLine) return '';
    if (!cashReceived || isNaN(cashReceivedNum)) return '';
    if (cashReceivedNum < cashLineTotal) return 'El monto recibido es menor al total en efectivo.';
    return '';
  }, [hasCashLine, cashReceived, cashReceivedNum, cashLineTotal]);

  // ── Payment lines validation ──────────────────────────────────────────────

  const totalPaid = paymentLines.reduce((sum, l) => sum + (parseFloat(l.amount) || 0), 0);
  const paymentsExact = Math.abs(total - totalPaid) < 0.01 && total > 0;

  // ── Confirm button disabled state ─────────────────────────────────────────

  const confirmDisabled = useMemo(() => {
    if (cart.length === 0) return true;
    if (total <= 0) return true;
    if (customerType === 'registered' && !customer) return true;
    if (discountEnabled && !!discountError) return true;
    // Payment lines must sum to exactly the total
    if (!paymentsExact) return true;
    // All payment lines must have a valid amount > 0
    if (paymentLines.some((l) => !l.amount || parseFloat(l.amount) <= 0 || isNaN(parseFloat(l.amount)))) return true;
    // Cash received must be sufficient if cash line exists
    if (hasCashLine && cashReceived && !!cashError) return true;
    return false;
  }, [cart, total, customerType, customer, discountEnabled, discountError, paymentsExact, paymentLines, hasCashLine, cashReceived, cashError]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // / → focus search (when not already in an input)
      if (
        e.key === '/' &&
        !(e.target instanceof HTMLInputElement) &&
        !(e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }

      // Ctrl+K → focus search
      if (e.key === 'k' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }

      // Ctrl+Enter → confirm sale
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (!confirmDisabled && !createSaleMutation.isPending) {
          void handleSubmit();
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmDisabled, createSaleMutation.isPending]);

  // ── Cart helpers ──────────────────────────────────────────────────────────

  const addToCart = useCallback((product: PosProduct) => {
    setCart((prev) => {
      const existing = prev.find((i) => i.product.id === product.id);
      const next = existing
        ? prev.map((i) =>
            i.product.id === product.id ? { ...i, quantity: i.quantity + 1 } : i,
          )
        : [...prev, { product, quantity: 1 }];

      const newQty = next.find((i) => i.product.id === product.id)?.quantity ?? 1;
      const newTotal = next.reduce(
        (sum, item) => sum + parseFloat(item.product.price) * item.quantity,
        0,
      );
      setAnnouncement(
        `${product.name} agregado. Cantidad: ${newQty}. Total: ${formatCurrency(String(newTotal))}`,
      );
      return next;
    });
    setError('');
  }, []);

  const removeFromCart = useCallback((productId: string) => {
    setCart((prev) => {
      const item = prev.find((i) => i.product.id === productId);
      const next = prev.filter((i) => i.product.id !== productId);
      if (item) {
        setAnnouncement(`${item.product.name} quitado del carrito.`);
      }
      return next;
    });
  }, []);

  const changeQty = useCallback((productId: string, delta: number) => {
    setCart((prev) => {
      const updated = prev
        .map((i) =>
          i.product.id === productId
            ? { ...i, quantity: Math.max(0, i.quantity + delta) }
            : i,
        )
        .filter((i) => i.quantity > 0);
      return updated;
    });
  }, []);

  const setQty = useCallback((productId: string, qty: number) => {
    if (qty <= 0) {
      removeFromCart(productId);
      return;
    }
    setCart((prev) =>
      prev.map((i) =>
        i.product.id === productId ? { ...i, quantity: qty } : i,
      ),
    );
  }, [removeFromCart]);

  // ── Handle customer type change ───────────────────────────────────────────

  function handleCustomerTypeChange(type: CustomerType) {
    setCustomerType(type);
    if (type === 'consumer') {
      setCustomer(null);
    }
  }

  // ── Submit ────────────────────────────────────────────────────────────────

  async function handleSubmit() {
    setError('');

    // Local validations
    if (cart.length === 0) {
      setError('Agregá al menos un producto.');
      return;
    }
    if (total <= 0) {
      setError('El total debe ser mayor a cero.');
      return;
    }
    if (customerType === 'registered' && !customer) {
      setError('Seleccioná o creá un cliente.');
      return;
    }
    if (discountEnabled && discountError) {
      setError(discountError);
      return;
    }
    if (hasCashLine && cashReceived && cashError) {
      setError(cashError);
      return;
    }
    if (!paymentsExact) {
      setError('La suma de pagos no coincide con el total de la venta.');
      return;
    }

    const token = session.status === 'authenticated' ? session.token : null;
    if (!token) {
      setError('Sin sesión operativa. Recargá la página.');
      return;
    }

    try {
      const result = await createSaleMutation.mutateAsync({
        items: cart.map((item) => ({
          product_id: item.product.id,
          quantity: item.quantity,
        })),
        payments: paymentLines.map((line) => ({
          method: toApiPaymentLineMethod(line.method),
          amount: parseFloat(line.amount).toFixed(2),
          reference: line.reference || undefined,
        })),
        customer_id: customerType === 'registered' ? (customer?.id ?? null) : null,
        discount: discountAmount > 0 ? discountAmount : undefined,
        notes:
          paymentLines.some((l) => l.method === 'mercadopago')
            ? 'Mercado Pago'
            : paymentLines.some((l) => l.method === 'credito')
              ? 'Tarjeta de crédito'
              : paymentLines.some((l) => l.method === 'debito')
                ? 'Tarjeta de débito'
                : undefined,
      });

      setSuccessMsg(
        `✓ Venta #${result.sale.number} confirmada · ${formatCurrency(result.sale.total)}`,
      );
      setAnnouncement(
        `Venta número ${result.sale.number} confirmada por ${formatCurrency(result.sale.total)}.`,
      );

      // Navigate back after brief success display
      setTimeout(() => {
        router.push('/pos/terminal' as any);
      }, 2000);
    } catch (err) {
      setError(handleError(err));
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const isPending = createSaleMutation.isPending;

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gray-50">
      {/* ── aria-live region for cart events ─────────────────────────── */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        role="status"
      >
        {announcement}
      </div>

      {/* ── Header ───────────────────────────────────────────────────── */}
      <header className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
          onClick={() => router.push('/pos/terminal' as any)}
            aria-label="Volver al terminal"
            className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 text-slate-500 transition-colors hover:bg-slate-50"
          >
            <span aria-hidden>←</span>
          </button>
          <h1 className="text-xl font-bold text-slate-900">Nueva venta</h1>
        </div>

        <div className="flex items-center gap-2">
          <span className="hidden text-xs text-slate-400 sm:block">
            <kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-xs text-slate-500">/</kbd>
            {' '}buscar ·{' '}
            <kbd className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-xs text-slate-500">Ctrl+↵</kbd>
            {' '}confirmar
          </span>
          <button
            type="button"
            onClick={() => router.push('/pos/terminal' as any)}
            className="rounded-xl border border-slate-200 px-4 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50"
          >
            Cancelar
          </button>
        </div>
      </header>

      {/* ── Main layout ──────────────────────────────────────────────── */}
      <main className="grid flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[1fr_380px]">

        {/* ── Left column: products ──────────────────────────────────── */}
        <section
          aria-label="Productos de la venta"
          className="flex flex-col gap-4 overflow-y-auto border-r border-slate-200 p-6"
        >
          {/* Search */}
          <div>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Buscar producto o categoría
            </h2>
            <ProductSearchPanel
              query={searchQuery}
              onQueryChange={setSearchQuery}
              disabled={isPending}
              inputRef={searchInputRef}
            />
          </div>

          {/* Divider */}
          <hr className="border-slate-100" />

          {/* Catalog browser — shows inline search results or category chips */}
          <ProductCatalogPanel
            onAdd={addToCart}
            disabled={isPending}
            searchQuery={searchQuery}
            selectedCategoryId={activeCategoryId}
            onCategorySelect={handleCategorySelect}
          />

          {/* Divider */}
          <hr className="border-slate-100" />

          {/* Cart items */}
          <div className="flex-1">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Productos en la venta
              {itemCount > 0 && (
                <span className="ml-2 rounded-full bg-slate-200 px-2 py-0.5 text-slate-600">
                  {itemCount}
                </span>
              )}
            </h2>
            <SaleItemsPanel
              items={cart}
              onChangeQty={changeQty}
              onSetQty={setQty}
              onRemove={removeFromCart}
              subtotal={subtotal}
              itemCount={itemCount}
              disabled={isPending}
            />
          </div>
        </section>

        {/* ── Right column: sale data (sticky/scrollable) ─────────────── */}
        <aside
          aria-label="Datos de la venta"
          className="flex flex-col gap-5 overflow-y-auto bg-white p-6"
        >
          {/* Customer */}
          <CustomerPanel
            customerType={customerType}
            onCustomerTypeChange={handleCustomerTypeChange}
            customer={customer}
            onCustomerChange={setCustomer}
            disabled={isPending}
          />

          {/* Divider */}
          <hr className="border-slate-100" />

          {/* Discount */}
          <DiscountPanel
            enabled={discountEnabled}
            onEnabledChange={setDiscountEnabled}
            type={discountType}
            onTypeChange={setDiscountType}
            value={discountValue}
            onValueChange={setDiscountValue}
            subtotal={subtotal}
            discountAmount={discountAmount}
            disabled={isPending}
            error={discountEnabled ? discountError : undefined}
          />

          {/* Divider */}
          <hr className="border-slate-100" />

          {/* Payment method */}
          <SplitPaymentPanel
            lines={paymentLines}
            onLinesChange={setPaymentLines}
            total={total}
            disabled={isPending}
            cashReceived={cashReceived}
            onCashReceivedChange={setCashReceived}
          />

          {/* Spacer to push summary to bottom on taller screens */}
          <div className="flex-1" />

          {/* Sale summary + confirm */}
          <div
            ref={(el) => {
              if (confirmBtnRef && !confirmBtnRef.current && el) {
                const btn = el.querySelector('button');
                if (btn) (confirmBtnRef as React.MutableRefObject<HTMLButtonElement>).current = btn;
              }
            }}
          >
            <SaleSummaryCard
              subtotal={subtotal}
              discountAmount={discountAmount}
              total={total}
              onConfirm={() => void handleSubmit()}
              onCancel={() => router.push('/pos/terminal' as any)}
              isPending={isPending}
              disabled={confirmDisabled}
              error={error}
              successMsg={successMsg}
            />
          </div>
        </aside>
      </main>
    </div>
  );
}

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
  usePosCreateCounterOrder,
  usePosCreateSale,
  usePosErrorHandler,
} from '@/features/pos/cash-hooks';
import {
  getEffectiveRestaurantOperationSettings,
  useRestaurantOperationSettings,
} from '@/features/resto/hooks';
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

type SaleFlowMode = 'quick-sale' | 'kitchen-order';

// ── Component ─────────────────────────────────────────────────────────────────

export function PosNewSalePage() {
  const router = useRouter();
  const { session } = useEmployeeSession();
  const createSaleMutation = usePosCreateSale();
  const createCounterOrderMutation = usePosCreateCounterOrder();
  const handleError = usePosErrorHandler();
  const operationSettingsQuery = useRestaurantOperationSettings();
  const operationSettings = getEffectiveRestaurantOperationSettings(operationSettingsQuery.data);

  // ── Cart state ────────────────────────────────────────────────────────────

  const [cart, setCart] = useState<CartItem[]>([]);
  const [saleMode, setSaleMode] = useState<SaleFlowMode>('quick-sale');

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
  const [counterCustomerName, setCounterCustomerName] = useState('');
  const [counterOrderNote, setCounterOrderNote] = useState('');

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
  const isQuickSaleEnabled = operationSettings.pos_quick_sale_enabled;
  const isKitchenOrderEnabled = operationSettings.kitchen_enabled && operationSettings.counter_orders_enabled;
  const availableModes = useMemo<SaleFlowMode[]>(() => {
    const modes: SaleFlowMode[] = [];
    if (isQuickSaleEnabled) modes.push('quick-sale');
    if (isKitchenOrderEnabled) modes.push('kitchen-order');
    return modes;
  }, [isQuickSaleEnabled, isKitchenOrderEnabled]);
  const hasOperationModeAvailable = availableModes.length > 0;

  const preferredMode = useMemo<SaleFlowMode | null>(() => {
    if (availableModes.length === 0) return null;

    const defaultMode = operationSettings.default_pos_mode;
    if (defaultMode === 'kitchen_order' && isKitchenOrderEnabled) {
      return 'kitchen-order';
    }
    if (defaultMode === 'quick_sale' && isQuickSaleEnabled) {
      return 'quick-sale';
    }
    if (isQuickSaleEnabled) return 'quick-sale';
    if (isKitchenOrderEnabled) return 'kitchen-order';
    return null;
  }, [availableModes.length, operationSettings.default_pos_mode, isKitchenOrderEnabled, isQuickSaleEnabled]);

  useEffect(() => {
    if (!preferredMode) return;
    if (!availableModes.includes(saleMode)) {
      setSaleMode(preferredMode);
      return;
    }

    if (operationSettings.default_pos_mode === 'kitchen_order' && preferredMode === 'kitchen-order' && saleMode !== 'kitchen-order') {
      setSaleMode('kitchen-order');
    }
  }, [availableModes, operationSettings.default_pos_mode, preferredMode, saleMode]);

  const effectiveDiscountAmount = saleMode === 'quick-sale' ? discountAmount : 0;
  const effectiveTotal = saleMode === 'quick-sale' ? total : subtotal;

  // Keep the single auto-amount payment line in sync with the sale total.
  // Triggers on every total change; only writes if there is exactly one line
  // whose amount was never manually edited (isAutoAmount === true).
  useEffect(() => {
    setPaymentLines((prev) => {
      if (saleMode !== 'quick-sale') return prev;
      if (prev.length !== 1) return prev;
      const line = prev[0]!;
      if (!line.isAutoAmount) return prev;
      const next = effectiveTotal > 0 ? effectiveTotal.toFixed(2) : '';
      if (line.amount === next) return prev;
      return [{ ...line, amount: next }];
    });
  }, [effectiveTotal, saleMode]);

  const cashReceivedNum = parseFloat(cashReceived);
  const hasCashLine = paymentLines.some((l) => l.method === 'efectivo');
  const cashLineTotal = paymentLines
    .filter((l) => l.method === 'efectivo')
    .reduce((sum, l) => sum + (parseFloat(l.amount) || 0), 0);

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
    if (cashReceivedNum < cashLineTotal) return 'El monto ingresado no cubre el cobro en efectivo.';
    return '';
  }, [hasCashLine, cashReceived, cashReceivedNum, cashLineTotal]);

  // ── Payment lines validation ──────────────────────────────────────────────

  const totalPaid = paymentLines.reduce((sum, l) => sum + (parseFloat(l.amount) || 0), 0);
  const paymentsExact = Math.abs(effectiveTotal - totalPaid) < 0.01 && effectiveTotal > 0;

  // ── Confirm button disabled state ─────────────────────────────────────────

  const confirmDisabled = useMemo(() => {
    if (cart.length === 0) return true;
    if (!hasOperationModeAvailable) return true;
    if (effectiveTotal <= 0) return true;
    if (saleMode === 'kitchen-order') {
      return cart.some((item) => item.quantity <= 0);
    }
    if (customerType === 'registered' && !customer) return true;
    if (discountEnabled && !!discountError) return true;
    // Payment lines must sum to exactly the total
    if (!paymentsExact) return true;
    // All payment lines must have a valid amount > 0
    if (paymentLines.some((l) => !l.amount || parseFloat(l.amount) <= 0 || isNaN(parseFloat(l.amount)))) return true;
    // Cash received must be sufficient if cash line exists
    if (hasCashLine && cashReceived && !!cashError) return true;
    return false;
  }, [
    cart,
    effectiveTotal,
    saleMode,
    customerType,
    customer,
    discountEnabled,
    discountError,
    paymentsExact,
    paymentLines,
    hasCashLine,
    cashReceived,
    cashError,
    hasOperationModeAvailable,
  ]);

  const isPending =
    saleMode === 'quick-sale'
      ? createSaleMutation.isPending
      : createCounterOrderMutation.isPending;

  function resetDraftState() {
    setCart([]);
    setCustomerType('consumer');
    setCustomer(null);
    setDiscountEnabled(false);
    setDiscountType('percent');
    setDiscountValue('');
    setPaymentLines([createPaymentLine()]);
    setCashReceived('');
    setCounterCustomerName('');
    setCounterOrderNote('');
    setSearchQuery('');
    setActiveCategoryId(null);
  }

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
        if (!confirmDisabled && !isPending) {
          void handleSubmit();
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmDisabled, isPending]);

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
    setSuccessMsg('');

    // Local validations
    if (cart.length === 0) {
      setError('Agregá al menos un producto.');
      return;
    }
    if (!hasOperationModeAvailable) {
      setError('No hay modos de venta habilitados para este negocio.');
      return;
    }
    if (effectiveTotal <= 0) {
      setError('El total debe ser mayor a cero.');
      return;
    }
    if (saleMode === 'kitchen-order' && cart.some((item) => item.quantity <= 0)) {
      setError('Revisá las cantidades antes de enviar el pedido a cocina.');
      return;
    }
    if (saleMode === 'kitchen-order') {
      const token = session.status === 'authenticated' ? session.token : null;
      if (!token) {
        setError('Sin sesión operativa. Recargá la página.');
        return;
      }

      try {
        const result = await createCounterOrderMutation.mutateAsync({
          items: cart.map((item) => ({
            product_id: item.product.id,
            quantity: item.quantity,
            note: item.note || undefined,
          })),
          customer_name: counterCustomerName.trim() || undefined,
          note: counterOrderNote.trim() || undefined,
          send_to_kitchen: true,
        });

        setSuccessMsg(`✓ Pedido #${result.number} enviado a cocina`);
        setAnnouncement(
          `Pedido número ${result.number} enviado a cocina por ${formatCurrency(result.total_amount)}.`,
        );
        resetDraftState();
      } catch (err) {
        setError(handleError(err));
      }
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
        router.push('/pos/terminal');
      }, 2000);
    } catch (err) {
      setError(handleError(err));
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

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
            onClick={() => router.push('/pos/terminal')}
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
            onClick={() => router.push('/pos/terminal')}
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
          <section aria-label="Modo de operación" className="space-y-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Modo de mostrador
              </p>
              <h2 className="mt-1 text-lg font-semibold text-slate-900">
                {!hasOperationModeAvailable
                  ? 'Operación deshabilitada'
                  : saleMode === 'quick-sale'
                    ? 'Venta rápida'
                    : 'Pedido con cocina'}
              </h2>
            </div>

            {availableModes.length > 1 ? (
              <div className="grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1">
                {isQuickSaleEnabled ? (
                  <button
                    type="button"
                    onClick={() => {
                      setSaleMode('quick-sale');
                      setError('');
                      setSuccessMsg('');
                    }}
                    className={`rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${
                      saleMode === 'quick-sale'
                        ? 'bg-white text-slate-900 shadow-sm'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                    aria-pressed={saleMode === 'quick-sale'}
                  >
                    Venta rápida
                  </button>
                ) : null}
                {isKitchenOrderEnabled ? (
                  <button
                    type="button"
                    onClick={() => {
                      setSaleMode('kitchen-order');
                      setError('');
                      setSuccessMsg('');
                    }}
                    className={`rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${
                      saleMode === 'kitchen-order'
                        ? 'bg-white text-slate-900 shadow-sm'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                    aria-pressed={saleMode === 'kitchen-order'}
                  >
                    Pedido con cocina
                  </button>
                ) : null}
              </div>
            ) : null}

            {availableModes.length === 1 ? (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                {availableModes[0] === 'quick-sale'
                  ? 'Solo venta rápida habilitada para este negocio.'
                  : 'Solo pedido con cocina habilitado para este negocio.'}
              </div>
            ) : null}

            {!hasOperationModeAvailable ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                Este negocio no tiene modos de operación POS habilitados. Revisá la configuración operativa de Restaurante Inteligente.
              </div>
            ) : null}

            {saleMode === 'kitchen-order' && hasOperationModeAvailable && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                Este pedido se enviará a cocina y se cobrará o cerrará desde el flujo de pedidos.
              </div>
            )}
          </section>

          <hr className="border-slate-100" />

          {/* Customer */}
          {saleMode === 'quick-sale' ? (
            <CustomerPanel
              customerType={customerType}
              onCustomerTypeChange={handleCustomerTypeChange}
              customer={customer}
              onCustomerChange={setCustomer}
              disabled={isPending}
            />
          ) : (
            <section aria-label="Datos del pedido" className="space-y-3">
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Datos del pedido
                </h3>
                <p className="mt-1 text-sm text-slate-500">
                  Podés identificar el pedido antes de enviarlo a cocina.
                </p>
              </div>

              <div>
                <label
                  htmlFor="counter-customer-name"
                  className="mb-1 block text-xs font-medium text-slate-500"
                >
                  Nombre del cliente <span className="text-slate-300">(opcional)</span>
                </label>
                <input
                  id="counter-customer-name"
                  type="text"
                  maxLength={128}
                  value={counterCustomerName}
                  onChange={(e) => setCounterCustomerName(e.target.value)}
                  disabled={isPending}
                  placeholder="Ej. Juan, retiro en 10 minutos"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60"
                />
              </div>

              <div>
                <label
                  htmlFor="counter-order-note"
                  className="mb-1 block text-xs font-medium text-slate-500"
                >
                  Nota general <span className="text-slate-300">(opcional)</span>
                </label>
                <textarea
                  id="counter-order-note"
                  rows={3}
                  maxLength={500}
                  value={counterOrderNote}
                  onChange={(e) => setCounterOrderNote(e.target.value)}
                  disabled={isPending}
                  placeholder="Aclaraciones para cocina o mostrador"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60"
                />
              </div>
            </section>
          )}

          {/* Divider */}
          <hr className="border-slate-100" />

          {/* Discount */}
          {saleMode === 'quick-sale' ? (
            <>
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
            </>
          ) : (
            <section className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
              Los pagos quedan deshabilitados en este modo para evitar crear una venta directa.
            </section>
          )}

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
              discountAmount={effectiveDiscountAmount}
              total={effectiveTotal}
              onConfirm={() => void handleSubmit()}
              onCancel={() => router.push('/pos/terminal')}
              isPending={isPending}
              disabled={confirmDisabled}
              error={error}
              successMsg={successMsg}
              confirmLabel={saleMode === 'quick-sale' ? 'Cobrar venta' : 'Enviar a cocina'}
              pendingLabel={saleMode === 'quick-sale' ? 'Cobrando…' : 'Enviando…'}
              helperText={
                saleMode === 'kitchen-order'
                  ? 'Este pedido no registra pago ni descuenta stock en esta etapa.'
                  : undefined
              }
            />
          </div>
        </aside>
      </main>
    </div>
  );
}

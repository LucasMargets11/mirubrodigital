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
import { usePosOperationSettings } from '@/features/pos/offline/pos-operation-settings';
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
import { usePosOfflineCatalog } from '@/features/pos/offline/offline-catalog';
import { OfflineProductCatalogPanel } from '@/features/pos/offline/OfflineProductCatalogPanel';
import { OfflineSalesPanel } from '@/features/pos/offline/offline-sales-panel';
import { OfflineContingencyNotice } from '@/features/pos/offline/OfflineContingencyNotice';
import { usePosOfflineGuard } from '@/features/pos/offline/offline-guard';
import {
  usePosCaptureOfflineSale,
  OfflineSaleValidationError,
} from '@/features/pos/offline/offline-sales-hooks';
import {
  validateOfflineSale,
  OFFLINE_PAYMENT_METHODS,
  OFFLINE_PAYMENT_LABELS,
} from '@/features/pos/offline/offline-sale-build';
import type { OfflinePaymentMethodCode } from '@/features/pos/offline/offline-sales-types';

type SaleFlowMode = 'quick-sale' | 'kitchen-order';

/** Shown while offline when the snapshot does not allow building a sale. */
const OFFLINE_DISABLED_MESSAGE =
  'Sin conexión. El catálogo offline no está disponible para este negocio.';
/** Confirmation shown after a sale is queued for later sync. */
const OFFLINE_SAVE_SUCCESS = 'Venta guardada para sincronizar.';

// ── Component ─────────────────────────────────────────────────────────────────

export function PosNewSalePage() {
  const router = useRouter();
  const { session } = useEmployeeSession();
  const createSaleMutation = usePosCreateSale();
  const createCounterOrderMutation = usePosCreateCounterOrder();
  const handleError = usePosErrorHandler();
  // PR-OFF-10: read operation flags from the POS bootstrap snapshot (employee
  // token) instead of the owner/admin endpoint, which 401s for POS sessions.
  const operationSettings = usePosOperationSettings();

  // ── Offline catalog source (PR-OFF-03) ──────────────────────────────────────
  // When the device is offline we browse the locally-persisted snapshot instead
  // of the online catalog. Confirmed sales are queued locally (PR-OFF-04).
  const offlineCatalog = usePosOfflineCatalog();
  const isOffline = offlineCatalog.isOffline;

  // Safe return to the terminal (PR-OFF-09, refined in PR-OFF-11). We always
  // use an SPA `router.replace('/pos/terminal')`: the terminal route is
  // precached by the service worker, so this resolves both online and offline
  // without hitting the network for an uncached RSC payload. We never call
  // `router.back()` (the previous history entry may be an uncached route) and
  // we never hard-navigate (a `window.location.assign` could let the SW fall
  // back to /pos/login). `replace` also avoids stacking new-sale in history.
  const navigateToTerminal = useCallback(() => {
    router.replace('/pos/terminal');
  }, [router]);

  const offlineGuard = usePosOfflineGuard();
  const captureOfflineSale = usePosCaptureOfflineSale();
  const [offlinePaymentMethod, setOfflinePaymentMethod] =
    useState<OfflinePaymentMethodCode>('cash');

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
  // PR-OFF-08: "Pedido con cocina" is never available offline. The offline MVP
  // only supports quick sales, so we hide the mode and harden the submit path.
  const kitchenOrderAvailable = isKitchenOrderEnabled && !isOffline;
  const availableModes = useMemo<SaleFlowMode[]>(() => {
    const modes: SaleFlowMode[] = [];
    if (isQuickSaleEnabled) modes.push('quick-sale');
    if (kitchenOrderAvailable) modes.push('kitchen-order');
    return modes;
  }, [isQuickSaleEnabled, kitchenOrderAvailable]);
  const hasOperationModeAvailable = availableModes.length > 0;

  const preferredMode = useMemo<SaleFlowMode | null>(() => {
    if (availableModes.length === 0) return null;

    const defaultMode = operationSettings.default_pos_mode;
    if (defaultMode === 'kitchen_order' && kitchenOrderAvailable) {
      return 'kitchen-order';
    }
    if (defaultMode === 'quick_sale' && isQuickSaleEnabled) {
      return 'quick-sale';
    }
    if (isQuickSaleEnabled) return 'quick-sale';
    if (kitchenOrderAvailable) return 'kitchen-order';
    return null;
  }, [availableModes.length, operationSettings.default_pos_mode, kitchenOrderAvailable, isQuickSaleEnabled]);

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

  // ── Offline capture validation (PR-OFF-04) ─────────────────────────────────

  const offlineEmployeeId = session.status === 'authenticated' ? session.employee.id : null;
  const offlineEmployeeCode =
    session.status === 'authenticated' ? session.employee.employee_code : null;

  const offlineValidation = useMemo(() => {
    if (!isOffline) return { ok: true } as const;
    if (!offlineEmployeeId || !offlineEmployeeCode) {
      return { ok: false as const, message: 'Sin sesión operativa. Recargá la página.' };
    }
    return validateOfflineSale({
      snapshot: offlineCatalog.snapshot,
      cart,
      paymentMethod: offlinePaymentMethod,
      employee: { id: offlineEmployeeId, code: offlineEmployeeCode },
    });
  }, [
    isOffline,
    offlineCatalog.snapshot,
    cart,
    offlinePaymentMethod,
    offlineEmployeeId,
    offlineEmployeeCode,
  ]);

  const isCapturingOffline = captureOfflineSale.isPending;
  // PR-OFF-07: block offline confirmation on snapshot expiry / pending-limit too.
  const offlineBlockReason = isOffline ? offlineGuard.blockReason : null;
  const offlineConfirmDisabled =
    isOffline && (!offlineValidation.ok || isCapturingOffline || offlineBlockReason !== null);

  const isPending =
    saleMode === 'quick-sale'
      ? createSaleMutation.isPending
      : createCounterOrderMutation.isPending;

  // Effective confirm gating: offline uses the snapshot validation instead.
  const submitDisabled = isOffline ? offlineConfirmDisabled : confirmDisabled;
  const submitPending = isOffline ? isCapturingOffline : isPending;

  // Helper line under the confirm button while offline.
  const offlineHelperText: string | undefined = (() => {
    if (!isOffline) return undefined;
    if (!offlineCatalog.canBuildCart) return OFFLINE_DISABLED_MESSAGE;
    if (offlineBlockReason) return offlineBlockReason;
    if (offlineValidation.ok === false && cart.length > 0) {
      return offlineValidation.message;
    }
    return 'La venta se guardará para sincronizar cuando vuelva la conexión.';
  })();

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
        if (!submitDisabled && !submitPending) {
          void handleSubmit();
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submitDisabled, submitPending]);

  // ── Cart helpers ──────────────────────────────────────────────────────────

  const addToCart = useCallback((product: PosProduct) => {
    // Offline: only allow building a cart from a valid, enabled snapshot, and
    // never while the snapshot is expired or the pending queue is full (PR-OFF-07).
    if (isOffline && (!offlineCatalog.canBuildCart || offlineBlockReason !== null)) {
      return;
    }
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
  }, [isOffline, offlineCatalog.canBuildCart, offlineBlockReason]);

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

  /**
   * Offline contingency (PR-OFF-04): validate against the snapshot and queue the
   * sale locally. No backend call, no real stock decrement — sync comes later.
   */
  async function handleOfflineSubmit() {
    setError('');
    setSuccessMsg('');

    if (session.status !== 'authenticated') {
      setError('Sin sesión operativa. Recargá la página.');
      return;
    }

    // Hard rule (PR-OFF-08): only quick sales may be captured offline. Never
    // create an OfflineSaleQueueItem from a kitchen order.
    if (saleMode !== 'quick-sale') {
      setError('Pedido con cocina no está disponible sin conexión. Cambiá a Venta rápida.');
      return;
    }

    try {
      await captureOfflineSale.mutateAsync({
        snapshot: offlineCatalog.snapshot,
        cart,
        paymentMethod: offlinePaymentMethod,
        employee: {
          id: session.employee.id,
          code: session.employee.employee_code,
        },
        note: 'Venta offline',
      });

      setSuccessMsg(OFFLINE_SAVE_SUCCESS);
      setAnnouncement('Venta guardada para sincronizar cuando vuelva la conexión.');
      resetDraftState();
      setOfflinePaymentMethod('cash');
    } catch (err) {
      if (err instanceof OfflineSaleValidationError) {
        setError(err.message);
      } else {
        setError('No se pudo guardar la venta offline. Intentá de nuevo.');
      }
    }
  }

  async function handleSubmit() {
    setError('');
    setSuccessMsg('');

    // Offline contingency: capture the sale locally (PR-OFF-04).
    if (isOffline) {
      // Hard rule (PR-OFF-08): kitchen orders cannot be captured offline.
      if (saleMode !== 'quick-sale') {
        setError('Pedido con cocina no está disponible sin conexión. Cambiá a Venta rápida.');
        return;
      }
      await handleOfflineSubmit();
      return;
    }

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
            onClick={navigateToTerminal}
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
            onClick={navigateToTerminal}
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

          {/* Contingency security notice (PR-OFF-07) */}
          {isOffline ? <OfflineContingencyNotice guard={offlineGuard} /> : null}

          {/* Catalog browser — offline snapshot or online API */}
          {isOffline ? (
            <OfflineProductCatalogPanel
              catalog={offlineCatalog}
              onAdd={addToCart}
              disabled={isPending || !offlineCatalog.canBuildCart || offlineBlockReason !== null}
              searchQuery={searchQuery}
              selectedCategoryId={activeCategoryId}
              onCategorySelect={handleCategorySelect}
            />
          ) : (
            <ProductCatalogPanel
              onAdd={addToCart}
              disabled={isPending}
              searchQuery={searchQuery}
              selectedCategoryId={activeCategoryId}
              onCategorySelect={handleCategorySelect}
            />
          )}

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
                {kitchenOrderAvailable ? (
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

            {/* PR-OFF-08: kitchen orders are not available offline. */}
            {isOffline && isKitchenOrderEnabled ? (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                Pedido con cocina no está disponible sin conexión. Solo podés registrar ventas rápidas.
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

          {/* Offline payment method (PR-OFF-04) */}
          {isOffline ? (
            <section aria-label="Pago de la venta offline" className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Método de pago
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {OFFLINE_PAYMENT_METHODS.map((method) => (
                  <button
                    key={method}
                    type="button"
                    onClick={() => {
                      setOfflinePaymentMethod(method);
                      setError('');
                    }}
                    disabled={isCapturingOffline}
                    aria-pressed={offlinePaymentMethod === method}
                    className={`rounded-xl border px-4 py-2 text-sm font-semibold transition-colors disabled:opacity-60 ${
                      offlinePaymentMethod === method
                        ? 'border-slate-900 bg-slate-900 text-white'
                        : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    {OFFLINE_PAYMENT_LABELS[method]}
                  </button>
                ))}
              </div>
              <p className="text-xs text-slate-400">
                La venta se guardará localmente y se sincronizará cuando vuelva la conexión.
              </p>
            </section>
          ) : saleMode === 'quick-sale' ? (
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
          {!isOffline && (saleMode === 'quick-sale' ? (
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
          ))}

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
              isPending={submitPending}
              disabled={submitDisabled}
              error={error}
              successMsg={successMsg}
              confirmLabel={
                isOffline
                  ? 'Guardar venta offline'
                  : saleMode === 'quick-sale'
                    ? 'Cobrar venta'
                    : 'Enviar a cocina'
              }
              pendingLabel={
                isOffline
                  ? 'Guardando…'
                  : saleMode === 'quick-sale'
                    ? 'Cobrando…'
                    : 'Enviando…'
              }
              helperText={
                isOffline
                  ? offlineHelperText
                  : saleMode === 'kitchen-order'
                    ? 'Este pedido no registra pago ni descuenta stock en esta etapa.'
                    : undefined
              }
            />
          </div>

          {/* Offline pending sales queue (PR-OFF-04) */}
          <OfflineSalesPanel />
        </aside>
      </main>
    </div>
  );
}

/**
 * Frontend tests for the SplitPaymentPanel and split-payment integration.
 *
 * Coverage:
 * SP1. Renders a single payment line by default
 * SP2. Can add and remove payment lines
 * SP3. Calculates total paid / remaining correctly
 * SP4. Shows exact-match indicator when payments sum equals total
 * SP5. Shows vuelto (change) for efectivo lines
 * SP6. Generates correct API payload with toApiPaymentLineMethod
 * SP7. Auto-fills remaining amount when adding a new line
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  SplitPaymentPanel,
  createPaymentLine,
  toApiPaymentLineMethod,
} from '@/features/pos/components/SplitPaymentPanel';
import type { PaymentLine } from '@/features/pos/components/SplitPaymentPanel';

// ── Helpers ────────────────────────────────────────────────────────────────────

function renderPanel(props: Partial<React.ComponentProps<typeof SplitPaymentPanel>> = {}) {
  const defaultLines = props.lines ?? [createPaymentLine('', 'efectivo')];
  const defaultProps = {
    lines: defaultLines,
    onLinesChange: vi.fn(),
    total: 30000,
    cashReceived: '',
    onCashReceivedChange: vi.fn(),
    ...props,
  };
  return { ...render(<SplitPaymentPanel {...defaultProps} />), props: defaultProps };
}

// ── SP1. Renders single payment line ──────────────────────────────────────────

describe('SplitPaymentPanel', () => {
  it('SP1: renders a single payment line with method select and amount input', () => {
    renderPanel();
    // Should have one method select and one amount input
    const selects = screen.getAllByRole('combobox');
    expect(selects).toHaveLength(1);
    // Amount input
    const amountInputs = screen.getAllByPlaceholderText('0');
    expect(amountInputs.length).toBeGreaterThanOrEqual(1);
  });

  // ── SP2. Add and remove lines ───────────────────────────────────────────────

  it('SP2: can add a payment line', () => {
    const onLinesChange = vi.fn();
    renderPanel({ onLinesChange });
    const addBtn = screen.getByText(/Agregar otro medio de pago/);
    fireEvent.click(addBtn);
    expect(onLinesChange).toHaveBeenCalledTimes(1);
    const newLines = onLinesChange.mock.calls[0]![0] as PaymentLine[];
    expect(newLines).toHaveLength(2);
  });

  it('SP2b: can remove a payment line when there are multiple', () => {
    const onLinesChange = vi.fn();
    const lines = [
      createPaymentLine('10000', 'efectivo'),
      createPaymentLine('20000', 'transferencia'),
    ];
    renderPanel({ lines, onLinesChange });
    const removeBtns = screen.getAllByLabelText(/Eliminar pago/);
    expect(removeBtns).toHaveLength(2);
    fireEvent.click(removeBtns[0]!);
    expect(onLinesChange).toHaveBeenCalledTimes(1);
    const remaining = onLinesChange.mock.calls[0]![0] as PaymentLine[];
    expect(remaining).toHaveLength(1);
    expect(remaining[0]!.method).toBe('transferencia');
  });

  // ── SP3. Total paid / remaining ─────────────────────────────────────────────

  it('SP3: shows remaining when payments under total', () => {
    const lines = [createPaymentLine('10000', 'efectivo')];
    renderPanel({ lines, total: 30000 });
    expect(screen.getByText('Restante')).toBeTruthy();
  });

  it('SP3b: shows excedente when payments over total', () => {
    const lines = [createPaymentLine('35000', 'efectivo')];
    renderPanel({ lines, total: 30000 });
    expect(screen.getByText('Excedente')).toBeTruthy();
  });

  // ── SP4. Exact match indicator ──────────────────────────────────────────────

  it('SP4: shows pago completo when payments match total exactly', () => {
    const lines = [
      createPaymentLine('10000', 'efectivo'),
      createPaymentLine('20000', 'transferencia'),
    ];
    renderPanel({ lines, total: 30000 });
    expect(screen.getByText(/Pago completo/)).toBeTruthy();
  });

  // ── SP5. Vuelto for cash ────────────────────────────────────────────────────

  it('SP5: shows vuelto when cash received > cash line total', () => {
    const lines = [createPaymentLine('8500', 'efectivo')];
    renderPanel({ lines, total: 8500, cashReceived: '10000' });
    expect(screen.getByText('Vuelto')).toBeTruthy();
  });

  // ── SP6. API method mapping ─────────────────────────────────────────────────

  it('SP6: toApiPaymentLineMethod maps correctly', () => {
    expect(toApiPaymentLineMethod('efectivo')).toBe('cash');
    expect(toApiPaymentLineMethod('debito')).toBe('debit');
    expect(toApiPaymentLineMethod('credito')).toBe('credit');
    expect(toApiPaymentLineMethod('transferencia')).toBe('transfer');
    expect(toApiPaymentLineMethod('mercadopago')).toBe('wallet');
    expect(toApiPaymentLineMethod('otro')).toBe('account');
  });

  // ── SP7. Auto-fill remaining ────────────────────────────────────────────────

  it('SP7: auto-fills remaining amount when adding a new line', () => {
    const onLinesChange = vi.fn();
    const lines = [createPaymentLine('10000', 'efectivo')];
    renderPanel({ lines, onLinesChange, total: 30000 });
    const addBtn = screen.getByText(/Agregar otro medio de pago/);
    fireEvent.click(addBtn);
    const newLines = onLinesChange.mock.calls[0]![0] as PaymentLine[];
    expect(newLines).toHaveLength(2);
    expect(newLines[1]!.amount).toBe('20000.00');
  });
});

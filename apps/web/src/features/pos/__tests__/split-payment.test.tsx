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

  it('SP3b: shows excess warning when payments over total', () => {
    const lines = [createPaymentLine('35000', 'efectivo')];
    renderPanel({ lines, total: 30000 });
    expect(screen.getByText(/Los montos superan el total/)).toBeTruthy();
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

  // ── SP8. Cash change toggle ─────────────────────────────────────────────────

  it('SP8: cash change toggle shows/hides cash received input', () => {
    const lines = [createPaymentLine('10000', 'efectivo')];
    renderPanel({ lines, total: 10000 });

    // Toggle exists
    const toggle = screen.getByRole('checkbox', { name: /calcular vuelto/i });
    expect(toggle).toBeTruthy();

    // Cash received input NOT visible initially
    expect(screen.queryByLabelText(/con cuánto paga/i)).toBeNull();

    // Enable toggle
    fireEvent.click(toggle);

    // Cash received input now visible
    expect(screen.getByLabelText(/con cuánto paga/i)).toBeTruthy();
  });

  it('SP8b: disabling toggle clears cash received', () => {
    const onCashReceivedChange = vi.fn();
    const lines = [createPaymentLine('10000', 'efectivo')];
    renderPanel({ lines, total: 10000, onCashReceivedChange });

    const toggle = screen.getByRole('checkbox', { name: /calcular vuelto/i });
    fireEvent.click(toggle); // on
    fireEvent.click(toggle); // off

    expect(onCashReceivedChange).toHaveBeenCalledWith('');
  });

  // ── SP9. Updated labels ─────────────────────────────────────────────────────

  it('SP9: shows "Monto a cobrar" label instead of "Monto"', () => {
    renderPanel();
    expect(screen.getByText('Monto a cobrar')).toBeTruthy();
    expect(screen.queryByText('Monto')).toBeNull();
  });

  it('SP9b: summary shows "Cobrado" instead of "Pagado"', () => {
    const lines = [createPaymentLine('30000', 'efectivo')];
    renderPanel({ lines, total: 30000 });
    expect(screen.getByText('Cobrado')).toBeTruthy();
    expect(screen.queryByText('Pagado')).toBeNull();
  });

  // ── SP10. Summary vuelto ────────────────────────────────────────────────────

  it('SP10: summary shows "Vuelto" row when cash change exists', () => {
    const lines = [createPaymentLine('30000', 'efectivo')];
    renderPanel({ lines, total: 30000, cashReceived: '35000' });
    const vueltoTexts = screen.getAllByText('Vuelto');
    expect(vueltoTexts.length).toBeGreaterThanOrEqual(1);
  });

  // ── SP11. Exact payment states ──────────────────────────────────────────────

  it('SP11: shows pago completo with no excess warning for exact payment', () => {
    const lines = [createPaymentLine('30000', 'efectivo')];
    renderPanel({ lines, total: 30000 });
    expect(screen.getByText(/Pago completo/)).toBeTruthy();
    expect(screen.queryByText(/Los montos superan/)).toBeNull();
  });

  // ── SP12. Mixed payment exact ───────────────────────────────────────────────

  it('SP12: mixed payment shows pago completo when sum matches total', () => {
    const lines = [
      createPaymentLine('10000', 'efectivo'),
      createPaymentLine('20000', 'transferencia'),
    ];
    renderPanel({ lines, total: 30000 });
    expect(screen.getByText('Cobrado')).toBeTruthy();
    expect(screen.getByText(/Pago completo/)).toBeTruthy();
  });

  // ── SP13. isAutoAmount flag ─────────────────────────────────────────────────

  it('SP13: createPaymentLine without amount sets isAutoAmount true', () => {
    const line = createPaymentLine();
    expect(line.isAutoAmount).toBe(true);
    expect(line.amount).toBe('');
  });

  it('SP13b: createPaymentLine with amount sets isAutoAmount false', () => {
    const line = createPaymentLine('5000', 'efectivo');
    expect(line.isAutoAmount).toBe(false);
    expect(line.amount).toBe('5000');
  });

  // ── SP14. Editing amount marks line as manual ───────────────────────────────

  it('SP14: editing amount marks line as manual (isAutoAmount false)', () => {
    const onLinesChange = vi.fn();
    const line = createPaymentLine();
    // isAutoAmount starts true
    expect(line.isAutoAmount).toBe(true);
    renderPanel({ lines: [line], onLinesChange, total: 10000 });

    // User types into amount input
    const amountInput = screen.getByPlaceholderText('0');
    fireEvent.change(amountInput, { target: { value: '5000' } });

    const updated = onLinesChange.mock.calls[0]![0] as PaymentLine[];
    expect(updated[0]!.amount).toBe('5000');
    expect(updated[0]!.isAutoAmount).toBe(false);
  });

  it('SP14b: changing method does not mark amount as manual', () => {
    const onLinesChange = vi.fn();
    const line: PaymentLine = { ...createPaymentLine(), amount: '10000', isAutoAmount: true };
    renderPanel({ lines: [line], onLinesChange, total: 10000 });

    const methodSelect = screen.getByRole('combobox');
    fireEvent.change(methodSelect, { target: { value: 'transferencia' } });

    const updated = onLinesChange.mock.calls[0]![0] as PaymentLine[];
    expect(updated[0]!.method).toBe('transferencia');
    expect(updated[0]!.isAutoAmount).toBe(true);
  });
});

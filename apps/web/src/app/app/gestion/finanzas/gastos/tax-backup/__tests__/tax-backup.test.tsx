import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { safeAmount, type FiscalProfile } from '@/lib/api/tax-backup';

// ── safeAmount helper tests ─────────────────────────────────────────────────

describe('safeAmount', () => {
  it('parses normal decimal string', () => {
    expect(safeAmount('1500.0000')).toBe(1500);
  });

  it('returns 0 for null', () => {
    expect(safeAmount(null)).toBe(0);
  });

  it('returns 0 for undefined', () => {
    expect(safeAmount(undefined)).toBe(0);
  });

  it('returns 0 for empty string', () => {
    expect(safeAmount('')).toBe(0);
  });

  it('returns 0 for non-numeric string', () => {
    expect(safeAmount('abc')).toBe(0);
  });

  it('never returns NaN', () => {
    const values = [null, undefined, '', 'NaN', 'abc', '0', '100.50'];
    for (const v of values) {
      const result = safeAmount(v);
      expect(Number.isNaN(result)).toBe(false);
    }
  });
});

// ── No residual service/alert API calls ─────────────────────────────────────

describe('tax-backup API module', () => {
  it('does not export listServices', async () => {
    const mod = await import('@/lib/api/tax-backup');
    expect('listServices' in mod).toBe(false);
  });

  it('does not export listAlerts', async () => {
    const mod = await import('@/lib/api/tax-backup');
    expect('listAlerts' in mod).toBe(false);
  });

  it('does not export resolveAlert', async () => {
    const mod = await import('@/lib/api/tax-backup');
    expect('resolveAlert' in mod).toBe(false);
  });

  it('does not export AlertStatus type or RecurringService', async () => {
    const mod = await import('@/lib/api/tax-backup');
    expect('AlertStatus' in mod).toBe(false);
    expect('RecurringService' in mod).toBe(false);
  });
});

// ── Profile rendering with source_* fields ──────────────────────────────────

// Minimal mock of the table row rendering logic (extracted from tax-backup-table)
function ProfileRow({ profile }: { profile: FiscalProfile }) {
  const amount = safeAmount(profile.source_amount);
  return (
    <tr data-testid="profile-row">
      <td data-testid="source-name">
        {profile.source_type === 'fixed_expense_period' && (
          <span data-testid="badge-fijo">Fijo</span>
        )}
        {profile.source_name || 'Sin nombre'}
      </td>
      <td data-testid="source-amount">
        {profile.source_amount != null ? `$${amount.toFixed(2)}` : '—'}
      </td>
    </tr>
  );
}

function renderRow(overrides: Partial<FiscalProfile> = {}) {
  const base: FiscalProfile = {
    id: 1,
    expense: 10,
    fixed_expense_period: null,
    source_type: 'expense',
    source_name: 'Gasto de prueba',
    source_amount: '1500.0000',
    source_due_date: '2026-03-15',
    source_period_label: null,
    source_status: 'pending',
    allocation_type: 'business',
    tax_status: 'registrado',
    tax_status_display: 'Registrado',
    is_capital_asset: false,
    doc_count: 0,
    created_at: '2026-03-15T00:00:00Z',
    ...overrides,
  };
  return render(
    <table>
      <tbody>
        <ProfileRow profile={base} />
      </tbody>
    </table>,
  );
}

describe('Profile rendering', () => {
  it('renders expense origin name and amount', () => {
    renderRow({ source_name: 'Compra insumos', source_amount: '2500.0000' });
    expect(screen.getByTestId('source-name')).toHaveTextContent('Compra insumos');
    expect(screen.getByTestId('source-amount')).toHaveTextContent('$2500.00');
  });

  it('renders fixed_expense_period origin with Fijo badge', () => {
    renderRow({
      source_type: 'fixed_expense_period',
      source_name: 'Alquiler — 2026-03',
      source_amount: '50000.0000',
      fixed_expense_period: 5,
      expense: null,
    });
    expect(screen.getByTestId('badge-fijo')).toBeInTheDocument();
    expect(screen.getByTestId('source-name')).toHaveTextContent('Alquiler — 2026-03');
    expect(screen.getByTestId('source-amount')).toHaveTextContent('$50000.00');
  });

  it('shows dash when source_amount is null', () => {
    renderRow({ source_amount: null });
    expect(screen.getByTestId('source-amount')).toHaveTextContent('—');
  });

  it('shows "Sin nombre" when source_name is empty', () => {
    renderRow({ source_name: '' });
    expect(screen.getByTestId('source-name')).toHaveTextContent('Sin nombre');
  });

  it('does not show NaN for any amount edge case', () => {
    // source_amount as various edge values
    const edgeCases = ['0', '0.00', null];
    for (const val of edgeCases) {
      const { unmount } = renderRow({ source_amount: val });
      const text = screen.getByTestId('source-amount').textContent ?? '';
      expect(text).not.toContain('NaN');
      unmount();
    }
  });
});

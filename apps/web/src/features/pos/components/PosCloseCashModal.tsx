'use client';

/**
 * PosCloseCashModal
 *
 * Modal to close the current POS cash session.
 * - Shows totals.cash_expected_total as reference.
 * - Allows entering closing_cash_counted (optional).
 * - Displays difference_amount from response with color coding.
 */

import { FormEvent, useState } from 'react';
import { Modal } from '@/components/ui/modal';
import { usePosCloseCashSession, usePosErrorHandler } from '@/features/pos/cash-hooks';
import { formatCurrency } from '@/features/cash/utils';
import type { PosCashSession } from '@/types/pos-cash';

interface Props {
  open: boolean;
  session: PosCashSession;
  onClose: () => void;
}

export function PosCloseCashModal({ open, session, onClose }: Props) {
  const mutation = usePosCloseCashSession();
  const handleError = usePosErrorHandler();

  const [countedCash, setCountedCash] = useState('');
  const [note, setNote] = useState('');
  const [closedSession, setClosedSession] = useState<PosCashSession | null>(null);
  const [error, setError] = useState('');

  const expectedTotal = session.totals?.cash_expected_total ?? '0';
  const counted = Number(countedCash || 0);
  const expected = Number(expectedTotal);
  const diff = countedCash ? counted - expected : null;

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');

    if (countedCash && Number(countedCash) < 0) {
      setError('El monto contado debe ser ≥ 0.');
      return;
    }

    try {
      const resp = await mutation.mutateAsync({
        closing_cash_counted: countedCash ? Number(countedCash).toFixed(2) : undefined,
        closing_note: note.trim() || undefined,
      });
      setClosedSession(resp.session);
    } catch (err) {
      setError(handleError(err));
    }
  };

  const handleDismiss = () => {
    setCountedCash('');
    setNote('');
    setError('');
    setClosedSession(null);
    onClose();
  };

  if (closedSession) {
    const finalDiff = closedSession.difference_amount !== null
      ? Number(closedSession.difference_amount) : null;
    const isNegative = finalDiff !== null && finalDiff < 0;
    const isPositive = finalDiff !== null && finalDiff > 0;

    return (
      <Modal open={open} title="Caja cerrada" onClose={handleDismiss}>
        <div className="space-y-4">
          <div className="rounded-xl bg-emerald-50 px-5 py-4 text-sm text-emerald-800">
            <p className="font-semibold text-base">Sesión cerrada correctamente</p>
            <p className="mt-1 text-emerald-600">
              {new Date(closedSession.closed_at ?? '').toLocaleString('es-AR', {
                dateStyle: 'medium',
                timeStyle: 'short',
              })}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Esperado</p>
              <p className="mt-1 text-lg font-bold text-slate-900">
                {formatCurrency(closedSession.expected_cash_total)}
              </p>
            </div>
            {closedSession.closing_cash_counted !== null && (
              <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Contado</p>
                <p className="mt-1 text-lg font-bold text-slate-900">
                  {formatCurrency(closedSession.closing_cash_counted)}
                </p>
              </div>
            )}
          </div>

          {finalDiff !== null && (
            <div className={`rounded-xl px-4 py-3 text-sm font-semibold ${
              isNegative
                ? 'bg-rose-50 text-rose-700 border border-rose-200'
                : isPositive
                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                  : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
            }`}>
              {isNegative && `Faltante: ${formatCurrency(Math.abs(finalDiff))}`}
              {isPositive && `Sobrante: ${formatCurrency(finalDiff)}`}
              {!isNegative && !isPositive && 'Sin diferencia — caja exacta ✓'}
            </div>
          )}

          <div className="flex justify-end pt-2">
            <button
              type="button"
              onClick={handleDismiss}
              className="rounded-xl bg-slate-900 px-5 py-2 text-sm font-semibold text-white"
            >
              Cerrar
            </button>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal open={open} title="Cerrar caja" onClose={handleDismiss}>
      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="rounded-xl bg-slate-50 px-4 py-3 text-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Efectivo esperado</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">
            {formatCurrency(expectedTotal)}
          </p>
          <p className="text-xs text-slate-400 mt-0.5">
            Apertura + ingresos (efectivo) − egresos
          </p>
        </div>

        <label className="block text-sm text-slate-600">
          Efectivo contado (opcional)
          <input
            type="number"
            min="0"
            step="0.01"
            value={countedCash}
            onChange={(e) => setCountedCash(e.target.value)}
            placeholder={`Referencia: ${formatCurrency(expectedTotal)}`}
            className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-base text-slate-900 focus:border-slate-400 focus:outline-none"
          />
        </label>

        {countedCash && diff !== null && (
          <div className={`rounded-xl px-4 py-2 text-sm font-medium ${
            diff < 0
              ? 'bg-rose-50 text-rose-700 border border-rose-200'
              : diff > 0
                ? 'bg-amber-50 text-amber-700 border border-amber-200'
                : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
          }`}>
            {diff < 0 && `Posible faltante: ${formatCurrency(Math.abs(diff))}`}
            {diff > 0 && `Posible sobrante: ${formatCurrency(diff)}`}
            {diff === 0 && 'Sin diferencia'}
          </div>
        )}

        <label className="block text-sm text-slate-600">
          Nota de cierre (opcional)
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Ejemplo: Cierre de turno noche"
            maxLength={200}
            className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
          />
        </label>

        {error && (
          <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={handleDismiss}
            className="rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="rounded-xl bg-rose-600 px-5 py-2 text-sm font-semibold text-white disabled:opacity-60 hover:bg-rose-700"
          >
            {mutation.isPending ? 'Cerrando…' : 'Cerrar caja'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

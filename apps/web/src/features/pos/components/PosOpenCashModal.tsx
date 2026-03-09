'use client';

/**
 * PosOpenCashModal
 *
 * Modal used to open a new POS cash session.
 * - Uses X-Employee-Token via usePosOpenCashSession hook.
 * - Handles 400 "already open" gracefully.
 * - Does NOT call admin cash API.
 */

import { FormEvent, useState } from 'react';
import { Modal } from '@/components/ui/modal';
import { ApiError } from '@/lib/api/client';
import { usePosOpenCashSession, usePosErrorHandler } from '@/features/pos/cash-hooks';

interface Props {
  open: boolean;
  onClose: () => void;
  onAlreadyOpen: () => void;
}

export function PosOpenCashModal({ open, onClose, onAlreadyOpen }: Props) {
  const mutation = usePosOpenCashSession();
  const handleError = usePosErrorHandler();

  const [amount, setAmount] = useState('0');
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');

    const numeric = Number(amount);
    if (Number.isNaN(numeric) || numeric < 0) {
      setError('Ingresá un importe válido (≥ 0).');
      return;
    }

    try {
      await mutation.mutateAsync({
        opening_cash_amount: numeric.toFixed(2),
      });
      setAmount('0');
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        const detail = (err.payload as { detail?: string } | undefined)?.detail ?? '';
        if (detail.toLowerCase().includes('sesión de caja abierta')) {
          // Already open — go fetch current instead of showing error
          onAlreadyOpen();
          onClose();
          return;
        }
      }
      setError(handleError(err));
    }
  };

  return (
    <Modal open={open} title="Abrir caja" onClose={onClose}>
      <form className="space-y-4" onSubmit={handleSubmit}>
        <p className="text-sm text-slate-500">
          Ingresá el efectivo inicial en caja. Podés dejarlo en&nbsp;
          <span className="font-medium">$ 0</span> si no tenés fondo inicial.
        </p>

        <label className="block text-sm text-slate-600">
          Efectivo inicial
          <input
            type="number"
            min="0"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-base text-slate-900 focus:border-slate-400 focus:outline-none"
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
            onClick={onClose}
            className="rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="rounded-xl bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {mutation.isPending ? 'Abriendo…' : 'Abrir caja'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

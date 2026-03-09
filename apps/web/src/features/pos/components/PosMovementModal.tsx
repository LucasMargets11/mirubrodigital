'use client';

/**
 * PosMovementModal
 *
 * Modal to register a cash IN/OUT movement in the current POS session.
 * - Uses X-Employee-Token via usePosCreateCashMovement hook.
 * - Validates amount > 0 before submitting.
 */

import { FormEvent, useState } from 'react';
import { Modal } from '@/components/ui/modal';
import { usePosCreateCashMovement, usePosErrorHandler } from '@/features/pos/cash-hooks';
import type { PosCashMovementCategory, PosCashMovementMethod, PosCashMovementType } from '@/types/pos-cash';

const MOVEMENT_TYPE_OPTIONS: { value: PosCashMovementType; label: string }[] = [
  { value: 'in', label: 'Ingreso' },
  { value: 'out', label: 'Egreso' },
];

const CATEGORY_OPTIONS: { value: PosCashMovementCategory; label: string }[] = [
  { value: 'deposit', label: 'Depósito' },
  { value: 'withdraw', label: 'Retiro' },
  { value: 'expense', label: 'Gasto' },
  { value: 'other', label: 'Otro' },
];

const METHOD_OPTIONS: { value: PosCashMovementMethod; label: string }[] = [
  { value: 'cash', label: 'Efectivo' },
  { value: 'transfer', label: 'Transferencia' },
  { value: 'debit', label: 'Débito' },
  { value: 'credit', label: 'Crédito' },
  { value: 'wallet', label: 'Billetera' },
  { value: 'account', label: 'Cuenta corriente' },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export function PosMovementModal({ open, onClose }: Props) {
  const mutation = usePosCreateCashMovement();
  const handleError = usePosErrorHandler();

  const [movementType, setMovementType] = useState<PosCashMovementType>('out');
  const [category, setCategory] = useState<PosCashMovementCategory>('other');
  const [method, setMethod] = useState<PosCashMovementMethod>('cash');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const reset = () => {
    setAmount('');
    setNote('');
    setError('');
    setSuccess('');
    setMovementType('out');
    setCategory('other');
    setMethod('cash');
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    const numeric = Number(amount);
    if (!numeric || numeric < 0.01) {
      setError('Ingresá un monto válido (mínimo $ 0.01).');
      return;
    }

    try {
      await mutation.mutateAsync({
        movement_type: movementType,
        category,
        method,
        amount: numeric.toFixed(2),
        note: note.trim(),
      });
      setSuccess('Movimiento registrado correctamente.');
      setTimeout(() => {
        reset();
        onClose();
      }, 900);
    } catch (err) {
      setError(handleError(err));
    }
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  return (
    <Modal open={open} title="Registrar movimiento" onClose={handleClose}>
      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm text-slate-600">
            Tipo
            <select
              value={movementType}
              onChange={(e) => setMovementType(e.target.value as PosCashMovementType)}
              className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700"
            >
              {MOVEMENT_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>

          <label className="block text-sm text-slate-600">
            Categoría
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as PosCashMovementCategory)}
              className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700"
            >
              {CATEGORY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
        </div>

        <label className="block text-sm text-slate-600">
          Método de pago
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value as PosCashMovementMethod)}
            className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700"
          >
            {METHOD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>

        <label className="block text-sm text-slate-600">
          Monto
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-base text-slate-900 focus:border-slate-400 focus:outline-none"
          />
        </label>

        <label className="block text-sm text-slate-600">
          Nota (opcional)
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Descripción del movimiento…"
            maxLength={200}
            className="mt-1 w-full rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
          />
        </label>

        {error && (
          <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
            {error}
          </p>
        )}
        {success && (
          <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
            {success}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={handleClose}
            className="rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="rounded-xl bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:opacity-60"
          >
            {mutation.isPending ? 'Registrando…' : 'Registrar'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

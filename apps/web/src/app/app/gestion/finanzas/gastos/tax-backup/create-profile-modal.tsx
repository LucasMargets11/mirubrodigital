"use client";

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';

import {
  createProfile,
  taxBackupKeys,
  type AllocationType,
} from '@/lib/api/tax-backup';
import type { Expense } from '@/lib/api/treasury';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { Currency } from '../../components/currency';
import { ALLOCATION_CONFIG } from './constants';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  /** Expenses that do NOT already have a fiscal profile */
  availableExpenses: Expense[];
}

export function CreateProfileModal({
  isOpen,
  onClose,
  availableExpenses,
}: Props) {
  const queryClient = useQueryClient();
  const [expenseId, setExpenseId] = useState('');
  const [allocation, setAllocation] = useState<AllocationType>('business');

  const mutation = useMutation({
    mutationFn: createProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taxBackupKeys.all });
      onClose();
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!expenseId) return;
    mutation.mutate({
      expense: Number(expenseId),
      allocation_type: allocation,
    });
  }

  const selectedExpense = availableExpenses.find(
    (e) => e.id === Number(expenseId),
  );

  return (
    <Modal open={isOpen} onClose={onClose} title="Nuevo perfil impositivo">
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Expense selector */}
        <div>
          <label className="block text-sm font-medium text-slate-700">
            Gasto a vincular
          </label>
          <select
            required
            value={expenseId}
            onChange={(e) => setExpenseId(e.target.value)}
            className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-slate-900 focus:ring-slate-900 sm:text-sm p-2 border"
          >
            <option value="">Seleccionar gasto...</option>
            {availableExpenses.map((exp) => (
              <option key={exp.id} value={exp.id}>
                {exp.name} — ${parseFloat(exp.amount).toFixed(2)}
              </option>
            ))}
          </select>
          {selectedExpense && (
            <p className="text-xs text-slate-500 mt-1">
              Monto: <Currency amount={parseFloat(selectedExpense.amount)} />
              {selectedExpense.category_name &&
                ` · ${selectedExpense.category_name}`}
            </p>
          )}
        </div>

        {/* Allocation type */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Asignación
          </label>
          <div className="space-y-2">
            {(
              Object.entries(ALLOCATION_CONFIG) as [
                AllocationType,
                (typeof ALLOCATION_CONFIG)[AllocationType],
              ][]
            ).map(([key, config]) => (
              <label
                key={key}
                className={`flex items-start gap-3 p-3 rounded-lg border-2 cursor-pointer transition-colors ${
                  allocation === key
                    ? 'border-indigo-500 bg-indigo-50/50'
                    : 'border-slate-200 hover:border-slate-300'
                }`}
              >
                <input
                  type="radio"
                  name="allocation"
                  value={key}
                  checked={allocation === key}
                  onChange={() => setAllocation(key)}
                  className="mt-0.5"
                />
                <div>
                  <span className="text-sm font-medium text-slate-900">
                    {config.icon} {config.label}
                  </span>
                  <p className="text-xs text-slate-500">{config.description}</p>
                </div>
              </label>
            ))}
          </div>
        </div>

        {mutation.error && (
          <p className="text-xs text-rose-600">
            Error: {(mutation.error as Error).message}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-4">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="submit"
            disabled={!expenseId || mutation.isPending}
          >
            {mutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Crear perfil
          </Button>
        </div>
      </form>
    </Modal>
  );
}

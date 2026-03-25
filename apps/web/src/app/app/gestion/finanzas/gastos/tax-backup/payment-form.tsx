"use client";

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';

import { addPayment, taxBackupKeys, type PaymentMethod } from '@/lib/api/tax-backup';
import { Button } from '@/components/ui/button';
import { PAYMENT_METHOD_OPTIONS } from './constants';

interface Props {
  profileId: number;
  onAdded: () => void;
  onCancel: () => void;
}

export function PaymentForm({ profileId, onAdded, onCancel }: Props) {
  const queryClient = useQueryClient();
  const [method, setMethod] = useState<PaymentMethod>('transfer');
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10));
  const [amount, setAmount] = useState('');
  const [reference, setReference] = useState('');
  const [proofFile, setProofFile] = useState<File | null>(null);

  const mutation = useMutation({
    mutationFn: (fd: FormData) => addPayment(profileId, fd),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: taxBackupKeys.profile(profileId),
      });
      onAdded();
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const fd = new FormData();
    fd.append('payment_method', method);
    fd.append('payment_date', paymentDate);
    if (amount) fd.append('amount', amount);
    if (reference) fd.append('reference', reference);
    if (proofFile) fd.append('proof_file', proofFile);
    mutation.mutate(fd);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 p-4 bg-slate-50 rounded-xl border border-slate-200">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Medio de pago
          </label>
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value as PaymentMethod)}
            className="block w-full rounded-md border border-slate-300 p-2 text-sm"
          >
            {PAYMENT_METHOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Fecha de pago
          </label>
          <input
            required
            type="date"
            value={paymentDate}
            onChange={(e) => setPaymentDate(e.target.value)}
            className="block w-full rounded-md border border-slate-300 p-2 text-sm"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Monto
          </label>
          <input
            required
            type="number"
            step="0.01"
            min="0"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            className="block w-full rounded-md border border-slate-300 p-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Referencia / Nro operación
          </label>
          <input
            type="text"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="Ej. 0070001234567"
            className="block w-full rounded-md border border-slate-300 p-2 text-sm"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-slate-600 mb-1">
          Comprobante de pago (opcional)
        </label>
        {proofFile ? (
          <div className="flex items-center gap-2 text-sm text-slate-700 bg-white p-2 rounded-md border border-slate-200">
            <span className="truncate flex-1">{proofFile.name}</span>
            <button
              type="button"
              onClick={() => setProofFile(null)}
              className="text-slate-400 hover:text-slate-600 text-xs"
            >
              Quitar
            </button>
          </div>
        ) : (
          <input
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.webp"
            onChange={(e) => setProofFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-slate-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200"
          />
        )}
      </div>

      {mutation.error && (
        <p className="text-xs text-rose-600">
          Error al registrar pago: {(mutation.error as Error).message}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" size="sm" disabled={mutation.isPending}>
          {mutation.isPending && (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          )}
          Registrar pago
        </Button>
      </div>
    </form>
  );
}

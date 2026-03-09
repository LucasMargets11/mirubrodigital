'use client';

/**
 * CreateCustomerDialog
 *
 * Modal for creating a minimal customer from the POS terminal.
 * On success, calls onCreated(customer) so the parent can auto-select it.
 *
 * Focus:
 * - Autofocuses the name field when opened.
 * - Returns focus to the triggering element on close via the onClose callback.
 *
 * Accessibility:
 * - Uses the existing <Modal> component (role=dialog, aria-modal=true).
 * - Inline error shown with role="alert".
 * - All inputs have explicit <label> elements.
 */

import { useEffect, useRef, useState } from 'react';
import { Modal } from '@/components/ui/modal';
import { usePosCreateCustomer, usePosErrorHandler } from '@/features/pos/cash-hooks';
import type { PosCustomerSummary } from '@/types/pos-cash';

interface CreateCustomerDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (customer: PosCustomerSummary) => void;
}

export function CreateCustomerDialog({ open, onClose, onCreated }: CreateCustomerDialogProps) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');

  const nameRef = useRef<HTMLInputElement>(null);
  const createMutation = usePosCreateCustomer();
  const handleError = usePosErrorHandler();

  // Reset and focus on open
  useEffect(() => {
    if (open) {
      setName('');
      setPhone('');
      setEmail('');
      setError('');
      setTimeout(() => nameRef.current?.focus(), 80);
    }
  }, [open]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError('El nombre del cliente es obligatorio.');
      nameRef.current?.focus();
      return;
    }
    setError('');

    try {
      const customer = await createMutation.mutateAsync({
        name: name.trim(),
        phone: phone.trim() || undefined,
        email: email.trim() || undefined,
      });
      onCreated(customer);
    } catch (err) {
      setError(handleError(err));
    }
  }

  const isPending = createMutation.isPending;

  return (
    <Modal open={open} onClose={onClose} title="Nuevo cliente">
      <form onSubmit={handleSubmit} noValidate>
        <div className="space-y-4">
          {/* Name */}
          <div>
            <label htmlFor="customer-name" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Nombre <span aria-hidden className="text-rose-400">*</span>
            </label>
            <input
              id="customer-name"
              ref={nameRef}
              type="text"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isPending}
              aria-required="true"
              aria-describedby={error ? 'customer-form-error' : undefined}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60"
            />
          </div>

          {/* Phone */}
          <div>
            <label htmlFor="customer-phone" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Teléfono
            </label>
            <input
              id="customer-phone"
              type="tel"
              autoComplete="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={isPending}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60"
            />
          </div>

          {/* Email */}
          <div>
            <label htmlFor="customer-email" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Email
            </label>
            <input
              id="customer-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isPending}
              className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-300 disabled:opacity-60"
            />
          </div>

          {/* Error */}
          {error && (
            <p id="customer-form-error" role="alert" className="rounded-xl bg-rose-50 px-4 py-2.5 text-sm text-rose-700">
              {error}
            </p>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isPending}
              className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isPending || !name.trim()}
              className="rounded-xl bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {isPending ? 'Guardando…' : 'Crear cliente'}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}

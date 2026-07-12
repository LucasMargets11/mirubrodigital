"use client";

import { useState, useRef } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import type { AdminSubscriptionDetail } from '@/lib/admin/types';
import { planLabel, statusLabel, formatDate } from '@/lib/admin/display';

// ── Helpers ──────────────────────────────────────────────────────────────────

function maskId(id: string): string {
  if (!id || id.length <= 8) return '***';
  return `${id.slice(0, 4)}...${id.slice(-4)}`;
}

function lastPaidAt(subscription: AdminSubscriptionDetail): string | null {
  const events = subscription.invoice_events ?? [];
  const sorted = [...events]
    .filter((e) => e.paid_at)
    .sort((a, b) => (a.paid_at! < b.paid_at! ? 1 : -1));
  return sorted[0]?.paid_at ?? null;
}

// ── Types ─────────────────────────────────────────────────────────────────────

type CancelSubscriptionModalProps = {
  subscription: AdminSubscriptionDetail;
  onClose: () => void;
  onSuccess: () => void;
};

// ── Component ─────────────────────────────────────────────────────────────────

export function CancelSubscriptionModal({
  subscription,
  onClose,
  onSuccess,
}: CancelSubscriptionModalProps) {
  const [reason, setReason] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitRef = useRef(false);

  const ownerEmail =
    subscription.business
      ? `(negocio ID ${subscription.business.id})`
      : '—';

  const lastPayment = lastPaidAt(subscription);

  async function handleConfirm() {
    if (submitRef.current || loading) return;
    if (!reason.trim()) {
      setError('El motivo es obligatorio.');
      return;
    }

    submitRef.current = true;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(
        `/api/v1/platform-admin/subscriptions/${subscription.id}/cancel/`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ reason: reason.trim() }),
        },
      );

      if (res.ok) {
        onSuccess();
      } else {
        const data = await res.json().catch(() => ({}));
        setError(
          data.detail ??
            `Error al cancelar la suscripción (HTTP ${res.status}). Reintentá.`,
        );
        submitRef.current = false;
      }
    } catch {
      setError('Error de red. Verificá tu conexión e intentá de nuevo.');
      submitRef.current = false;
    } finally {
      setLoading(false);
    }
  }

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cancel-modal-title"
    >
      <div className="w-full max-w-lg rounded-xl bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-100 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
              <AlertTriangle className="h-5 w-5 text-red-600" />
            </div>
            <div>
              <h2
                id="cancel-modal-title"
                className="text-lg font-semibold text-slate-900"
              >
                Cancelar suscripción inmediatamente
              </h2>
              <p className="mt-0.5 text-xs text-red-600 font-medium">
                El acceso se revoca en el momento de confirmar.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={loading}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-50"
            aria-label="Cerrar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-5 px-6 py-5">
          {/* Warning banner */}
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
            <p className="font-medium">
              Esta es una cancelación inmediata. El cliente perderá el acceso
              en el momento de confirmar, sin esperar el fin del período.
            </p>
            <p className="mt-1">
              Se cancelarán los futuros cobros de Mercado Pago y el cliente
              perderá el acceso inmediatamente.
            </p>
            <p className="mt-1 font-medium">
              El pago ya realizado no será reembolsado. Esta acción no se puede
              revertir automáticamente.
            </p>
          </div>

          {/* Subscription summary */}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <div>
              <dt className="text-slate-500">Negocio</dt>
              <dd className="font-medium text-slate-800">
                {subscription.business?.name ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">ID negocio</dt>
              <dd className="text-slate-700">{ownerEmail}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Plan</dt>
              <dd className="font-medium text-slate-800">
                {planLabel(subscription.plan_code)}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Estado actual</dt>
              <dd className="font-medium text-slate-800">
                {statusLabel(subscription.status)}
              </dd>
            </div>
            {subscription.provider_sub_id && (
              <div>
                <dt className="text-slate-500">ID externo (MP)</dt>
                <dd className="font-mono text-xs text-slate-600">
                  {maskId(subscription.provider_sub_id)}
                </dd>
              </div>
            )}
            {lastPayment && (
              <div>
                <dt className="text-slate-500">Último pago</dt>
                <dd className="text-slate-700">{formatDate(lastPayment)}</dd>
              </div>
            )}
          </dl>

          {/* Access loss warning */}
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            ⚠️ El cliente perderá el acceso pago inmediatamente. Podrá volver a
            contratar un plan desde el onboarding.
          </p>

          {/* Reason field */}
          <div>
            <label
              htmlFor="cancel-reason"
              className="mb-1.5 block text-sm font-medium text-slate-700"
            >
              Motivo de cancelación{' '}
              <span className="text-red-500" aria-hidden="true">
                *
              </span>
            </label>
            <textarea
              id="cancel-reason"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Ej.: Cuenta utilizada para prueba de checkout"
              maxLength={512}
              disabled={loading}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-red-400 focus:outline-none focus:ring-2 focus:ring-red-100 disabled:bg-slate-50"
            />
            <p className="mt-1 text-xs text-slate-400">
              {reason.length}/512 caracteres
            </p>
          </div>

          {/* Error message */}
          {error && (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
            >
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 border-t border-slate-100 px-6 py-4">
          <button
            onClick={onClose}
            disabled={loading}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            onClick={handleConfirm}
            disabled={loading || !reason.trim()}
            className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading && (
              <span
                className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
                aria-hidden="true"
              />
            )}
            {loading ? 'Cancelando…' : 'Confirmar cancelación'}
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Route } from 'next';

import { apiPost, ApiError } from '@/lib/api/client';

import type { TenantTicketCreateResponse } from '../types';

const CATEGORY_OPTIONS = [
  { value: 'billing', label: 'Facturación / Pagos' },
  { value: 'technical', label: 'Problema técnico' },
  { value: 'account', label: 'Cuenta / Acceso' },
  { value: 'feature_request', label: 'Solicitud de funcionalidad' },
  { value: 'other', label: 'Otro' },
];

export function NuevoTicketClient() {
  const router = useRouter();
  const [subject, setSubject] = useState('');
  const [category, setCategory] = useState('other');
  const [body, setBody] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = subject.trim().length > 0 && body.trim().length > 0 && !submitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError(null);

    try {
      const res = await apiPost<TenantTicketCreateResponse>('/api/v1/support/tickets/', {
        subject: subject.trim(),
        category,
        body: body.trim(),
      });
      router.push(`/app/soporte/${res.id}` as Route);
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = (err.payload as { detail?: string })?.detail;
        setError(detail ?? 'Error al crear el ticket. Intentá de nuevo.');
      } else {
        setError('Error inesperado. Intentá de nuevo.');
      }
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-6">
      <header>
        <p className="text-xs uppercase tracking-wide text-slate-400">Soporte</p>
        <h1 className="text-3xl font-semibold text-slate-900">Nuevo ticket</h1>
        <p className="text-sm text-slate-500">Describí tu consulta o problema y te responderemos a la brevedad.</p>
      </header>

      <form onSubmit={handleSubmit} className="max-w-2xl space-y-5 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        {error && (
          <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
            {error}
          </p>
        )}

        <div className="space-y-1.5">
          <label htmlFor="subject" className="text-sm font-medium text-slate-700">
            Asunto
          </label>
          <input
            id="subject"
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            maxLength={200}
            placeholder="Ej: No puedo generar facturas"
            className="w-full rounded-2xl border border-slate-200 px-4 py-2.5 text-sm focus:border-slate-900 focus:outline-none"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="category" className="text-sm font-medium text-slate-700">
            Categoría
          </label>
          <select
            id="category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-2xl border border-slate-200 px-4 py-2.5 text-sm text-slate-600 focus:border-slate-900 focus:outline-none"
          >
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="body" className="text-sm font-medium text-slate-700">
            Mensaje
          </label>
          <textarea
            id="body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            maxLength={5000}
            rows={6}
            placeholder="Contanos qué pasó, qué esperabas que sucediera o qué necesitás…"
            className="w-full resize-y rounded-2xl border border-slate-200 px-4 py-2.5 text-sm focus:border-slate-900 focus:outline-none"
          />
          <p className="text-right text-xs text-slate-400">{body.length} / 5000</p>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-full bg-slate-900 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Enviando…' : 'Enviar ticket'}
          </button>
          <button
            type="button"
            onClick={() => router.push('/app/soporte' as Route)}
            className="rounded-full border border-slate-200 px-6 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            Cancelar
          </button>
        </div>
      </form>
    </section>
  );
}

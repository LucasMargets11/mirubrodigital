"use client";

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Send } from 'lucide-react';

import { SectionCard } from '@/components/admin/section-card';

export function NuevoTicketForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [businessId, setBusinessId] = useState('');
  const [subscriptionId, setSubscriptionId] = useState('');
  const [subject, setSubject] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [priority, setPriority] = useState('medium');
  const [category, setCategory] = useState('other');
  const [firstMessage, setFirstMessage] = useState('');

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!businessId.trim() || !subject.trim()) return;
      setSubmitting(true);
      setError(null);
      try {
        const payload: Record<string, string> = {
          business_id: businessId.trim(),
          subject: subject.trim(),
          priority,
          category,
        };
        if (subscriptionId.trim()) payload.subscription_id = subscriptionId.trim();
        if (contactEmail.trim()) payload.contact_email = contactEmail.trim();
        if (firstMessage.trim()) payload.body = firstMessage.trim();

        const res = await fetch('/api/v1/platform-admin/tickets/create/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(payload),
        });

        if (res.ok) {
          const data = await res.json();
          router.push(`/admin/soporte/${data.id}`);
        } else {
          const data = await res.json().catch(() => null);
          setError(data?.detail ?? `Error ${res.status}: no se pudo crear el ticket.`);
        }
      } catch {
        setError('Error de red. Intente nuevamente.');
      } finally {
        setSubmitting(false);
      }
    },
    [businessId, subscriptionId, subject, contactEmail, priority, category, firstMessage, router],
  );

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-6">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <SectionCard title="Datos del ticket">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              ID del negocio *
            </label>
            <input
              type="text"
              value={businessId}
              onChange={(e) => setBusinessId(e.target.value)}
              required
              placeholder="Ej: 42"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              ID de suscripción (opcional)
            </label>
            <input
              type="text"
              value={subscriptionId}
              onChange={(e) => setSubscriptionId(e.target.value)}
              placeholder="UUID de la suscripción"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              Asunto *
            </label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              required
              maxLength={200}
              placeholder="Descripción breve del problema"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              Email de contacto
            </label>
            <input
              type="email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              placeholder="cliente@ejemplo.com"
              className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              Prioridad
            </label>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <option value="low">Baja</option>
              <option value="medium">Media</option>
              <option value="high">Alta</option>
              <option value="urgent">Urgente</option>
            </select>
          </div>

          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
              Categoría
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <option value="billing">Facturación / Pagos</option>
              <option value="technical">Problema técnico</option>
              <option value="account">Cuenta / Acceso</option>
              <option value="feature_request">Solicitud funcionalidad</option>
              <option value="other">Otro</option>
            </select>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Primer mensaje (opcional)">
        <textarea
          value={firstMessage}
          onChange={(e) => setFirstMessage(e.target.value)}
          placeholder="Descripción detallada del problema o solicitud..."
          rows={5}
          maxLength={5000}
          className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-500 resize-none"
        />
      </SectionCard>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={!businessId.trim() || !subject.trim() || submitting}
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="h-4 w-4" />
          {submitting ? 'Creando...' : 'Crear ticket'}
        </button>
        <button
          type="button"
          onClick={() => router.push('/admin/soporte')}
          className="rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}

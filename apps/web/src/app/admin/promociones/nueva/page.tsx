"use client";

import { useState, useEffect, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { getPublicApiBaseUrl } from '@/lib/api-url';
import type { AdminPromoOptions, AdminPlanOption } from '@/lib/admin/types';

const API_URL = getPublicApiBaseUrl();

type FormState = {
  code: string;
  name: string;
  description: string;
  discount_type: 'percent' | 'fixed_amount';
  discount_value: string;
  duration_cycles: string;
  selected_plan_codes: string[];
  starts_at: string;
  ends_at: string;
  max_redemptions: string;
  max_redemptions_per_business: string;
  active: boolean;
};

const INITIAL: FormState = {
  code: '',
  name: '',
  description: '',
  discount_type: 'percent',
  discount_value: '',
  duration_cycles: '1',
  selected_plan_codes: [],
  starts_at: '',
  ends_at: '',
  max_redemptions: '',
  max_redemptions_per_business: '1',
  active: true,
};

export default function NuevaPromoPage() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(INITIAL);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState('');
  const [isPending, startTransition] = useTransition();

  const [options, setOptions] = useState<AdminPromoOptions | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [selectedService, setSelectedService] = useState<string>('');

  useEffect(() => {
    (async () => {
      try {
        const resp = await fetch(`${API_URL}/api/v1/platform-admin/promo-codes/options/`, {
          credentials: 'include',
        });
        if (resp.ok) {
          const data: AdminPromoOptions = await resp.json();
          setOptions(data);
          if (data.services.length > 0) {
            setSelectedService(data.services[0].value);
          }
        }
      } finally {
        setOptionsLoading(false);
      }
    })();
  }, []);

  const filteredPlans: AdminPlanOption[] = options
    ? options.plans.filter((p) => !selectedService || p.service === selectedService)
    : [];

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
    const { name, value, type } = e.target;
    if (type === 'checkbox') {
      setForm((f) => ({ ...f, [name]: (e.target as HTMLInputElement).checked }));
    } else {
      setForm((f) => ({ ...f, [name]: value }));
    }
  }

  function togglePlanCode(code: string) {
    setForm((f) => {
      const has = f.selected_plan_codes.includes(code);
      return {
        ...f,
        selected_plan_codes: has
          ? f.selected_plan_codes.filter((c) => c !== code)
          : [...f.selected_plan_codes, code],
      };
    });
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!form.code.trim()) errs.code = 'Requerido';
    if (!form.name.trim()) errs.name = 'Requerido';
    if (!form.discount_value || parseFloat(form.discount_value) <= 0)
      errs.discount_value = 'Debe ser mayor a 0';
    if (form.discount_type === 'percent' && parseFloat(form.discount_value) > 100)
      errs.discount_value = 'No puede superar 100%';
    const cycles = parseInt(form.duration_cycles, 10);
    if (!form.duration_cycles || isNaN(cycles) || cycles < 1) errs.duration_cycles = 'Mínimo 1';
    if (form.selected_plan_codes.length === 0)
      errs.applies_to_plan_codes = 'Seleccioná al menos un plan';
    if (form.starts_at && form.ends_at && form.ends_at <= form.starts_at)
      errs.ends_at = 'Debe ser posterior a "Válido desde"';
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    startTransition(async () => {
      setServerError('');
      const payload: Record<string, unknown> = {
        code: form.code.trim(),
        name: form.name.trim(),
        description: form.description.trim(),
        discount_type: form.discount_type,
        discount_value: form.discount_value,
        duration_cycles: parseInt(form.duration_cycles, 10),
        applies_to_plan_codes: form.selected_plan_codes,
        applies_to_billing_periods: ['monthly'],
        active: form.active,
      };
      if (form.starts_at) payload.starts_at = form.starts_at;
      if (form.ends_at) payload.ends_at = form.ends_at;
      if (form.max_redemptions) payload.max_redemptions = parseInt(form.max_redemptions, 10);
      if (form.max_redemptions_per_business)
        payload.max_redemptions_per_business = parseInt(form.max_redemptions_per_business, 10);

      try {
        const resp = await fetch(`${API_URL}/api/v1/platform-admin/promo-codes/`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (resp.ok) {
          router.push('/admin/promociones');
        } else {
          const data = await resp.json().catch(() => ({}));
          if (typeof data === 'object' && data !== null) {
            const fieldErrors: Record<string, string> = {};
            for (const [k, v] of Object.entries(data)) {
              fieldErrors[k] = Array.isArray(v) ? v.join(' ') : String(v);
            }
            setErrors(fieldErrors);
          } else {
            setServerError('Error al crear el código. Intentá de nuevo.');
          }
        }
      } catch {
        setServerError('Error de red. Revisá tu conexión.');
      }
    });
  }

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Nuevo Código Promocional"
        description="Completá los datos para crear un nuevo código de descuento."
      />

      <form onSubmit={handleSubmit} className="space-y-6 max-w-2xl">
        {serverError && (
          <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{serverError}</div>
        )}

        <div className="grid grid-cols-2 gap-4">
          {/* Code */}
          <div>
            <label className="block text-sm font-medium text-slate-700">Código</label>
            <input
              name="code"
              value={form.code}
              onChange={handleChange}
              placeholder="ej. SAVE20"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-mono uppercase focus:border-blue-500 focus:outline-none"
            />
            {errors.code && <p className="mt-1 text-xs text-red-600">{errors.code}</p>}
          </div>

          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-slate-700">Nombre</label>
            <input
              name="name"
              value={form.name}
              onChange={handleChange}
              placeholder="ej. 20% de descuento primer mes"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
            {errors.name && <p className="mt-1 text-xs text-red-600">{errors.name}</p>}
          </div>

          {/* Discount type */}
          <div>
            <label className="block text-sm font-medium text-slate-700">Tipo de descuento</label>
            <select
              name="discount_type"
              value={form.discount_type}
              onChange={handleChange}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            >
              {options
                ? options.discount_types.map((dt) => (
                    <option key={dt.value} value={dt.value}>{dt.label}</option>
                  ))
                : (
                  <>
                    <option value="percent">Porcentaje (%)</option>
                    <option value="fixed_amount">Monto fijo (ARS)</option>
                  </>
                )}
            </select>
          </div>

          {/* Discount value */}
          <div>
            <label className="block text-sm font-medium text-slate-700">
              Valor {form.discount_type === 'percent' ? '(%)' : '(ARS)'}
            </label>
            <input
              name="discount_value"
              type="number"
              min="0.01"
              step="0.01"
              max={form.discount_type === 'percent' ? 100 : undefined}
              value={form.discount_value}
              onChange={handleChange}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
            {errors.discount_value && <p className="mt-1 text-xs text-red-600">{errors.discount_value}</p>}
          </div>

          {/* Duration cycles */}
          <div>
            <label className="block text-sm font-medium text-slate-700">Ciclos de duración</label>
            <input
              name="duration_cycles"
              type="number"
              min="1"
              value={form.duration_cycles}
              onChange={handleChange}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
            {errors.duration_cycles && <p className="mt-1 text-xs text-red-600">{errors.duration_cycles}</p>}
          </div>

          {/* Max redemptions */}
          <div>
            <label className="block text-sm font-medium text-slate-700">Límite de usos (global)</label>
            <input
              name="max_redemptions"
              type="number"
              min="1"
              value={form.max_redemptions}
              onChange={handleChange}
              placeholder="Sin límite"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Max per business */}
          <div>
            <label className="block text-sm font-medium text-slate-700">Límite por negocio</label>
            <input
              name="max_redemptions_per_business"
              type="number"
              min="1"
              value={form.max_redemptions_per_business}
              onChange={handleChange}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Plan selector */}
          <div className="col-span-2">
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Planes aplicables <span className="text-red-500">*</span>
            </label>

            {/* Service filter */}
            {options && options.services.length > 1 && (
              <div className="mb-2 flex gap-2">
                {options.services.map((svc) => (
                  <button
                    key={svc.value}
                    type="button"
                    onClick={() => setSelectedService(svc.value)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                      selectedService === svc.value
                        ? 'border-blue-500 bg-blue-50 text-blue-700'
                        : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    {svc.label}
                  </button>
                ))}
              </div>
            )}

            {optionsLoading ? (
              <p className="text-sm text-slate-400 py-2">Cargando planes…</p>
            ) : filteredPlans.length === 0 ? (
              <p className="text-sm text-slate-400 py-2">No hay planes disponibles.</p>
            ) : (
              <div className="rounded-md border border-slate-200 divide-y divide-slate-100">
                {filteredPlans.map((plan) => {
                  const checked = form.selected_plan_codes.includes(plan.code);
                  return (
                    <label
                      key={plan.code}
                      className={`flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-slate-50 ${
                        checked ? 'bg-blue-50' : ''
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => togglePlanCode(plan.code)}
                        className="h-4 w-4 rounded border-slate-300"
                      />
                      <span className="flex-1 text-sm text-slate-800">{plan.label}</span>
                      <span className="text-xs text-slate-400 font-mono">{plan.code}</span>
                      <span className="text-xs text-slate-500">${parseInt(plan.price, 10).toLocaleString('es-AR')}/mes</span>
                    </label>
                  );
                })}
              </div>
            )}
            {errors.applies_to_plan_codes && (
              <p className="mt-1 text-xs text-red-600">{errors.applies_to_plan_codes}</p>
            )}
          </div>

          {/* Starts / ends */}
          <div>
            <label className="block text-sm font-medium text-slate-700">Válido desde</label>
            <input
              name="starts_at"
              type="datetime-local"
              value={form.starts_at}
              onChange={handleChange}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700">Válido hasta</label>
            <input
              name="ends_at"
              type="datetime-local"
              value={form.ends_at}
              onChange={handleChange}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
            {errors.ends_at && <p className="mt-1 text-xs text-red-600">{errors.ends_at}</p>}
          </div>

          {/* Description */}
          <div className="col-span-2">
            <label className="block text-sm font-medium text-slate-700">Descripción (opcional)</label>
            <textarea
              name="description"
              value={form.description}
              onChange={handleChange}
              rows={2}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Active */}
          <div className="col-span-2 flex items-center gap-2">
            <input
              id="active"
              name="active"
              type="checkbox"
              checked={form.active}
              onChange={handleChange}
              className="h-4 w-4 rounded border-slate-300"
            />
            <label htmlFor="active" className="text-sm text-slate-700">Código activo</label>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={isPending}
            className="rounded-md bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            {isPending ? 'Guardando...' : 'Crear código'}
          </button>
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded-md border border-slate-300 px-5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancelar
          </button>
        </div>
      </form>
    </div>
  );
}

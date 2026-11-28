'use client';

import { useState } from 'react';

import { addCalendarMonths, todayDateOnly } from '@/lib/admin/complimentary-period';
import type { ComplimentaryGrantErrors, ComplimentaryGrantFields } from '@/lib/admin/complimentary-grant';
import type { AdminProvisioningUsageTierOption } from '@/lib/admin/types';

/*
 * PROD-09E — Commercial fields of a complimentary grant, extracted verbatim
 * from the "Nuevo cliente" form (same ids, labels, classes and behaviour) so
 * the add-service modal reuses them instead of duplicating them.
 */

export const inputClass =
  'mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none disabled:bg-slate-50 disabled:text-slate-400';
export const labelClass = 'block text-sm font-medium text-slate-700';
export const errorClass = 'mt-1 text-xs text-red-600';

type Key = keyof ComplimentaryGrantFields;

type FieldProps = {
  form: ComplimentaryGrantFields;
  errors: ComplimentaryGrantErrors;
  onChange: (key: Key, value: string) => void;
  /** Lets the parent focus the first invalid field. */
  registerRef?: (key: Key, el: HTMLElement | null) => void;
};

/** Nivel de uso + cupo personalizado (Turnos IA, Recepcionista; PROD-02F3). */
export function UsageTierFields({
  form, errors, onChange, registerRef, usageTiers, customAllowance,
}: FieldProps & {
  usageTiers: AdminProvisioningUsageTierOption[];
  customAllowance: { min: number; max: number } | null;
}) {
  return (
    <>
      {usageTiers.length > 0 && (
        <div className="sm:col-span-2">
          <label htmlFor="usage_tier" className={labelClass}>
            Nivel de uso
          </label>
          <select
            id="usage_tier"
            ref={(el) => registerRef?.('usage_tier', el)}
            value={form.usage_tier}
            onChange={(e) => onChange('usage_tier', e.target.value)}
            aria-invalid={Boolean(errors.usage_tier)}
            aria-describedby="usage_tier-help"
            className={inputClass}
          >
            <option value="">Seleccioná un nivel de uso</option>
            {usageTiers.map((tier) => (
              <option key={tier.code} value={tier.code}>{tier.name}</option>
            ))}
          </select>
          <p id="usage_tier-help" className="mt-1 text-xs text-slate-500">
            Conversaciones de IA incluidas por mes. El alta es bonificada: no se cobra.
          </p>
          {errors.usage_tier && <p className={errorClass}>{errors.usage_tier}</p>}
        </div>
      )}

      {customAllowance && (
        <div className="sm:col-span-2">
          <label htmlFor="custom_included_sessions" className={labelClass}>
            Cupo personalizado (conversaciones por mes)
          </label>
          <input
            id="custom_included_sessions"
            ref={(el) => registerRef?.('custom_included_sessions', el)}
            type="number"
            inputMode="numeric"
            min={customAllowance.min}
            max={customAllowance.max}
            step={1}
            value={form.custom_included_sessions}
            onChange={(e) => onChange('custom_included_sessions', e.target.value)}
            aria-invalid={Boolean(errors.custom_included_sessions)}
            aria-describedby="custom_included_sessions-help"
            className={inputClass}
          />
          <p id="custom_included_sessions-help" className="mt-1 text-xs text-slate-500">
            Cupo individual de este acuerdo. Sin excedentes: al agotarse, la IA se bloquea hasta el próximo período.
          </p>
          {errors.custom_included_sessions && (
            <p className={errorClass}>{errors.custom_included_sessions}</p>
          )}
        </div>
      )}
    </>
  );
}

type PeriodPreset = '6m' | '1y' | 'custom';

const presetClass = (active: boolean) =>
  `rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
    active ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-slate-300 text-slate-600 hover:bg-slate-50'
  }`;

/** Accesos rápidos (6 meses / 1 año / Personalizado) + inicio y fin, "YYYY-MM-DD". */
export function ComplimentaryPeriodFields({ form, errors, onChange, registerRef }: FieldProps) {
  const [preset, setPreset] = useState<PeriodPreset>('custom');

  function quickPick(kind: '6m' | '1y') {
    const start = form.complimentary_start || todayDateOnly();
    onChange('complimentary_start', start);
    onChange('complimentary_end', addCalendarMonths(start, kind === '6m' ? 6 : 12));
    setPreset(kind);
  }

  function change(key: 'complimentary_start' | 'complimentary_end', value: string) {
    onChange(key, value);
    setPreset('custom');
  }

  return (
    <>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => quickPick('6m')} className={presetClass(preset === '6m')}>
          6 meses
        </button>
        <button type="button" onClick={() => quickPick('1y')} className={presetClass(preset === '1y')}>
          1 año
        </button>
        <button type="button" onClick={() => setPreset('custom')} className={presetClass(preset === 'custom')}>
          Personalizado
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="complimentary_start" className={labelClass}>
            Inicio de la bonificación
          </label>
          <input
            id="complimentary_start"
            type="date"
            ref={(el) => registerRef?.('complimentary_start', el)}
            value={form.complimentary_start}
            onChange={(e) => change('complimentary_start', e.target.value)}
            aria-invalid={Boolean(errors.complimentary_start)}
            className={inputClass}
          />
          {errors.complimentary_start && <p className={errorClass}>{errors.complimentary_start}</p>}
        </div>
        <div>
          <label htmlFor="complimentary_end" className={labelClass}>
            Fin de la bonificación
          </label>
          <input
            id="complimentary_end"
            type="date"
            ref={(el) => registerRef?.('complimentary_end', el)}
            value={form.complimentary_end}
            onChange={(e) => change('complimentary_end', e.target.value)}
            aria-invalid={Boolean(errors.complimentary_end)}
            className={inputClass}
          />
          {errors.complimentary_end && <p className={errorClass}>{errors.complimentary_end}</p>}
        </div>
      </div>
    </>
  );
}

/** Motivo obligatorio de la bonificación. `maxLength` solo donde se pida. */
export function GrantReasonField({ form, errors, onChange, registerRef, maxLength }: FieldProps & { maxLength?: number }) {
  return (
    <div>
      <label htmlFor="grant_reason" className={labelClass}>
        Motivo de la bonificación
      </label>
      <textarea
        id="grant_reason"
        ref={(el) => registerRef?.('grant_reason', el)}
        value={form.grant_reason}
        onChange={(e) => onChange('grant_reason', e.target.value)}
        rows={3}
        maxLength={maxLength}
        aria-invalid={Boolean(errors.grant_reason)}
        className={inputClass}
      />
      {errors.grant_reason && <p className={errorClass}>{errors.grant_reason}</p>}
    </div>
  );
}

'use client';

import { useBusinessBrandingQuery } from '@/features/gestion/hooks';

import { LOGO_VARIANT_OPTIONS } from '../constants';
import type { LogoVariant } from '../types';

type LogoSelectorProps = {
  value: LogoVariant;
  onChange: (variant: LogoVariant) => void;
};

export function LogoSelector({ value, onChange }: LogoSelectorProps) {
  const brandingQuery = useBusinessBrandingQuery();
  const branding = brandingQuery.data;

  const hasHorizontal = Boolean(branding?.logo_horizontal_url);
  const hasSquare = Boolean(branding?.logo_square_url);

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-slate-700">Logo en el cartel</label>

      <div className="space-y-1.5">
        {LOGO_VARIANT_OPTIONS.map((opt) => {
          const isSelected = value === opt.value;

          const unavailable =
            (opt.value === 'horizontal' && !hasHorizontal) ||
            (opt.value === 'square' && !hasSquare);

          return (
            <label
              key={opt.value}
              className={[
                'flex items-center gap-2 rounded-lg border px-3 py-2 cursor-pointer transition-colors',
                isSelected
                  ? 'border-slate-900 bg-slate-50'
                  : 'border-slate-200 bg-white hover:border-slate-300',
                unavailable ? 'opacity-60' : '',
              ].join(' ')}
            >
              <input
                type="radio"
                name="logo_variant"
                value={opt.value}
                checked={isSelected}
                onChange={() => onChange(opt.value)}
                className="accent-slate-900"
              />
              <span className="text-sm text-slate-800">{opt.label}</span>
              {unavailable && (
                <span className="ml-auto text-xs text-amber-600">Sin imagen cargada</span>
              )}
            </label>
          );
        })}
      </div>

      {value === 'default' && !hasHorizontal && !hasSquare && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          No hay logos cargados todavía. El PDF se generará igual sin logo.
        </p>
      )}

      {!hasHorizontal && !hasSquare && value !== 'default' && (
        <p className="text-xs text-slate-400">
          Subí logos en{' '}
          <a href="/app/config/branding" className="underline hover:text-slate-700">
            Configuración → Marca
          </a>{' '}
          para habilitarlos.
        </p>
      )}
    </div>
  );
}

'use client';

import { PRINTABLE_CARD_SIZES } from '../constants';
import type { PrintableCardSize } from '../types';

type CardSizeSelectorProps = {
  value: PrintableCardSize;
  onChange: (size: PrintableCardSize) => void;
};

export function CardSizeSelector({ value, onChange }: CardSizeSelectorProps) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-slate-700">Medida del cartel</label>
      <div className="grid grid-cols-3 gap-2">
        {PRINTABLE_CARD_SIZES.map((size) => {
          const isSelected = size.code === value.code;
          return (
            <button
              key={size.code}
              type="button"
              onClick={() => onChange(size)}
              className={[
                'rounded-lg border px-2 py-2 text-center text-xs transition-colors',
                isSelected
                  ? 'border-slate-900 bg-slate-900 text-white font-semibold'
                  : 'border-slate-200 bg-white text-slate-700 hover:border-slate-400',
              ].join(' ')}
            >
              {size.label}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-slate-400">
        El PDF A4 incluirá la cantidad de carteles que entren en la hoja con las medidas elegidas.
      </p>
    </div>
  );
}

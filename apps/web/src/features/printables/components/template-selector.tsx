'use client';

import { PRINTABLE_TEMPLATES } from '../constants';
import type { PrintableTemplateCode, PrintableType } from '../types';

interface TemplateSelectorProps {
  type: PrintableType;
  value: PrintableTemplateCode;
  onChange: (code: PrintableTemplateCode) => void;
}

export function TemplateSelector({ type, value, onChange }: TemplateSelectorProps) {
  const options = PRINTABLE_TEMPLATES.filter((t) => t.type === type);

  // For product there is only one template — no need to show a selector
  if (options.length <= 1) return null;

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-slate-700">Estilo de cartel</p>
      <div className="flex flex-wrap gap-2">
        {options.map((tpl) => (
          <button
            key={tpl.code}
            type="button"
            onClick={() => onChange(tpl.code)}
            className={[
              'rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors',
              value === tpl.code
                ? 'border-slate-900 bg-slate-900 text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-800',
            ].join(' ')}
          >
            {tpl.label}
          </button>
        ))}
      </div>
    </div>
  );
}

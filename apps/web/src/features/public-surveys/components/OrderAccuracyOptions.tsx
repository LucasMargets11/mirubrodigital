'use client';

import type { OrderAccuracyValue } from '../types';

interface Option {
    value: OrderAccuracyValue;
    label: string;
}

const OPTIONS: Option[] = [
    { value: 'todo_correcto', label: 'Sí, todo correcto' },
    { value: 'error_menor', label: 'Hubo un error menor' },
    { value: 'falto_algo', label: 'Faltó algo' },
    { value: 'producto_incorrecto', label: 'Recibí algo incorrecto' },
];

interface Props {
    value: OrderAccuracyValue | undefined;
    onChange: (value: OrderAccuracyValue) => void;
}

export function OrderAccuracyOptions({ value, onChange }: Props) {
    return (
        <div className="flex flex-col gap-2.5" role="radiogroup" aria-label="Pedido correcto">
            {OPTIONS.map((opt) => {
                const selected = value === opt.value;
                return (
                    <button
                        key={opt.value}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => onChange(opt.value)}
                        className={[
                            'flex w-full items-center justify-between rounded-2xl border-2 px-4 py-4 text-left transition-all active:scale-[0.98]',
                            'min-h-[64px]',
                            selected
                                ? 'border-[#FFC72C] bg-[#FFF7E0]'
                                : 'border-slate-200 bg-white hover:border-slate-300',
                        ].join(' ')}
                    >
                        <span className="flex-1 text-base font-semibold text-slate-900">
                            {opt.label}
                        </span>
                        {selected && (
                            <span
                                aria-hidden="true"
                                className="ml-3 flex h-6 w-6 items-center justify-center rounded-full bg-[#FFC72C] text-[#27251F]"
                            >
                                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                </svg>
                            </span>
                        )}
                    </button>
                );
            })}
        </div>
    );
}

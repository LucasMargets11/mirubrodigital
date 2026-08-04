'use client';

import type { StarsValue } from '../types';

const LABELS: Record<StarsValue, string> = {
    1: 'Malo',
    2: 'Regular',
    3: 'Bueno',
    4: 'Muy bueno',
    5: 'Excelente',
};

interface Props {
    value: StarsValue | undefined;
    onChange: (value: StarsValue) => void;
}

export function StarRating({ value, onChange }: Props) {
    return (
        <div className="flex flex-col items-center gap-3">
            <div
                className="flex items-center justify-center gap-1.5"
                role="radiogroup"
                aria-label="Calificación con estrellas"
            >
                {([1, 2, 3, 4, 5] as StarsValue[]).map((star) => {
                    const filled = value !== undefined && star <= value;
                    const selected = value === star;
                    return (
                        <button
                            key={star}
                            type="button"
                            role="radio"
                            aria-checked={selected}
                            aria-label={`${star} estrella${star > 1 ? 's' : ''} — ${LABELS[star]}`}
                            onClick={() => onChange(star)}
                            className="rounded-full p-1.5 transition-transform active:scale-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#DA291C] focus-visible:ring-offset-2"
                        >
                            <svg
                                xmlns="http://www.w3.org/2000/svg"
                                className={[
                                    'h-12 w-12 transition-colors duration-150',
                                    filled ? 'text-[#FFC72C]' : 'text-slate-300',
                                ].join(' ')}
                                fill={filled ? 'currentColor' : 'none'}
                                viewBox="0 0 24 24"
                                stroke="currentColor"
                                strokeWidth={filled ? 0 : 1.5}
                                aria-hidden="true"
                            >
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
                                />
                            </svg>
                        </button>
                    );
                })}
            </div>
            <p
                className="h-6 text-base font-semibold text-slate-700"
                aria-live="polite"
            >
                {value !== undefined ? LABELS[value] : ''}
            </p>
        </div>
    );
}

'use client';

import type { EmojiRatingValue } from '../types';

interface RatingOption {
    value: EmojiRatingValue;
    emoji: string;
    label: string;
}

const OPTIONS: RatingOption[] = [
    { value: 1, emoji: '😞', label: 'Malo' },
    { value: 2, emoji: '😐', label: 'Regular' },
    { value: 3, emoji: '🙂', label: 'Bueno' },
    { value: 4, emoji: '😄', label: 'Muy bueno' },
    { value: 5, emoji: '🤩', label: 'Excelente' },
];

interface Props {
    value: EmojiRatingValue | undefined;
    onChange: (value: EmojiRatingValue) => void;
}

export function RatingOptions({ value, onChange }: Props) {
    return (
        <div className="flex flex-col gap-2.5" role="radiogroup" aria-label="Calificación">
            {OPTIONS.map((opt) => {
                const selected = value === opt.value;
                return (
                    <button
                        key={opt.value}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        aria-label={`${opt.label} (${opt.value} de 5)`}
                        onClick={() => onChange(opt.value)}
                        className={[
                            'flex w-full items-center gap-4 rounded-2xl border-2 px-4 py-4 text-left transition-all active:scale-[0.98]',
                            'min-h-[64px]',
                            selected
                                ? 'border-[#FFC72C] bg-[#FFF7E0]'
                                : 'border-slate-200 bg-white hover:border-slate-300',
                        ].join(' ')}
                    >
                        <span
                            className="text-3xl leading-none"
                            aria-hidden="true"
                        >
                            {opt.emoji}
                        </span>
                        <span className="flex-1 text-base font-semibold text-slate-900">
                            {opt.label}
                        </span>
                        {selected && (
                            <span
                                aria-hidden="true"
                                className="flex h-6 w-6 items-center justify-center rounded-full bg-[#FFC72C] text-[#27251F]"
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

'use client';

import { useEffect, useRef } from 'react';
import type {
    EmojiRatingValue,
    OrderAccuracyValue,
    StarsValue,
    SurveyAnswerValue,
    SurveyQuestion,
} from '../types';
import { RatingOptions } from './RatingOptions';
import { StarRating } from './StarRating';
import { OrderAccuracyOptions } from './OrderAccuracyOptions';

interface Props {
    question: SurveyQuestion;
    value: SurveyAnswerValue | undefined;
    onChange: (value: SurveyAnswerValue) => void;
    /** Índice 0-based de la pregunta actual dentro de la categoría. */
    questionIndex?: number;
    /** Total de preguntas de la categoría. */
    questionTotal?: number;
}

export function SurveyQuestionScreen({
    question,
    value,
    onChange,
    questionIndex,
    questionTotal,
}: Props) {
    /**
     * Al montar (el padre usa `key={question.id}` para forzar remount en
     * cada pregunta), reposicionamos el viewport sobre el contador
     * "Pregunta X de Y" / título para que en mobile siempre se vea bien.
     */
    const headerRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        const raf = window.requestAnimationFrame(() => {
            headerRef.current?.scrollIntoView({
                behavior: 'smooth',
                block: 'start',
            });
        });
        return () => window.cancelAnimationFrame(raf);
    }, []);

    const showCounter =
        typeof questionIndex === 'number' &&
        typeof questionTotal === 'number' &&
        questionTotal > 0;

    return (
        <div className="flex flex-col gap-6">
            <div ref={headerRef} className="space-y-1.5">
                {showCounter && (
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                        Pregunta {questionIndex + 1} de {questionTotal}
                    </p>
                )}
                <h2 className="text-[22px] font-bold leading-tight text-black break-words">
                    {question.question}
                </h2>
                {question.helper && (
                    <p className="text-[13px] leading-snug text-slate-500">
                        {question.helper}
                    </p>
                )}
            </div>

            <div className="w-full">
                {question.type === 'emoji-rating' && (
                    <RatingOptions
                        value={value as EmojiRatingValue | undefined}
                        onChange={(v) => onChange(v)}
                    />
                )}
                {question.type === 'order-accuracy' && (
                    <OrderAccuracyOptions
                        value={value as OrderAccuracyValue | undefined}
                        onChange={(v) => onChange(v)}
                    />
                )}
                {question.type === 'stars' && (
                    <div className="py-2">
                        <StarRating
                            value={value as StarsValue | undefined}
                            onChange={(v) => onChange(v)}
                        />
                    </div>
                )}
            </div>
        </div>
    );
}

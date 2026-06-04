'use client';

import { useMemo, useState } from 'react';

import { mcdonaldsSurvey } from './data/mcdonaldsSurvey';
import type {
    OrderAccuracyValue,
    SurveyAnswerValue,
    SurveyAnswers,
    SurveyCategory,
    SurveyQuestion,
    SurveySubmission,
} from './types';
import { SurveyShell } from './components/SurveyShell';
import { SurveyQuestionScreen } from './components/SurveyQuestionScreen';
import { CategorySelectionScreen } from './components/CategorySelectionScreen';

/* ── Steps del wizard ─────────────────────────────────────────────────────
 *
 *  intro → category → question → comment → thanks
 *
 *  Plana, sin useReducer ni librerías de state machine, como pide el MVP.
 */
type Step = 'intro' | 'category' | 'question' | 'comment' | 'thanks';

const SURVEY = mcdonaldsSurvey;
/**
 * Pasos visibles en la barra de progreso:
 *   category(1) → question 1..5 (2..6) → comment(7).
 */
const QUESTIONS_PER_CATEGORY = 5;
const TOTAL_PROGRESS_STEPS = 2 + QUESTIONS_PER_CATEGORY; // 7

/** Logo del header. Asset local en `apps/web/public/brands/mcdonalds/`. */
const BRAND_LOGO_SRC = '/brands/mcdonalds/Mlogopng.png';
const BRAND_LOGO_ALT = "McDonald's Recoleta";

/** Score numérico (1..5) usado para calcular si el resultado es "positivo". */
function scoreFor(
    question: SurveyQuestion,
    answer: SurveyAnswerValue | undefined,
): number | null {
    if (answer === undefined) return null;
    if (question.type === 'emoji-rating' || question.type === 'stars') {
        return typeof answer === 'number' ? answer : null;
    }
    // order-accuracy
    switch (answer as OrderAccuracyValue) {
        case 'todo_correcto':
            return 5;
        case 'error_menor':
            return 3;
        case 'falto_algo':
            return 2;
        case 'producto_incorrecto':
            return 1;
        default:
            return null;
    }
}

/**
 * Evalúa si la categoría completa cuenta como "positiva".
 * - Promedio de las respuestas ≥ 4 → positiva.
 * - Si alguna respuesta `order-accuracy` es `producto_incorrecto` o
 *   `falto_algo`, fuerza variante de mejora aunque el promedio sea alto.
 */
function isCategoryPositive(
    questions: SurveyQuestion[],
    answers: SurveyAnswers,
): boolean {
    if (questions.length === 0) return false;

    let sum = 0;
    let count = 0;
    for (const q of questions) {
        const ans = answers[q.id];
        if (q.type === 'order-accuracy') {
            const v = ans as OrderAccuracyValue | undefined;
            if (v === 'producto_incorrecto' || v === 'falto_algo') {
                return false;
            }
        }
        const s = scoreFor(q, ans);
        if (s !== null) {
            sum += s;
            count += 1;
        }
    }
    if (count === 0) return false;
    return sum / count >= 4;
}

export function McDonaldsExperienceSurvey() {
    const [step, setStep] = useState<Step>('intro');
    const [selectedCategory, setSelectedCategory] =
        useState<SurveyCategory | null>(null);
    const [activeQuestionIndex, setActiveQuestionIndex] = useState(0);
    const [answers, setAnswers] = useState<SurveyAnswers>({});
    const [comment, setComment] = useState('');

    /* ── Derivados ───────────────────────────────────────────────────────── */
    /** Lista ordenada de preguntas de la categoría activa. */
    const categoryQuestions = useMemo<SurveyQuestion[]>(() => {
        if (!selectedCategory) return [];
        const out: SurveyQuestion[] = [];
        for (const qid of selectedCategory.questionIds) {
            const q = SURVEY.questions.find((x) => x.id === qid);
            if (q) out.push(q);
        }
        return out;
    }, [selectedCategory]);

    const currentQuestion = categoryQuestions[activeQuestionIndex] ?? null;
    const currentAnswer = currentQuestion ? answers[currentQuestion.id] : undefined;
    const totalCategoryQuestions = categoryQuestions.length;

    const progress = useMemo<{ current: number | null; total: number | null }>(() => {
        switch (step) {
            case 'category':
                return { current: 1, total: TOTAL_PROGRESS_STEPS };
            case 'question':
                // 2..6 según activeQuestionIndex (0..4)
                return {
                    current: 2 + activeQuestionIndex,
                    total: TOTAL_PROGRESS_STEPS,
                };
            case 'comment':
                return { current: TOTAL_PROGRESS_STEPS, total: TOTAL_PROGRESS_STEPS };
            default:
                return { current: null, total: null };
        }
    }, [step, activeQuestionIndex]);

    /* ── Handlers ────────────────────────────────────────────────────────── */
    function handleStart() {
        setStep('category');
    }

    function handleCategorySelect(category: SurveyCategory) {
        // Cambio de categoría: limpiamos respuestas previas y reseteamos índice.
        setSelectedCategory(category);
        setActiveQuestionIndex(0);
        setAnswers({});
        setComment('');
        setStep('question');
    }

    function handleAnswer(value: SurveyAnswerValue) {
        if (!currentQuestion) return;
        setAnswers((prev) => ({ ...prev, [currentQuestion.id]: value }));
        // Si quedan preguntas, avanzar a la siguiente; si no, ir al comentario.
        if (activeQuestionIndex < totalCategoryQuestions - 1) {
            setActiveQuestionIndex((i) => i + 1);
        } else {
            setStep('comment');
        }
    }

    function handleBack() {
        if (step === 'category') {
            setStep('intro');
            return;
        }
        if (step === 'question') {
            if (activeQuestionIndex > 0) {
                setActiveQuestionIndex((i) => i - 1);
            } else {
                setStep('category');
            }
            return;
        }
        if (step === 'comment') {
            // Volver a la última pregunta de la categoría.
            setActiveQuestionIndex(Math.max(totalCategoryQuestions - 1, 0));
            setStep('question');
        }
    }

    function handleSubmit() {
        if (!selectedCategory) return;
        const submission: SurveySubmission = {
            surveyId: 'mcdonalds-recoleta-demo',
            selectedCategoryId: selectedCategory.id,
            selectedCategoryLabel: selectedCategory.label,
            answers,
            comment: comment.trim(),
            submittedAt: new Date().toISOString(),
        };
        // Mock submit: en el MVP demo solo logueamos el payload.
        // eslint-disable-next-line no-console
        console.log('[McDonaldsExperienceSurvey] submission', submission);
        setStep('thanks');
    }

    function handleFinish() {
        // "Finalizar" en la variante de mejora reinicia el demo a la intro.
        setSelectedCategory(null);
        setActiveQuestionIndex(0);
        setAnswers({});
        setComment('');
        setStep('intro');
    }

    /* ── Render por step ─────────────────────────────────────────────────── */

    if (step === 'intro') {
        return (
            <SurveyShell
                displayName={SURVEY.displayName}
                brandLogoSrc={BRAND_LOGO_SRC}
                brandLogoAlt={BRAND_LOGO_ALT}
            >
                {/*
                 * Hero mobile: empujamos el bloque principal hacia ~38–42%
                 * del alto visible con padding superior basado en `svh`
                 * (más estable que `vh` en mobile con barra de URL).
                 * `mt-auto` en el caption final equilibra la mitad inferior.
                 */}
                <div className="flex min-h-[60svh] flex-col items-start gap-7 pt-[16svh] sm:pt-[18svh]">
                    <div className="space-y-3">
                        <h1 className="text-[26px] font-bold leading-tight text-black">
                            {SURVEY.title}
                        </h1>
                        <p className="text-[14px] leading-relaxed text-slate-600">
                            {SURVEY.subtitle}
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={handleStart}
                        className="w-full rounded-2xl bg-[#FFC72C] px-6 py-4 text-base font-bold text-[#27251F] transition-colors hover:bg-[#F2B800] active:bg-[#EFB500] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#DA291C] focus-visible:ring-offset-2"
                    >
                        Comenzar encuesta
                    </button>

                    <p className="w-full text-center text-[11px] text-slate-400">
                        Toma menos de un minuto.
                    </p>
                </div>
            </SurveyShell>
        );
    }

    if (step === 'category') {
        return (
            <SurveyShell
                displayName={SURVEY.displayName}
                brandLogoSrc={BRAND_LOGO_SRC}
                brandLogoAlt={BRAND_LOGO_ALT}
                currentStep={progress.current}
                totalSteps={progress.total}
                onBack={handleBack}
            >
                <CategorySelectionScreen
                    categories={SURVEY.categories}
                    onSelect={handleCategorySelect}
                />
            </SurveyShell>
        );
    }

    if (step === 'question' && currentQuestion) {
        return (
            <SurveyShell
                displayName={SURVEY.displayName}
                brandLogoSrc={BRAND_LOGO_SRC}
                brandLogoAlt={BRAND_LOGO_ALT}
                currentStep={progress.current}
                totalSteps={progress.total}
                onBack={handleBack}
                eyebrow={selectedCategory?.label ?? null}
            >
                {/* `key` fuerza remount por pregunta → dispara scroll/focus. */}
                <SurveyQuestionScreen
                    key={currentQuestion.id}
                    question={currentQuestion}
                    value={currentAnswer}
                    onChange={handleAnswer}
                    questionIndex={activeQuestionIndex}
                    questionTotal={totalCategoryQuestions}
                />
            </SurveyShell>
        );
    }

    if (step === 'comment') {
        return (
            <SurveyShell
                displayName={SURVEY.displayName}
                brandLogoSrc={BRAND_LOGO_SRC}
                brandLogoAlt={BRAND_LOGO_ALT}
                currentStep={progress.current}
                totalSteps={progress.total}
                onBack={handleBack}
                eyebrow={selectedCategory?.label ?? null}
            >
                <div className="flex flex-col gap-5">
                    <div className="space-y-1.5">
                        <h2 className="text-[22px] font-bold leading-tight text-black">
                            ¿Querés contarnos algo más?
                        </h2>
                        <p className="text-[13px] leading-snug text-slate-500">
                            Tu comentario es opcional, pero nos ayuda muchísimo.
                        </p>
                    </div>

                    <label htmlFor="survey-comment" className="sr-only">
                        Tu comentario
                    </label>
                    <textarea
                        id="survey-comment"
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        rows={6}
                        maxLength={2000}
                        placeholder="Escribí tu comentario..."
                        className="w-full resize-none rounded-2xl border-2 border-black bg-white px-4 py-3 text-[15px] leading-relaxed text-slate-900 placeholder:text-slate-400 focus:border-[#FFC72C] focus:outline-none"
                    />

                    <button
                        type="button"
                        onClick={handleSubmit}
                        className="w-full rounded-2xl bg-[#FFC72C] px-6 py-4 text-base font-bold text-[#27251F] transition-colors hover:bg-[#F2B800] active:bg-[#EFB500] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#DA291C] focus-visible:ring-offset-2"
                    >
                        Enviar opinión
                    </button>
                </div>
            </SurveyShell>
        );
    }

    /* ── Thanks ─────────────────────────────────────────────────────────── */
    const positive = isCategoryPositive(categoryQuestions, answers);

    return (
        <SurveyShell
            displayName={SURVEY.displayName}
            brandLogoSrc={BRAND_LOGO_SRC}
            brandLogoAlt={BRAND_LOGO_ALT}
        >
            {positive ? (
                <div className="flex flex-col items-center gap-5 py-4 text-center">
                    <div
                        aria-hidden="true"
                        className="flex h-16 w-16 items-center justify-center rounded-full bg-[#FFC72C] text-3xl"
                    >
                        🎉
                    </div>
                    <div className="space-y-2">
                        <h2 className="text-[24px] font-bold leading-tight text-black">
                            ¡Gracias por tu opinión!
                        </h2>
                        <p className="text-[14px] leading-relaxed text-slate-600">
                            Nos alegra saber que tu experiencia fue positiva.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={handleFinish}
                        className="w-full rounded-2xl bg-[#FFC72C] px-6 py-4 text-base font-bold text-[#27251F] transition-colors hover:bg-[#F2B800] active:bg-[#EFB500] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#DA291C] focus-visible:ring-offset-2"
                    >
                        Finalizar
                    </button>
                </div>
            ) : (
                <div className="flex flex-col items-center gap-5 py-4 text-center">
                    <div
                        aria-hidden="true"
                        className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-100 text-3xl"
                    >
                        🙏
                    </div>
                    <div className="space-y-2">
                        <h2 className="text-[24px] font-bold leading-tight text-black">
                            Gracias por contarnos tu experiencia
                        </h2>
                        <p className="text-[14px] leading-relaxed text-slate-600">
                            Tu comentario será enviado al equipo de la sucursal
                            para seguir mejorando.
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={handleFinish}
                        className="w-full rounded-2xl border-2 border-black bg-white px-6 py-4 text-base font-bold text-black transition-colors hover:bg-[#FFF7E0] active:bg-[#FFE9A8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#DA291C] focus-visible:ring-offset-2"
                    >
                        Finalizar
                    </button>
                </div>
            )}
        </SurveyShell>
    );
}

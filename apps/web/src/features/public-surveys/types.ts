/* ── Public Surveys — Tipos base (MVP demo frontend-only) ─────────────────
 *
 * Tipos compartidos por el MVP demo de encuesta de experiencia.
 * No se conectan al backend ni al módulo de reviews.
 */

export type SurveyQuestionType = 'emoji-rating' | 'stars' | 'order-accuracy';

export type EmojiRatingValue = 1 | 2 | 3 | 4 | 5;
export type StarsValue = 1 | 2 | 3 | 4 | 5;

export type OrderAccuracyValue =
    | 'todo_correcto'
    | 'error_menor'
    | 'falto_algo'
    | 'producto_incorrecto';

export type SurveyAnswerValue = EmojiRatingValue | StarsValue | OrderAccuracyValue;

/** Mapa de respuestas indexado por `SurveyQuestion.id`. */
export type SurveyAnswers = Record<string, SurveyAnswerValue>;

export interface SurveyQuestion {
    /** Clave única usada como índice en `SurveyAnswers`. */
    id: string;
    type: SurveyQuestionType;
    /** Texto principal de la pregunta. */
    question: string;
    /** Subtítulo / ayuda opcional. */
    helper?: string;
}

/* ── Categorías de la encuesta ───────────────────────────────────────────
 *
 * El MVP demo arranca con un único set de categorías (McDonald's), pero
 * mantenemos los IDs como string-union para poder ampliarlos sin perder
 * autocomplete.
 */
export type SurveyCategoryId =
    | 'atencion'
    | 'rapidez'
    | 'limpieza'
    | 'calidad'
    | 'pedido_correcto'
    | 'experiencia_general';

/** Nombre de un ícono de `lucide-react`. Se mapea a un componente en el render. */
export type SurveyCategoryIconName =
    | 'Headphones'
    | 'Timer'
    | 'Sparkles'
    | 'Utensils'
    | 'ClipboardCheck'
    | 'Star';

export interface SurveyCategory {
    id: SurveyCategoryId;
    label: string;
    /**
     * IDs ordenados de las preguntas asociadas a esta categoría.
     * Cada ID debe existir en `SurveyConfig.questions`.
     * El MVP usa 5 preguntas por categoría.
     */
    questionIds: string[];
    description?: string;
    iconName?: SurveyCategoryIconName;
}

export interface SurveyConfig {
    brandName: string;
    branchName: string;
    /** Texto a mostrar como nombre de sucursal en el header (ej: "McDonald's Recoleta"). */
    displayName: string;
    title: string;
    subtitle: string;
    questions: SurveyQuestion[];
    categories: SurveyCategory[];
}

/** Payload que se loguea al "enviar" la encuesta demo. */
export interface SurveySubmission {
    surveyId: string;
    selectedCategoryId: SurveyCategoryId;
    selectedCategoryLabel: string;
    answers: SurveyAnswers;
    comment: string;
    submittedAt: string;
}

import type { SurveyConfig } from '../types';

/* ── McDonald's Recoleta — Configuración del MVP demo ─────────────────────
 *
 * Cada categoría tiene 5 preguntas. Los IDs de pregunta siguen la
 * convención `{categoryId}_{n}` (1..5) y deben existir en `questions`.
 */
export const mcdonaldsSurvey: SurveyConfig = {
    brandName: "McDonald's",
    branchName: 'Recoleta',
    displayName: "McDonald's Recoleta",
    title: 'Queremos conocer tu experiencia',
    subtitle:
        'Tu opinión nos ayuda a mejorar la atención, la rapidez y la calidad del servicio.',
    questions: [
        // ── Atención ───────────────────────────────────────────────────
        { id: 'atencion_1', type: 'emoji-rating', question: '¿Cómo fue la atención del equipo?' },
        { id: 'atencion_2', type: 'emoji-rating', question: '¿El personal te atendió con amabilidad?' },
        { id: 'atencion_3', type: 'emoji-rating', question: '¿Te ayudaron o resolvieron tus dudas cuando lo necesitaste?' },
        { id: 'atencion_4', type: 'emoji-rating', question: '¿La comunicación del equipo fue clara?' },
        { id: 'atencion_5', type: 'emoji-rating', question: '¿Cómo evaluarías el trato recibido durante tu visita?' },

        // ── Rapidez ────────────────────────────────────────────────────
        { id: 'rapidez_1', type: 'emoji-rating', question: '¿Cómo fue el tiempo de espera?' },
        { id: 'rapidez_2', type: 'emoji-rating', question: '¿Qué tan rápido prepararon tu pedido?' },
        { id: 'rapidez_3', type: 'emoji-rating', question: '¿La entrega de tu pedido fue ágil?' },
        { id: 'rapidez_4', type: 'emoji-rating', question: '¿Sentiste que la fila avanzó de forma ordenada?' },
        { id: 'rapidez_5', type: 'emoji-rating', question: '¿Cómo evaluarías la rapidez general del servicio?' },

        // ── Limpieza ───────────────────────────────────────────────────
        { id: 'limpieza_1', type: 'emoji-rating', question: '¿Cómo encontraste la limpieza del local?' },
        { id: 'limpieza_2', type: 'emoji-rating', question: '¿Cómo estaban las mesas y espacios comunes?' },
        { id: 'limpieza_3', type: 'emoji-rating', question: '¿Cómo viste el estado de los baños?' },
        { id: 'limpieza_4', type: 'emoji-rating', question: '¿Los cestos, bandejas y sectores de uso común estaban cuidados?' },
        { id: 'limpieza_5', type: 'emoji-rating', question: '¿Qué tan limpio y cuidado te pareció el ambiente del local?' },

        // ── Calidad del pedido ─────────────────────────────────────────
        { id: 'calidad_1', type: 'emoji-rating', question: '¿Cómo estaba la calidad de tu pedido?' },
        { id: 'calidad_2', type: 'emoji-rating', question: '¿La comida estaba fresca y bien preparada?' },
        { id: 'calidad_3', type: 'emoji-rating', question: '¿La temperatura de la comida y/o bebida fue adecuada?' },
        { id: 'calidad_4', type: 'emoji-rating', question: '¿El sabor fue el esperado?' },
        { id: 'calidad_5', type: 'emoji-rating', question: '¿Cómo calificarías la presentación del pedido?' },

        // ── Pedido correcto ────────────────────────────────────────────
        { id: 'pedido_correcto_1', type: 'order-accuracy', question: '¿Recibiste exactamente lo que pediste?' },
        { id: 'pedido_correcto_2', type: 'order-accuracy', question: '¿Tu pedido llegó completo?' },
        { id: 'pedido_correcto_3', type: 'order-accuracy', question: '¿Las bebidas, salsas y acompañamientos estaban correctos?' },
        { id: 'pedido_correcto_4', type: 'order-accuracy', question: '¿Se respetaron las modificaciones o aclaraciones de tu pedido?' },
        { id: 'pedido_correcto_5', type: 'emoji-rating', question: '¿Cómo evaluarías la precisión general del pedido?' },

        // ── Experiencia general ────────────────────────────────────────
        { id: 'experiencia_general_1', type: 'stars', question: '¿Cómo fue tu experiencia general hoy?' },
        { id: 'experiencia_general_2', type: 'stars', question: '¿Qué tan satisfecho/a quedaste con tu visita?' },
        { id: 'experiencia_general_3', type: 'stars', question: '¿Volverías a visitar esta sucursal?' },
        { id: 'experiencia_general_4', type: 'stars', question: '¿Recomendarías esta sucursal?' },
        { id: 'experiencia_general_5', type: 'stars', question: '¿Cómo calificarías la experiencia completa?' },
    ],
    categories: [
        {
            id: 'atencion',
            label: 'Atención',
            iconName: 'Headphones',
            questionIds: ['atencion_1', 'atencion_2', 'atencion_3', 'atencion_4', 'atencion_5'],
        },
        {
            id: 'rapidez',
            label: 'Rapidez',
            iconName: 'Timer',
            questionIds: ['rapidez_1', 'rapidez_2', 'rapidez_3', 'rapidez_4', 'rapidez_5'],
        },
        {
            id: 'limpieza',
            label: 'Limpieza',
            iconName: 'Sparkles',
            questionIds: ['limpieza_1', 'limpieza_2', 'limpieza_3', 'limpieza_4', 'limpieza_5'],
        },
        {
            id: 'calidad',
            label: 'Calidad del pedido',
            iconName: 'Utensils',
            questionIds: ['calidad_1', 'calidad_2', 'calidad_3', 'calidad_4', 'calidad_5'],
        },
        {
            id: 'pedido_correcto',
            label: 'Pedido correcto',
            iconName: 'ClipboardCheck',
            questionIds: [
                'pedido_correcto_1',
                'pedido_correcto_2',
                'pedido_correcto_3',
                'pedido_correcto_4',
                'pedido_correcto_5',
            ],
        },
        {
            id: 'experiencia_general',
            label: 'Experiencia general',
            iconName: 'Star',
            questionIds: [
                'experiencia_general_1',
                'experiencia_general_2',
                'experiencia_general_3',
                'experiencia_general_4',
                'experiencia_general_5',
            ],
        },
    ],
};

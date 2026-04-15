/* ── QR de Reseñas — Product definition ────────────────────── */
/* Central source of truth for all copy, benefits, plan features,
   pricing tiers and product messaging used across /app/resenas
   and marketing pages. */

export const PRODUCT = {
    name: 'QR de Reseñas',
    tagline: 'Más reseñas en Google, menos quejas públicas.',
    description:
        'Un QR que tus clientes escanean para dejar su opinión. ' +
        'Las positivas van a Google. Las negativas te llegan como feedback privado.',
} as const;

/** Dominant CTA — used consistently across all surfaces */
export const CTA_PRIMARY = {
    label: 'Compartir mi QR',
    href: '/app/resenas/qr',
} as const;

/** Upgrade CTA — used in post-trial banners, gating cards, config.
 *  For NON-active users the link goes to the pricing page.
 *  For ACTIVE users the UpgradeToProButton component calls the API directly. */
export const CTA_UPGRADE_PRO = {
    label: 'Ver planes Pro',
    href: '/pricing?service=qr_reviews',
} as const;

/** In-place upgrade label for active businesses */
export const CTA_UPGRADE_PRO_INPLACE = {
    label: 'Actualizar a Pro',
    loadingLabel: 'Iniciando pago…',
} as const;

/** Downgrade label for active Pro businesses */
export const CTA_DOWNGRADE_TO_BASE = {
    label: 'Volver a Reseñas Base',
    loadingLabel: 'Procesando…',
    confirmTitle: 'Volver a Reseñas Base',
    confirmMessage:
        'Al volver a Reseñas Base perderás el acceso al filtro inteligente, ' +
        'feedback privado y analytics avanzadas. Tus datos se conservan.',
    confirmButton: 'Confirmar downgrade',
    cancelButton: 'Cancelar',
} as const;

export const PRODUCT_BENEFITS = [
    'Aumentá tus reseñas en Google',
    'Convertí más clientes en recomendaciones',
    'Detectá problemas antes de que se publiquen',
] as const;

/** Three-step flow explanation — reusable in app and marketing */
export const PRODUCT_FLOW_STEPS = [
    {
        title: 'Compartís tu QR',
        description: 'Imprimilo o compartí el link. Tu cliente lo escanea desde el celular.',
    },
    {
        title: 'El cliente deja su opinión',
        description: 'Elige una calificación y opcionalmente deja un comentario.',
    },
    {
        title: 'Se filtra automáticamente',
        description: 'Las positivas van a Google. Las negativas quedan como feedback privado.',
    },
] as const;

/* ── Smart-filter differentiator ───────────────────────────── */

export const SMART_FILTER = {
    headline: 'No todas las reseñas van a Google',
    description:
        'Tu QR tiene un filtro inteligente: las opiniones altas se publican en Google y las bajas quedan como feedback privado. ' +
        'Así protegés tu reputación y mejorás con la crítica real.',
    bullets: [
        { label: 'Por encima del umbral', result: 'Se derivan a Google automáticamente' },
        { label: 'Por debajo del umbral', result: 'Quedan como feedback interno para vos' },
    ],
} as const;

/* ── Plans — PricingCardData format (reuses ProductPricing) ── */

import type { PricingCardData } from '@/components/marketing/product-landing/product-pricing';
import { REVIEWS_BASE, REVIEWS_PRO, formatPrice } from '@/lib/pricing';

export const REVIEW_PRICING_CARDS: PricingCardData[] = [
    {
        name: REVIEWS_BASE.name,
        tagline: 'Generá reseñas en Google de forma simple.',
        price: formatPrice(REVIEWS_BASE.priceMonthly),
        period: '/mes',
        highlights: [
            'QR listo para compartir',
            'Recepción de reseñas',
            'Redirección directa a Google',
        ],
        ctaHref: '/entrar',
        ctaLabel: 'Activar Reseñas Base',
    },
    {
        name: REVIEWS_PRO.name,
        tagline: 'Elegí qué llega a Google y qué queda como feedback privado.',
        price: formatPrice(REVIEWS_PRO.priceMonthly),
        period: '/mes',
        highlights: [
            'Todo lo de Base',
            'Filtro inteligente por calificación',
            'Feedback privado automático',
            'Gestión de estados',
            'Analytics avanzadas',
        ],
        ctaHref: '/entrar',
        ctaLabel: 'Activar Reseñas Pro',
        featured: true,
    },
];

/** Differentiator vs Carta Online — avoid product confusion */
export const PRODUCT_DIFFERENTIATOR = {
    title: 'QR de Reseñas ≠ Carta Online',
    items: [
        { label: 'QR de Reseñas', description: 'Te ayuda a conseguir opiniones y mejorar tu reputación.' },
        { label: 'Carta Online', description: 'Muestra tu menú digital con QR para que tus clientes vean productos y precios.' },
    ],
    note: 'Podés usar ambos de forma independiente o complementaria.',
} as const;

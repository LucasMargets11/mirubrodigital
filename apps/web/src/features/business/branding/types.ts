/**
 * Re-exports BusinessBranding types from the canonical source.
 * Use this path when importing from Carta Online, QR de Reseñas, or
 * any feature that must not depend on `features/gestion` directly.
 */
export type { BusinessBranding, BusinessBrandingPayload } from '@/features/gestion/types';

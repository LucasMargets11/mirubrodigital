/**
 * Re-exports branding API functions from the canonical source.
 * Use this path when importing from Carta Online, QR de Reseñas, or
 * any feature that must not depend on `features/gestion` directly.
 */
export {
    fetchBusinessBranding,
    updateBusinessBranding,
    uploadBusinessLogo,
} from '@/features/gestion/api';

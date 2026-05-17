/**
 * Re-exports branding hooks from the canonical source.
 * Use this path when importing from Carta Online, QR de Reseñas, or
 * any feature that must not depend on `features/gestion` directly.
 */
export {
    useBusinessBrandingQuery,
    useUpdateBusinessBrandingMutation,
    useUploadBusinessLogoMutation,
} from '@/features/gestion/hooks';

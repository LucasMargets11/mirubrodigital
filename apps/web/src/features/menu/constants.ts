/**
 * Plans that enable the `menu_item_images` capability.
 *
 * This is the **single source of truth** for the client-side fallback check.
 * When the feature flag `menu_item_images` is not yet propagated (stale
 * session), the pages fall back to checking the plan code against this list.
 *
 * If a new plan needs image support, add it here — every server page that
 * evaluates `canUploadImages` imports from this module.
 */
export const PLANS_WITH_IMAGES = [
    'menu_qr_visual',
    'menu_qr_marca',
    'menu_qr_pro',
    'menu_qr_premium',
    'plus',
    'business',
] as const;

/**
 * Evaluate whether the current session can upload menu item images.
 *
 * Checks the feature flag first; falls back to the plan-code list for
 * sessions whose feature dict may be stale.
 */
export function canUploadMenuImages(
    features: Record<string, boolean> | null | undefined,
    planCode: string | null | undefined,
): boolean {
    if (features?.menu_item_images === true) return true;
    return PLANS_WITH_IMAGES.includes(planCode as (typeof PLANS_WITH_IMAGES)[number]);
}

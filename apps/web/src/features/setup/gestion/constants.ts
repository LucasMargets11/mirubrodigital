/**
 * Priority order of setup steps per plan.
 * Used by getRecommendedSetupTask() to determine the next actionable step.
 *
 * Rules:
 * - 'business' and 'enterprise' share the same order.
 * - Steps not available in a given plan will have status='upgrade' in the API
 *   response, so they are automatically skipped by getRecommendedSetupTask().
 */
export const SETUP_PRIORITY_ORDER: Record<string, string[]> = {
    starter: [
        'gestion.business_and_fiscal',
        'gestion.products',
        'gestion.categories',
        'gestion.initial_stock',
        'gestion.branding',
    ],
    pro: [
        'gestion.business_and_fiscal',
        'gestion.products',
        'gestion.treasury_accounts',
        'gestion.cash_link',
        'gestion.document_series',
        'gestion.categories',
        'gestion.initial_stock',
        'gestion.branding',
        'gestion.team',
    ],
    business: [
        'gestion.business_and_fiscal',
        'gestion.products',
        'gestion.treasury_accounts',
        'gestion.document_series',
        'gestion.branches',
        'gestion.cash_link',
        'gestion.categories',
        'gestion.initial_stock',
        'gestion.branding',
        'gestion.team',
    ],
    enterprise: [
        'gestion.business_and_fiscal',
        'gestion.products',
        'gestion.treasury_accounts',
        'gestion.document_series',
        'gestion.branches',
        'gestion.cash_link',
        'gestion.categories',
        'gestion.initial_stock',
        'gestion.branding',
        'gestion.team',
    ],
};

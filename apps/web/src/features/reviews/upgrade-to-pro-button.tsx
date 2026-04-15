/**
 * UpgradeToProButton — in-place upgrade CTA for active businesses on Reseñas Base.
 *
 * Calls POST /api/v1/billing/reviews/upgrade/ and redirects to MercadoPago.
 * Renders a styled button with loading + error states.
 */
'use client';

import { useReviewsUpgrade } from '@/features/reviews/use-reviews-upgrade';
import { CTA_UPGRADE_PRO_INPLACE } from '@/features/reviews/product';

type Props = {
    /** Extra tailwind classes for the wrapper (not the button). */
    className?: string;
    /** Size variant. */
    size?: 'sm' | 'md';
};

export function UpgradeToProButton({ className = '', size = 'md' }: Props) {
    const { startUpgrade, loading, error } = useReviewsUpgrade();

    const btnClasses =
        size === 'sm'
            ? 'rounded-full bg-brand-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors disabled:opacity-50'
            : 'rounded-full bg-brand-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 transition-colors disabled:opacity-50';

    return (
        <div className={className}>
            <button onClick={startUpgrade} disabled={loading} className={btnClasses}>
                {loading ? CTA_UPGRADE_PRO_INPLACE.loadingLabel : CTA_UPGRADE_PRO_INPLACE.label}
            </button>
            {error && (
                <p className="mt-1 text-xs text-red-600">{error}</p>
            )}
        </div>
    );
}

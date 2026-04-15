/**
 * DowngradeToBaseButton — downgrade CTA for active businesses on Reseñas Pro.
 *
 * Calls POST /api/v1/billing/reviews/downgrade/ after user confirms.
 * On success, dispatches 'reviews-config-changed' so nav and config re-fetch.
 */
'use client';

import { useState } from 'react';
import { useReviewsDowngrade } from '@/features/reviews/use-reviews-downgrade';
import { CTA_DOWNGRADE_TO_BASE } from '@/features/reviews/product';

type Props = {
    className?: string;
    onDowngraded?: () => void;
};

export function DowngradeToBaseButton({ className = '', onDowngraded }: Props) {
    const { executeDowngrade, loading, error } = useReviewsDowngrade();
    const [confirming, setConfirming] = useState(false);

    async function handleConfirm() {
        const result = await executeDowngrade();
        if (result) {
            setConfirming(false);
            window.dispatchEvent(new Event('reviews-config-changed'));
            onDowngraded?.();
        }
    }

    if (!confirming) {
        return (
            <div className={className}>
                <button
                    onClick={() => setConfirming(true)}
                    disabled={loading}
                    className="rounded-full border border-slate-300 bg-white px-4 py-1.5 text-xs font-medium text-slate-600 shadow-sm hover:bg-slate-50 transition-colors disabled:opacity-50"
                >
                    {CTA_DOWNGRADE_TO_BASE.label}
                </button>
            </div>
        );
    }

    return (
        <div className={`rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-3 ${className}`}>
            <p className="text-sm font-semibold text-amber-900">
                {CTA_DOWNGRADE_TO_BASE.confirmTitle}
            </p>
            <p className="text-xs text-amber-800">
                {CTA_DOWNGRADE_TO_BASE.confirmMessage}
            </p>
            <div className="flex gap-2">
                <button
                    onClick={handleConfirm}
                    disabled={loading}
                    className="rounded-full bg-amber-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-amber-700 transition-colors disabled:opacity-50"
                >
                    {loading ? CTA_DOWNGRADE_TO_BASE.loadingLabel : CTA_DOWNGRADE_TO_BASE.confirmButton}
                </button>
                <button
                    onClick={() => setConfirming(false)}
                    disabled={loading}
                    className="rounded-full border border-slate-300 bg-white px-4 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
                >
                    {CTA_DOWNGRADE_TO_BASE.cancelButton}
                </button>
            </div>
            {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
    );
}

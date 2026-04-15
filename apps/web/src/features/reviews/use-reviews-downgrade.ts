/**
 * useReviewsDowngrade — triggers the downgrade from Reseñas Pro → Base.
 *
 * Calls POST /api/v1/billing/reviews/downgrade/ with { confirm: true }.
 * Immediate — no payment, no redirect. Returns result inline.
 */

import { useState, useCallback } from 'react';
import { getClientApiBaseUrl } from '@/lib/api-url';

const API_URL = getClientApiBaseUrl();

type DowngradeResult = {
    plan: string;
    previous_plan: string;
    message: string;
};

export function useReviewsDowngrade() {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const executeDowngrade = useCallback(async (): Promise<DowngradeResult | null> => {
        setLoading(true);
        setError(null);

        try {
            const res = await fetch(`${API_URL}/api/v1/billing/reviews/downgrade/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ confirm: true }),
            });

            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                const msg = body?.detail ?? 'No pudimos procesar el cambio. Intentá de nuevo.';
                setError(msg);
                setLoading(false);
                return null;
            }

            const data: DowngradeResult = await res.json();
            setLoading(false);
            return data;
        } catch {
            setError('Error de red. Verificá tu conexión e intentalo de nuevo.');
            setLoading(false);
            return null;
        }
    }, []);

    return { executeDowngrade, loading, error };
}

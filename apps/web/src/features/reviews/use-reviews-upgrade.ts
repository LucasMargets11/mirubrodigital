/**
 * useReviewsUpgrade — triggers the in-place upgrade from Reseñas Base → Pro.
 *
 * Calls POST /api/v1/billing/reviews/upgrade/ which creates a MercadoPago
 * preference and returns a checkout_url.  The caller redirects the user to
 * that URL; after payment MP redirects back to /app/resenas?upgrade=success.
 */

import { useState, useCallback } from 'react';
import { getClientApiBaseUrl } from '@/lib/api-url';

const API_URL = getClientApiBaseUrl();

type UpgradeResult = {
    pending_change_id: number;
    checkout_url: string;
    message: string;
};

export function useReviewsUpgrade() {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const startUpgrade = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const res = await fetch(`${API_URL}/api/v1/billing/reviews/upgrade/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
            });

            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                const msg = body?.detail ?? 'No pudimos iniciar el upgrade. Intentá de nuevo.';
                setError(msg);
                setLoading(false);
                return null;
            }

            const data: UpgradeResult = await res.json();
            // Redirect to MercadoPago checkout
            if (data.checkout_url) {
                window.location.assign(data.checkout_url);
            }
            return data;
        } catch {
            setError('Error de red. Verificá tu conexión e intentalo de nuevo.');
            setLoading(false);
            return null;
        }
    }, []);

    return { startUpgrade, loading, error };
}

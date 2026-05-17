import { useCallback, useState } from 'react';

import { generateQrPosterPdf, downloadBlob } from './api';
import type { GenerateQrPosterPayload } from './types';

/**
 * Hook para generar y descargar el PDF de un Cartel QR de Reseñas PRO.
 * Mismo patrón que useGeneratePrintablePdf en features/printables/hooks.ts.
 */
export function useGenerateQrPosterPdf() {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const generate = useCallback(async (payload: GenerateQrPosterPayload) => {
        setIsLoading(true);
        setError(null);
        try {
            const blob = await generateQrPosterPdf(payload);
            downloadBlob(blob, 'cartel-qr-resenas.pdf');
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : 'No pudimos generar el cartel. Intentá nuevamente.',
            );
        } finally {
            setIsLoading(false);
        }
    }, []);

    const clearError = useCallback(() => setError(null), []);

    return { generate, isLoading, error, clearError };
}

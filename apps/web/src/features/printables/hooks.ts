import { useCallback, useState } from 'react';

import { generatePrintablePdf, downloadBlob } from './api';
import type { GeneratePrintablePdfPayload } from './types';

/**
 * Hook para generar y descargar un PDF de carteles/etiquetas.
 */
export function useGeneratePrintablePdf() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = useCallback(async (payload: GeneratePrintablePdfPayload) => {
    setIsLoading(true);
    setError(null);
    try {
      const blob = await generatePrintablePdf(payload);
      downloadBlob(blob, 'carteles-etiquetas.pdf');
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'No se pudo generar el PDF. Intentá nuevamente.';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { generate, isLoading, error, clearError };
}

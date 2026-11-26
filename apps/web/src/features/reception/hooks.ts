import { useQuery } from '@tanstack/react-query';

import { getAIUsageSummary } from './api';

export const aiUsageSummaryKey = ['reception', 'ai-usage-summary'];

export function useAIUsageSummary() {
    return useQuery({
        queryKey: aiUsageSummaryKey,
        queryFn: getAIUsageSummary,
        // Lectura de estado comercial: sin reintentos ante 403/5xx para no
        // enmascarar un servicio no contratado o suspendido.
        retry: false,
        staleTime: 60_000,
    });
}

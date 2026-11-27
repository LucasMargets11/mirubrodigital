import { useQuery } from '@tanstack/react-query';

import {
    getAIUsageSummary, getAdminAIUsage, getAdminOperationalMetrics, getAdminWhatsAppConnections, type MetricsRange,
} from './api';

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

// PROD-08D — Platform Admin. Claves por cliente (y rango): un cambio de
// cliente nunca reutiliza datos del anterior.
const ADMIN_READ = { retry: false, retryOnMount: false, refetchOnWindowFocus: false, staleTime: 60_000 } as const;

export function useAdminAIUsage(businessId: number) {
    return useQuery({
        queryKey: ['platform-admin', 'ai-usage', businessId],
        queryFn: () => getAdminAIUsage(businessId),
        ...ADMIN_READ,
    });
}

export function useAdminOperationalMetrics(businessId: number, range: MetricsRange, enabled: boolean) {
    return useQuery({
        queryKey: ['platform-admin', 'operational-metrics', businessId, range.date_from ?? null, range.date_to ?? null],
        queryFn: () => getAdminOperationalMetrics(businessId, range),
        enabled,
        ...ADMIN_READ,
    });
}

/** PROD-08E2 — Sin polling: se actualiza solo a pedido (`refetch`). */
export function useAdminWhatsAppConnections(businessId: number) {
    return useQuery({
        queryKey: ['platform-admin', 'whatsapp-connections', businessId],
        queryFn: () => getAdminWhatsAppConnections(businessId),
        ...ADMIN_READ,
    });
}

import { apiGet } from '@/lib/api/client';

import type { AIUsageSummary, AdminAIUsageOverview, AdminWhatsAppConnections, OperationalMetrics } from './types';

/** Consumo comercial de IA del negocio activo (403 `ai_service_not_contracted` sin fuente IA). */
export function getAIUsageSummary() {
    return apiGet<AIUsageSummary>('/api/v1/ai-usage/');
}

/** PROD-08D — Platform Admin: el Business sale solo de la ruta (nunca de `bid`). */
export function getAdminAIUsage(businessId: number) {
    return apiGet<AdminAIUsageOverview>(`/api/v1/platform-admin/clients/${businessId}/ai-usage/`);
}

export type MetricsRange = { date_from?: string; date_to?: string };

export function getAdminOperationalMetrics(businessId: number, range: MetricsRange) {
    const params = new URLSearchParams();
    if (range.date_from) params.set('date_from', range.date_from);
    if (range.date_to) params.set('date_to', range.date_to);
    const qs = params.toString();
    return apiGet<OperationalMetrics>(
        `/api/v1/platform-admin/clients/${businessId}/operational-metrics/${qs ? `?${qs}` : ''}`,
    );
}

/** PROD-08E2 — Estado local de canales y autorizaciones WhatsApp (solo lectura). */
export function getAdminWhatsAppConnections(businessId: number) {
    return apiGet<AdminWhatsAppConnections>(`/api/v1/platform-admin/clients/${businessId}/whatsapp-connections/`);
}

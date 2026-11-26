import { apiGet } from '@/lib/api/client';

import type { AIUsageSummary } from './types';

/** Consumo comercial de IA del negocio activo (403 `ai_service_not_contracted` sin fuente IA). */
export function getAIUsageSummary() {
    return apiGet<AIUsageSummary>('/api/v1/ai-usage/');
}

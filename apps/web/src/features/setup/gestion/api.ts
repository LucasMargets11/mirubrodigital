import { apiGet } from '@/lib/api/client';

import type { GestionSetupContext } from './types';

export function fetchGestionSetupContext(): Promise<GestionSetupContext> {
    return apiGet<GestionSetupContext>('/api/v1/setup/gestion/context');
}

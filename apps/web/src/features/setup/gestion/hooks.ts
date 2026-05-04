import { useQuery } from '@tanstack/react-query';

import { fetchGestionSetupContext } from './api';
import type { GestionSetupContext } from './types';

export function useGestionSetupContext() {
    return useQuery<GestionSetupContext>({
        queryKey: ['gestion-setup-context'],
        queryFn: fetchGestionSetupContext,
        staleTime: 30_000,
    });
}

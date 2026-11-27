'use client';

import { useMemo } from 'react';

import { Providers } from '@/app/providers';
import { AdminAIUsageSection } from '@/components/admin/admin-ai-usage-section';
import { AdminOperationalMetricsSection } from '@/components/admin/admin-operational-metrics-section';
import { SectionCard } from '@/components/admin/section-card';
import {
    ReceptionistConfigForm,
    isClientWithoutReception,
    useReceptionistConfig,
} from '@/features/reception/receptionist-config-form';
import type { ReceptionistConfigTarget } from '@/features/reception/receptionist-config-api';

type Props = {
    businessId: number;
    businessName: string;
};

/**
 * PROD-08C/08D — Recepcionista IA en el detalle del cliente (Platform Admin):
 * configuración del agente, consumo comercial y métricas operativas, bajo un
 * único `Providers` (`/admin` no tiene QueryClient propio).
 *
 * El Business sale solo del id de la ruta, nunca de `bid`. El bloque entero se
 * oculta solo ante el 404 de dominio `client_not_found` del endpoint de
 * configuración (cliente sin Recepcionista aplicable, sea servicio principal o
 * adicional). Cada sección tiene sus propios estados de carga y error.
 */
export function ReceptionistAdminCard(props: Props) {
    return (
        <Providers>
            <ReceptionistAdminSections {...props} />
        </Providers>
    );
}

function ReceptionistAdminSections({ businessId, businessName }: Props) {
    const target = useMemo<ReceptionistConfigTarget>(() => ({ kind: 'platform_admin', businessId }), [businessId]);
    const { query } = useReceptionistConfig(target);

    // Hasta saber si el cliente tiene Recepcionista no se muestra el bloque.
    if (query.isLoading) return null;
    if (query.isError && isClientWithoutReception(query.error)) return null;

    return (
        <>
            <SectionCard
                title="Recepcionista IA"
                description="Configuración del agente de este cliente. «Configuración lista» no significa agente conectado."
            >
                <ReceptionistConfigForm target={target} businessName={`${businessName} (ID ${businessId})`} canEdit />
            </SectionCard>
            <AdminAIUsageSection businessId={businessId} />
            <AdminOperationalMetricsSection businessId={businessId} />
        </>
    );
}

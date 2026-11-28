'use client';

import { useMemo } from 'react';

import { Providers } from '@/app/providers';
import { AdminAIUsageSection } from '@/components/admin/admin-ai-usage-section';
import { AdminOperationalMetricsSection } from '@/components/admin/admin-operational-metrics-section';
import { AdminWhatsAppConnectionsSection } from '@/components/admin/admin-whatsapp-connections-section';
import { ReceptionistReadinessSection } from '@/components/admin/receptionist-readiness-section';
import { SectionCard } from '@/components/admin/section-card';
import {
    ReceptionistConfigForm,
    isClientWithoutReception,
    useReceptionistConfig,
} from '@/features/reception/receptionist-config-form';
import type { ReceptionistConfigTarget } from '@/features/reception/receptionist-config-api';
import type { AdminMember } from '@/lib/admin/types';

type Props = {
    businessId: number;
    businessName: string;
    /** Owner del detalle del cliente (membership activa), para la preparación. */
    owner: AdminMember | null;
    /** PROD-09D2: superadmin puede extender la vigencia bonificada (el backend decide). */
    canExtendValidity?: boolean;
};

/**
 * PROD-08C/08D/08E2/09B — Recepcionista IA en el detalle del cliente
 * (Platform Admin): preparación, configuración del agente, conexiones
 * WhatsApp, consumo comercial y métricas operativas, bajo un único
 * `Providers` (`/admin` no tiene QueryClient propio).
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

function ReceptionistAdminSections({ businessId, businessName, owner, canExtendValidity = false }: Props) {
    const target = useMemo<ReceptionistConfigTarget>(() => ({ kind: 'platform_admin', businessId }), [businessId]);
    const { adapter, query } = useReceptionistConfig(target);

    // Hasta saber si el cliente tiene Recepcionista no se muestra el bloque.
    if (query.isLoading) return null;
    if (query.isError && isClientWithoutReception(query.error)) return null;

    return (
        <>
            <ReceptionistReadinessSection
                businessId={businessId}
                businessName={`${businessName} (ID ${businessId})`}
                owner={owner}
                config={query}
                adapter={adapter}
            />
            <SectionCard
                title="Recepcionista IA"
                description="Configuración del agente de este cliente. «Configuración lista» no significa agente conectado."
            >
                <ReceptionistConfigForm target={target} businessName={`${businessName} (ID ${businessId})`} canEdit />
            </SectionCard>
            <AdminWhatsAppConnectionsSection businessId={businessId} />
            <AdminAIUsageSection
                businessId={businessId}
                businessName={`${businessName} (ID ${businessId})`}
                canExtendValidity={canExtendValidity}
            />
            <AdminOperationalMetricsSection businessId={businessId} />
        </>
    );
}

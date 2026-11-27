'use client';

import { useMemo } from 'react';

import { Providers } from '@/app/providers';
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
 * PROD-08C — Recepcionista IA en el detalle del cliente (Platform Admin).
 * Monta el formulario compartido de PROD-08B con el adaptador
 * `platform_admin`: el Business sale solo del id de la ruta, nunca de `bid`.
 *
 * Se oculta solo ante el 404 de dominio `client_not_found` (cliente sin
 * Recepcionista aplicable, sea servicio principal o adicional). Permisos
 * (403), red y otros errores se muestran dentro de la sección.
 * `/admin` no tiene QueryClient propio: se reutiliza `Providers`.
 */
export function ReceptionistConfigCard(props: Props) {
    return (
        <Providers>
            <ReceptionistConfigSection {...props} />
        </Providers>
    );
}

function ReceptionistConfigSection({ businessId, businessName }: Props) {
    const target = useMemo<ReceptionistConfigTarget>(() => ({ kind: 'platform_admin', businessId }), [businessId]);
    const { query } = useReceptionistConfig(target);

    // Hasta saber si el cliente tiene Recepcionista no se muestra la sección.
    if (query.isLoading) return null;
    if (query.isError && isClientWithoutReception(query.error)) return null;

    return (
        <SectionCard
            title="Recepcionista IA"
            description="Configuración del agente de este cliente. «Configuración lista» no significa agente conectado."
        >
            <ReceptionistConfigForm target={target} businessName={`${businessName} (ID ${businessId})`} canEdit />
        </SectionCard>
    );
}

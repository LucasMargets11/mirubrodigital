import { renderLeadDetailPage } from '@/features/leads/ui/leads-pages';

type Props = {
    params: Promise<{ id: string }>;
};

/** Detalle de Lead de Turnos (LEADS 05B). Implementación única en `features/leads/ui` (PROD-02G2). */
export default async function LeadDetailPage({ params }: Props) {
    const { id } = await params;
    return renderLeadDetailPage('appointments', id);
}

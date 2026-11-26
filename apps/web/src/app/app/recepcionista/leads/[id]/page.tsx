import { renderLeadDetailPage } from '@/features/leads/ui/leads-pages';

type Props = {
    params: Promise<{ id: string }>;
};

/** PROD-02G2: detalle de Lead de Recepcionista IA (misma implementación que Turnos). */
export default async function RecepcionistaLeadDetailPage({ params }: Props) {
    const { id } = await params;
    return renderLeadDetailPage('reception', id);
}

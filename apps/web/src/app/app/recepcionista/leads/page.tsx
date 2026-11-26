import { renderLeadsInboxPage } from '@/features/leads/ui/leads-pages';

/** PROD-02G2: bandeja de Leads de Recepcionista IA (misma implementación que Turnos). */
export default async function RecepcionistaLeadsPage() {
    return renderLeadsInboxPage('reception');
}

import { renderLeadsInboxPage } from '@/features/leads/ui/leads-pages';

/** Bandeja de Leads de Turnos (LEADS 05A). Implementación única en `features/leads/ui` (PROD-02G2). */
export default async function LeadsPage() {
    return renderLeadsInboxPage('appointments');
}

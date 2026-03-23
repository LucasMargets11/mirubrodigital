import { Metadata } from 'next';

import { AdminPageHeader } from '@/components/admin/admin-page-header';
import { getAdminTickets, getAdminTicketKPIs } from '@/lib/admin';
import { SoporteContent } from './soporte-content';

export const metadata: Metadata = {
  title: 'Soporte | Mi Rubro Admin',
};

type Props = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function AdminSoportePage({ searchParams }: Props) {
  const raw = await searchParams;
  const params: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (typeof v === 'string') params[k] = v;
  }

  const [tickets, kpis] = await Promise.all([
    getAdminTickets(params),
    getAdminTicketKPIs(),
  ]);

  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Soporte"
        description="Tickets y solicitudes de soporte de los clientes."
      />
      <SoporteContent initialData={tickets} kpis={kpis} initialParams={params} />
    </div>
  );
}
